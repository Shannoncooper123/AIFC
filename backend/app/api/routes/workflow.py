"""
Workflow Trace API - 提供 workflow 运行记录的查询接口

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
from modules.agent.utils.workflow_trace_storage import get_trace_path


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/workflow", tags=["workflow"])


class TraceEventCache:
    """Trace 事件缓存 - 避免重复读取文件"""
    
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


_trace_cache = TraceEventCache(ttl_seconds=2.0)


def _read_events_sync() -> List[Dict[str, Any]]:
    """同步读取所有 trace 事件（带缓存）"""
    return _trace_cache.get_all_events()


def _read_events_for_run_sync(workflow_run_id: str) -> List[Dict[str, Any]]:
    """同步读取指定 workflow_run_id 的事件（O(1) 查找）"""
    return _trace_cache.get_events_by_workflow_run_id(workflow_run_id)


async def _read_events() -> List[Dict[str, Any]]:
    """异步读取所有 trace 事件（在线程池中执行）"""
    return await asyncio.to_thread(_read_events_sync)


async def _read_events_for_run(workflow_run_id: str) -> List[Dict[str, Any]]:
    """异步读取指定 workflow_run_id 的事件（在线程池中执行）"""
    return await asyncio.to_thread(_read_events_for_run_sync, workflow_run_id)


def _summarize_runs(events: List[Dict[str, Any]]) -> List[WorkflowRunSummary]:
    """汇总运行记录"""
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
    events = await _read_events()
    runs = _summarize_runs(events)
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
    """获取 artifact 文件"""
    events = await _read_events()
    for e in events:
        if e.get("type") == "artifact":
            payload = e.get("payload") or {}
            if payload.get("artifact_id") == artifact_id:
                file_path = payload.get("file_path")
                if not file_path or not os.path.exists(file_path):
                    raise HTTPException(status_code=404, detail="文件不存在")
                return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="Artifact 不存在")
