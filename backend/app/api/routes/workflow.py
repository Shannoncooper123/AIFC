"""
Workflow Trace API - 提供 workflow 运行记录的查询接口

优化后的存储结构：
- workflow_index.jsonl: 索引文件，存储每个 workflow 的摘要信息（用于快速列表查询）
- workflow_traces/: 目录，按 workflow_run_id 分文件存储详细 trace

新的 trace 结构使用 trace_id 和 parent_trace_id 建立层级关系，
每个 trace 记录包含 type 字段标识类型：
- workflow: 顶层工作流
- node: LangGraph 节点
- agent: Agent 调用
- model_call: 模型调用
- tool_call: 工具调用
- artifact: 图片等产物
"""
import asyncio
import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.models.schemas import (
    WorkflowRunsResponse,
    WorkflowRunSummary,
    WorkflowRunDetailResponse,
    WorkflowRunEvent,
    WorkflowArtifact,
    WorkflowTimelineResponse,
    WorkflowTimeline,
    WorkflowTraceItem,
)
from modules.agent.utils.workflow_trace_storage import (
    get_trace_path,
    get_index_path,
    get_traces_dir,
    get_workflow_trace_path,
    get_artifact_index_path,
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/workflow", tags=["workflow"])


class WorkflowIndexCache:
    """Workflow 索引缓存 - 只缓存索引文件，用于快速列表查询"""
    
    def __init__(self, ttl_seconds: float = 2.0):
        self._runs: Dict[str, WorkflowRunSummary] = {}
        self._last_load_time: float = 0
        self._last_file_mtime: float = 0
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
    
    def _should_reload(self, index_path: str) -> bool:
        """检查是否需要重新加载"""
        if not os.path.exists(index_path):
            return False
        
        current_time = time.time()
        if current_time - self._last_load_time < self._ttl:
            return False
        
        try:
            file_mtime = os.path.getmtime(index_path)
            if file_mtime > self._last_file_mtime:
                return True
        except OSError:
            pass
        
        return False
    
    def _load_index(self, index_path: str) -> None:
        """加载索引文件并合并同一 run_id 的记录"""
        runs: Dict[str, WorkflowRunSummary] = {}
        
        if not os.path.exists(index_path):
            self._runs = runs
            return
        
        with open(index_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    run_id = record.get("run_id")
                    if not run_id:
                        continue
                    
                    if run_id not in runs:
                        runs[run_id] = WorkflowRunSummary(
                            run_id=run_id,
                            start_time=record.get("start_time"),
                            end_time=record.get("end_time"),
                            duration_ms=record.get("duration_ms"),
                            status=record.get("status"),
                            symbols=record.get("symbols") or [],
                            pending_count=record.get("pending_count") or 0,
                            nodes_count=record.get("nodes_count") or 0,
                            tool_calls_count=record.get("tool_calls_count") or 0,
                            model_calls_count=record.get("model_calls_count") or 0,
                            artifacts_count=record.get("artifacts_count") or 0,
                        )
                    else:
                        existing = runs[run_id]
                        status = record.get("status")
                        if status and status != "running":
                            existing.end_time = record.get("end_time")
                            existing.duration_ms = record.get("duration_ms")
                            existing.status = status
                            existing.nodes_count = record.get("nodes_count") or existing.nodes_count
                            existing.tool_calls_count = record.get("tool_calls_count") or existing.tool_calls_count
                            existing.model_calls_count = record.get("model_calls_count") or existing.model_calls_count
                            existing.artifacts_count = record.get("artifacts_count") or existing.artifacts_count
                        if record.get("symbols"):
                            existing.symbols = record.get("symbols")
                        if record.get("pending_count"):
                            existing.pending_count = record.get("pending_count")
                            
                except json.JSONDecodeError as e:
                    logger.warning(f"解析索引JSON行失败: {e}")
                    continue
        
        self._runs = runs
        self._last_load_time = time.time()
        try:
            self._last_file_mtime = os.path.getmtime(index_path)
        except OSError:
            pass
    
    def get_runs(self, limit: int = 50) -> List[WorkflowRunSummary]:
        """获取 workflow 运行列表（带缓存）"""
        index_path = get_index_path()
        with self._lock:
            if self._should_reload(index_path):
                self._load_index(index_path)
            runs = list(self._runs.values())
            runs_sorted = sorted(runs, key=lambda r: r.start_time or "", reverse=True)
            return runs_sorted[:limit]
    
    def get_total_count(self) -> int:
        """获取总运行数"""
        index_path = get_index_path()
        with self._lock:
            if self._should_reload(index_path):
                self._load_index(index_path)
            return len(self._runs)


class WorkflowTraceCache:
    """单个 Workflow Trace 缓存 - 按需加载单个 workflow 的 trace"""
    
    def __init__(self, ttl_seconds: float = 5.0):
        self._cache: Dict[str, tuple] = {}
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
    
    def _should_reload(self, workflow_run_id: str, trace_path: str) -> bool:
        """检查是否需要重新加载"""
        if not os.path.exists(trace_path):
            return False
        
        with self._lock:
            if workflow_run_id not in self._cache:
                return True
            
            _, last_load_time, last_file_mtime = self._cache[workflow_run_id]
            
            current_time = time.time()
            if current_time - last_load_time < self._ttl:
                return False
            
            try:
                file_mtime = os.path.getmtime(trace_path)
                if file_mtime > last_file_mtime:
                    return True
            except OSError:
                pass
            
            return False
    
    def _load_trace(self, workflow_run_id: str, trace_path: str) -> List[Dict[str, Any]]:
        """加载单个 workflow 的 trace 事件"""
        events: List[Dict[str, Any]] = []
        
        if not os.path.exists(trace_path):
            return events
        
        with open(trace_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    events.append(event)
                except json.JSONDecodeError as e:
                    logger.warning(f"解析trace JSON行失败: {e}")
                    continue
        
        with self._lock:
            try:
                file_mtime = os.path.getmtime(trace_path)
            except OSError:
                file_mtime = 0
            self._cache[workflow_run_id] = (events, time.time(), file_mtime)
        
        return events
    
    def get_events(self, workflow_run_id: str) -> List[Dict[str, Any]]:
        """获取单个 workflow 的 trace 事件（带缓存）"""
        trace_path = get_workflow_trace_path(workflow_run_id)
        
        if self._should_reload(workflow_run_id, trace_path):
            return self._load_trace(workflow_run_id, trace_path)
        
        with self._lock:
            if workflow_run_id in self._cache:
                return self._cache[workflow_run_id][0]
        
        return self._load_trace(workflow_run_id, trace_path)


class LegacyTraceCache:
    """旧版 Trace 缓存 - 兼容旧的单文件存储格式"""
    
    def __init__(self, ttl_seconds: float = 2.0):
        self._events: List[Dict[str, Any]] = []
        self._events_by_workflow_run_id: Dict[str, List[Dict[str, Any]]] = {}
        self._last_load_time: float = 0
        self._last_file_mtime: float = 0
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
    
    def _should_reload(self, trace_path: str) -> bool:
        """检查是否需要重新加载"""
        if not os.path.exists(trace_path):
            return False
        
        current_time = time.time()
        if current_time - self._last_load_time < self._ttl:
            return False
        
        try:
            file_mtime = os.path.getmtime(trace_path)
            if file_mtime > self._last_file_mtime:
                return True
        except OSError:
            pass
        
        return False
    
    def _load_events(self, trace_path: str) -> None:
        """加载事件并建立索引"""
        events: List[Dict[str, Any]] = []
        events_by_workflow_run_id: Dict[str, List[Dict[str, Any]]] = {}
        
        if not os.path.exists(trace_path):
            self._events = events
            self._events_by_workflow_run_id = events_by_workflow_run_id
            return
        
        with open(trace_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    events.append(event)
                    workflow_run_id = event.get("workflow_run_id")
                    if workflow_run_id:
                        if workflow_run_id not in events_by_workflow_run_id:
                            events_by_workflow_run_id[workflow_run_id] = []
                        events_by_workflow_run_id[workflow_run_id].append(event)
                except json.JSONDecodeError as e:
                    logger.warning(f"解析工作流事件JSON行失败: {e}")
                    continue
        
        self._events = events
        self._events_by_workflow_run_id = events_by_workflow_run_id
        self._last_load_time = time.time()
        try:
            self._last_file_mtime = os.path.getmtime(trace_path)
        except OSError:
            pass
    
    def get_all_events(self) -> List[Dict[str, Any]]:
        """获取所有事件（带缓存）"""
        trace_path = get_trace_path()
        with self._lock:
            if self._should_reload(trace_path):
                self._load_events(trace_path)
            return self._events
    
    def get_events_by_workflow_run_id(self, workflow_run_id: str) -> List[Dict[str, Any]]:
        """按 workflow_run_id 获取事件（O(1) 查找）"""
        trace_path = get_trace_path()
        with self._lock:
            if self._should_reload(trace_path):
                self._load_events(trace_path)
            return self._events_by_workflow_run_id.get(workflow_run_id, [])


class ArtifactIndexCache:
    """Artifact 索引缓存 - 用于快速查找 artifact_id 到 file_path 的映射
    
    通过索引文件实现 O(1) 查找，避免遍历所有 trace 文件。
    """
    
    def __init__(self, ttl_seconds: float = 5.0):
        self._artifacts: Dict[str, Dict[str, Any]] = {}
        self._last_load_time: float = 0
        self._last_file_mtime: float = 0
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
    
    def _should_reload(self, index_path: str) -> bool:
        """检查是否需要重新加载"""
        if not os.path.exists(index_path):
            return False
        
        current_time = time.time()
        if current_time - self._last_load_time < self._ttl:
            return False
        
        try:
            file_mtime = os.path.getmtime(index_path)
            if file_mtime > self._last_file_mtime:
                return True
        except OSError:
            pass
        
        return False
    
    def _load_index(self, index_path: str) -> None:
        """加载 artifact 索引文件"""
        artifacts: Dict[str, Dict[str, Any]] = {}
        
        if not os.path.exists(index_path):
            self._artifacts = artifacts
            return
        
        with open(index_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    artifact_id = record.get("artifact_id")
                    if artifact_id:
                        artifacts[artifact_id] = record
                except json.JSONDecodeError as e:
                    logger.warning(f"解析 artifact 索引 JSON 行失败: {e}")
                    continue
        
        self._artifacts = artifacts
        self._last_load_time = time.time()
        try:
            self._last_file_mtime = os.path.getmtime(index_path)
        except OSError:
            pass
    
    def get_artifact_info(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        """通过 artifact_id 获取 artifact 信息（带缓存）
        
        Returns:
            包含 file_path, workflow_run_id, symbol, interval 等信息的字典，
            如果未找到则返回 None
        """
        index_path = get_artifact_index_path()
        with self._lock:
            if self._should_reload(index_path):
                self._load_index(index_path)
            return self._artifacts.get(artifact_id)
    
    def get_artifacts_by_workflow(self, workflow_run_id: str) -> List[Dict[str, Any]]:
        """获取指定 workflow 的所有 artifacts（带缓存）"""
        index_path = get_artifact_index_path()
        with self._lock:
            if self._should_reload(index_path):
                self._load_index(index_path)
            return [
                info for info in self._artifacts.values()
                if info.get("workflow_run_id") == workflow_run_id
            ]


_index_cache = WorkflowIndexCache(ttl_seconds=2.0)
_trace_cache = WorkflowTraceCache(ttl_seconds=5.0)
_legacy_cache = LegacyTraceCache(ttl_seconds=2.0)
_artifact_index_cache = ArtifactIndexCache(ttl_seconds=5.0)


def _is_new_storage_available() -> bool:
    """检查是否使用新的存储格式"""
    index_path = get_index_path()
    traces_dir = get_traces_dir()
    return os.path.exists(index_path) or os.path.exists(traces_dir)


def _read_events_for_run_sync(workflow_run_id: str) -> List[Dict[str, Any]]:
    """同步读取指定 workflow_run_id 的事件"""
    trace_path = get_workflow_trace_path(workflow_run_id)
    if os.path.exists(trace_path):
        return _trace_cache.get_events(workflow_run_id)
    
    return _legacy_cache.get_events_by_workflow_run_id(workflow_run_id)


async def _read_events_for_run(workflow_run_id: str) -> List[Dict[str, Any]]:
    """异步读取指定 workflow_run_id 的事件（在线程池中执行）"""
    return await asyncio.to_thread(_read_events_for_run_sync, workflow_run_id)


def _summarize_runs_from_legacy(events: List[Dict[str, Any]]) -> List[WorkflowRunSummary]:
    """从旧版事件列表汇总运行记录"""
    runs: Dict[str, WorkflowRunSummary] = {}
    
    for event in events:
        workflow_run_id = event.get("workflow_run_id")
        if not workflow_run_id:
            continue
            
        if workflow_run_id not in runs:
            runs[workflow_run_id] = WorkflowRunSummary(
                run_id=workflow_run_id,
                start_time=None,
                end_time=None,
                duration_ms=None,
                status=None,
                symbols=[],
                pending_count=0,
                nodes_count=0,
                tool_calls_count=0,
                model_calls_count=0,
                artifacts_count=0,
            )
        
        run = runs[workflow_run_id]
        event_type = event.get("type")
        
        if event_type == "workflow":
            status = event.get("status")
            if status == "running":
                run.start_time = event.get("start_time")
                payload = event.get("payload", {})
                alert = payload.get("alert", {})
                run.symbols = alert.get("symbols", [])
                run.pending_count = int(alert.get("pending_count", 0))
            else:
                run.end_time = event.get("end_time")
                run.status = status
                run.duration_ms = event.get("duration_ms")
                if not run.start_time:
                    run.start_time = event.get("start_time")
        elif event_type == "node":
            run.nodes_count += 1
        elif event_type == "tool_call":
            run.tool_calls_count += 1
        elif event_type == "model_call":
            run.model_calls_count += 1
        elif event_type == "artifact":
            run.artifacts_count += 1
    
    return list(runs.values())


def _build_timeline(workflow_run_id: str, run_events: List[Dict[str, Any]]) -> WorkflowTimeline:
    """
    构建时间线树形结构
    
    使用 trace_id 和 parent_trace_id 建立层级关系
    """
    run_events = sorted(run_events, key=lambda e: e.get("timestamp_ms", 0))
    
    timeline = WorkflowTimeline(
        run_id=workflow_run_id,
        start_time=None,
        end_time=None,
        duration_ms=None,
        status=None,
        symbols=[],
        traces=[],
    )
    
    traces_map: Dict[str, WorkflowTraceItem] = {}
    
    for event in run_events:
        trace_id = event.get("trace_id")
        if not trace_id:
            continue
        
        event_type = event.get("type")
        status = event.get("status")
        
        if event_type == "workflow":
            if status == "running":
                timeline.start_time = event.get("start_time")
                payload = event.get("payload", {})
                alert = payload.get("alert", {})
                timeline.symbols = alert.get("symbols", [])
            else:
                timeline.end_time = event.get("end_time")
                timeline.status = status
                timeline.duration_ms = event.get("duration_ms")
                if not timeline.start_time:
                    timeline.start_time = event.get("start_time")
            continue
        
        if trace_id in traces_map:
            existing = traces_map[trace_id]
            if existing.status == "running" and status != "running":
                pass
            else:
                continue
        
        trace_item = WorkflowTraceItem(
            trace_id=trace_id,
            parent_trace_id=event.get("parent_trace_id"),
            type=event_type,
            name=event.get("name", "unknown"),
            symbol=event.get("symbol"),
            start_time=event.get("start_time"),
            end_time=event.get("end_time"),
            duration_ms=event.get("duration_ms"),
            status=status,
            error=event.get("error"),
            payload=event.get("payload"),
            children=[],
            artifacts=[],
        )
        
        traces_map[trace_id] = trace_item
    
    child_traces_map: Dict[str, List[WorkflowTraceItem]] = {}
    artifacts_map: Dict[str, List[WorkflowArtifact]] = {}
    root_traces: List[WorkflowTraceItem] = []
    
    for trace_id, trace_item in traces_map.items():
        parent_id = trace_item.parent_trace_id
        
        if trace_item.type == "artifact":
            payload = trace_item.payload or {}
            artifact = WorkflowArtifact(
                artifact_id=payload.get("artifact_id", trace_id),
                run_id=workflow_run_id,
                type=payload.get("artifact_type", "unknown"),
                file_path=payload.get("file_path", ""),
                trace_id=trace_id,
                parent_trace_id=parent_id,
                symbol=payload.get("symbol") or trace_item.symbol,
                interval=payload.get("interval"),
                image_id=payload.get("image_id"),
                created_at=trace_item.start_time,
            )
            if parent_id:
                if parent_id not in artifacts_map:
                    artifacts_map[parent_id] = []
                artifacts_map[parent_id].append(artifact)
            continue
        
        if parent_id and parent_id in traces_map:
            if parent_id not in child_traces_map:
                child_traces_map[parent_id] = []
            child_traces_map[parent_id].append(trace_item)
        elif parent_id == workflow_run_id or not parent_id:
            root_traces.append(trace_item)
    
    def attach_children_and_artifacts(trace_item: WorkflowTraceItem) -> None:
        """递归地将子 traces 和 artifacts 附加到父 trace"""
        children = child_traces_map.get(trace_item.trace_id, [])
        children.sort(key=lambda t: t.start_time or "")
        for child in children:
            attach_children_and_artifacts(child)
        trace_item.children = children
        trace_item.artifacts = artifacts_map.get(trace_item.trace_id, [])
    
    for trace_item in root_traces:
        attach_children_and_artifacts(trace_item)
    
    root_traces.sort(key=lambda t: t.start_time or "")
    timeline.traces = root_traces
    
    return timeline


@router.get("/runs", response_model=WorkflowRunsResponse)
async def list_runs(limit: int = Query(default=50, ge=1, le=500)):
    """获取 workflow 运行列表"""
    if _is_new_storage_available():
        runs = await asyncio.to_thread(_index_cache.get_runs, limit)
        total = await asyncio.to_thread(_index_cache.get_total_count)
        return WorkflowRunsResponse(runs=runs, total=total)
    else:
        events = await asyncio.to_thread(_legacy_cache.get_all_events)
        runs = _summarize_runs_from_legacy(events)
        runs_sorted = sorted(runs, key=lambda r: r.start_time or "", reverse=True)[:limit]
        return WorkflowRunsResponse(runs=runs_sorted, total=len(runs_sorted))


@router.get("/runs/{run_id}", response_model=WorkflowRunDetailResponse)
async def get_run(run_id: str):
    """获取 workflow 运行详情（原始事件列表）"""
    run_events = await _read_events_for_run(run_id)
    if not run_events:
        raise HTTPException(status_code=404, detail=f"运行记录不存在: {run_id}")
    run_events_sorted = sorted(run_events, key=lambda e: e.get("timestamp_ms", 0))
    return WorkflowRunDetailResponse(
        run_id=run_id,
        events=[WorkflowRunEvent(**e) for e in run_events_sorted],
    )


@router.get("/runs/{run_id}/timeline", response_model=WorkflowTimelineResponse)
async def get_run_timeline(run_id: str):
    """获取 workflow 运行时间线（树形结构）"""
    run_events = await _read_events_for_run(run_id)
    if not run_events:
        raise HTTPException(status_code=404, detail=f"运行记录不存在: {run_id}")
    timeline = _build_timeline(run_id, run_events)
    return WorkflowTimelineResponse(timeline=timeline)


@router.get("/runs/{run_id}/artifacts", response_model=List[WorkflowArtifact])
async def list_run_artifacts(run_id: str):
    """获取 workflow 运行的 artifacts"""
    run_events = await _read_events_for_run(run_id)
    artifacts = []
    for e in run_events:
        if e.get("type") == "artifact":
            payload = e.get("payload") or {}
            artifacts.append(WorkflowArtifact(
                artifact_id=payload.get("artifact_id", ""),
                run_id=run_id,
                type=payload.get("artifact_type", "unknown"),
                file_path=payload.get("file_path", ""),
                trace_id=e.get("trace_id"),
                parent_trace_id=e.get("parent_trace_id"),
                symbol=payload.get("symbol"),
                interval=payload.get("interval"),
                image_id=payload.get("image_id"),
                created_at=e.get("start_time"),
            ))
    return artifacts


@router.get("/artifacts/{artifact_id}")
async def get_artifact(artifact_id: str):
    """获取 artifact 文件
    
    优先从 artifact 索引缓存中查找（O(1)），
    如果索引中没有则降级到遍历 trace 文件（兼容旧数据）。
    """
    artifact_info = await asyncio.to_thread(_artifact_index_cache.get_artifact_info, artifact_id)
    if artifact_info:
        file_path = artifact_info.get("file_path")
        if file_path and os.path.exists(file_path):
            return FileResponse(file_path)
        elif file_path:
            logger.warning(f"Artifact 文件不存在: {file_path}")
    
    traces_dir = get_traces_dir()
    if os.path.exists(traces_dir):
        for filename in os.listdir(traces_dir):
            if not filename.endswith(".jsonl"):
                continue
            trace_path = os.path.join(traces_dir, filename)
            try:
                with open(trace_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            event = json.loads(line)
                            if event.get("type") == "artifact":
                                payload = event.get("payload") or {}
                                if payload.get("artifact_id") == artifact_id:
                                    file_path = payload.get("file_path")
                                    if file_path and os.path.exists(file_path):
                                        return FileResponse(file_path)
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                logger.warning(f"读取 trace 文件失败 {trace_path}: {e}")
                continue
    
    events = await asyncio.to_thread(_legacy_cache.get_all_events)
    for e in events:
        if e.get("type") == "artifact":
            payload = e.get("payload") or {}
            if payload.get("artifact_id") == artifact_id:
                file_path = payload.get("file_path")
                if not file_path or not os.path.exists(file_path):
                    raise HTTPException(status_code=404, detail="文件不存在")
                return FileResponse(file_path)
    
    raise HTTPException(status_code=404, detail="Artifact 不存在")
