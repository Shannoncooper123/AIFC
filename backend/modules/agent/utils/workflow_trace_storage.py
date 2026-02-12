"""
Workflow Trace 存储模块

提供 trace 事件的记录和存储功能。

存储结构（优化后）：
- workflow_index.jsonl: 索引文件，存储每个 workflow 的摘要信息
- workflow_traces/: 目录，按 workflow_run_id 分文件存储详细 trace

Trace 类型:
- workflow: 顶层工作流
- node: LangGraph 节点
- agent: Agent (create_trace_agent)
- model_call: 模型调用
- tool_call: 工具调用
- artifact: 图片等产物

公共工具函数:
- now_iso: 返回当前 UTC 时间的 ISO 格式字符串
- calculate_duration_ms: 计算两个 ISO 时间字符串之间的毫秒差
"""
import atexit
import base64
import json
import os
import queue
import time
import random
import string
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from modules.agent.trade_simulator.utils.file_utils import locked_append_jsonl
from modules.config.settings import get_config
from modules.monitor.utils.logger import get_logger

logger = get_logger("agent.workflow_trace")
_TRACE_FSYNC = False
_TRACE_ASYNC = True
_TRACE_QUEUE_MAX = 10000
_trace_queue: Optional["queue.Queue[Dict[str, Any]]"] = None
_trace_worker: Optional[threading.Thread] = None
_trace_running = False
_trace_lock = threading.Lock()

_workflow_counters: Dict[str, Dict[str, int]] = {}
_workflow_counters_lock = threading.Lock()


def _ensure_trace_worker() -> None:
    global _trace_queue, _trace_worker, _trace_running
    if not _TRACE_ASYNC:
        return
    if _trace_worker is None:
        with _trace_lock:
            if _trace_worker is None:
                _trace_queue = queue.Queue(maxsize=_TRACE_QUEUE_MAX)
                _trace_running = True
                _trace_worker = threading.Thread(
                    target=_trace_worker_loop,
                    daemon=False,
                    name="WorkflowTraceWriter",
                )
                _trace_worker.start()
                atexit.register(shutdown_trace_writer)


def _trace_worker_loop() -> None:
    while _trace_running or (_trace_queue and not _trace_queue.empty()):
        try:
            item = _trace_queue.get(timeout=0.5)
            trace_path = item["trace_path"]
            event = item["event"]
            locked_append_jsonl(trace_path, event, fsync=_TRACE_FSYNC)
            _trace_queue.task_done()
        except queue.Empty:
            continue
        except Exception as e:
            logger.error(f"workflow trace 异步写入失败: {e}", exc_info=True)


def shutdown_trace_writer(timeout: float = 5.0) -> None:
    global _trace_running, _trace_worker, _trace_queue
    if _trace_worker is None or _trace_queue is None:
        return
    _trace_running = False
    start = time.time()
    while not _trace_queue.empty():
        if time.time() - start >= timeout:
            break
        time.sleep(0.1)
    _trace_worker.join(timeout=max(0.5, timeout - (time.time() - start)))
    _trace_worker = None
    _trace_queue = None


def now_iso() -> str:
    """返回当前 UTC 时间的 ISO 格式字符串"""
    return datetime.now(timezone.utc).isoformat()


def calculate_duration_ms(start_time: str, end_time: str) -> int:
    """计算两个 ISO 时间字符串之间的毫秒差"""
    start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
    end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
    return int((end_dt - start_dt).total_seconds() * 1000)


def generate_trace_id(prefix: str = "trace") -> str:
    """
    生成唯一的 trace ID
    
    Args:
        prefix: ID 前缀，如 'wf'(workflow), 'node', 'agent', 'model', 'tool', 'art'
        
    Returns:
        格式: {prefix}_{timestamp}_{random}
    """
    now = datetime.now(timezone.utc)
    timestamp_part = now.strftime("%Y%m%d_%H%M%S")
    random_suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{prefix}_{timestamp_part}_{random_suffix}"


def _get_base_dir() -> str:
    """获取 backend 基础目录"""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _get_trace_path(cfg: Optional[Dict[str, Any]] = None) -> str:
    """获取旧版 trace 文件路径（兼容）"""
    if cfg is None:
        cfg = get_config()
    agent_cfg = cfg.get("agent", {})
    base_dir = _get_base_dir()
    trace_path = agent_cfg.get("workflow_trace_path", "logs/workflow_runs.jsonl")
    if not os.path.isabs(trace_path):
        trace_path = os.path.join(base_dir, trace_path)
    return trace_path


def _get_index_path(cfg: Optional[Dict[str, Any]] = None) -> str:
    """获取索引文件路径"""
    if cfg is None:
        cfg = get_config()
    agent_cfg = cfg.get("agent", {})
    base_dir = _get_base_dir()
    index_path = agent_cfg.get("workflow_index_path", "modules/data/workflow_index.jsonl")
    if not os.path.isabs(index_path):
        index_path = os.path.join(base_dir, index_path)
    return index_path


def _get_traces_dir(cfg: Optional[Dict[str, Any]] = None) -> str:
    """获取分文件存储目录"""
    if cfg is None:
        cfg = get_config()
    agent_cfg = cfg.get("agent", {})
    base_dir = _get_base_dir()
    traces_dir = agent_cfg.get("workflow_traces_dir", "modules/data/workflow_traces")
    if not os.path.isabs(traces_dir):
        traces_dir = os.path.join(base_dir, traces_dir)
    return traces_dir


def _get_workflow_trace_path(workflow_run_id: str, cfg: Optional[Dict[str, Any]] = None) -> str:
    """获取单个 workflow 的 trace 文件路径"""
    traces_dir = _get_traces_dir(cfg)
    os.makedirs(traces_dir, exist_ok=True)
    return os.path.join(traces_dir, f"{workflow_run_id}.jsonl")


def _get_artifacts_dir(cfg: Optional[Dict[str, Any]] = None) -> str:
    """获取 artifacts 目录路径"""
    if cfg is None:
        cfg = get_config()
    agent_cfg = cfg.get("agent", {})
    base_dir = _get_base_dir()
    artifacts_dir = agent_cfg.get("workflow_artifacts_dir", "logs/workflow_artifacts")
    if not os.path.isabs(artifacts_dir):
        artifacts_dir = os.path.join(base_dir, artifacts_dir)
    return artifacts_dir


def _get_artifact_index_path(cfg: Optional[Dict[str, Any]] = None) -> str:
    """获取 artifact 索引文件路径
    
    索引文件用于快速查找 artifact_id 到 file_path 的映射，
    避免遍历所有 trace 文件。
    """
    if cfg is None:
        cfg = get_config()
    agent_cfg = cfg.get("agent", {})
    base_dir = _get_base_dir()
    index_path = agent_cfg.get("artifact_index_path", "modules/data/artifact_index.jsonl")
    if not os.path.isabs(index_path):
        index_path = os.path.join(base_dir, index_path)
    return index_path


def get_trace_path(cfg: Optional[Dict[str, Any]] = None) -> str:
    """公开的获取旧版 trace 文件路径接口（兼容）"""
    return _get_trace_path(cfg)


def get_index_path(cfg: Optional[Dict[str, Any]] = None) -> str:
    """公开的获取索引文件路径接口"""
    return _get_index_path(cfg)


def get_traces_dir(cfg: Optional[Dict[str, Any]] = None) -> str:
    """公开的获取分文件存储目录接口"""
    return _get_traces_dir(cfg)


def get_workflow_trace_path(workflow_run_id: str, cfg: Optional[Dict[str, Any]] = None) -> str:
    """公开的获取单个 workflow trace 文件路径接口"""
    return _get_workflow_trace_path(workflow_run_id, cfg)


def get_artifacts_dir(cfg: Optional[Dict[str, Any]] = None) -> str:
    """公开的获取 artifacts 目录路径接口"""
    return _get_artifacts_dir(cfg)


def get_artifact_index_path(cfg: Optional[Dict[str, Any]] = None) -> str:
    """公开的获取 artifact 索引文件路径接口"""
    return _get_artifact_index_path(cfg)


def _increment_counter(workflow_run_id: str, counter_type: str) -> None:
    """增加 workflow 的计数器"""
    with _workflow_counters_lock:
        if workflow_run_id not in _workflow_counters:
            _workflow_counters[workflow_run_id] = {
                "nodes_count": 0,
                "tool_calls_count": 0,
                "model_calls_count": 0,
                "artifacts_count": 0,
            }
        if counter_type in _workflow_counters[workflow_run_id]:
            _workflow_counters[workflow_run_id][counter_type] += 1


def _get_counters(workflow_run_id: str) -> Dict[str, int]:
    """获取 workflow 的计数器"""
    with _workflow_counters_lock:
        return _workflow_counters.get(workflow_run_id, {
            "nodes_count": 0,
            "tool_calls_count": 0,
            "model_calls_count": 0,
            "artifacts_count": 0,
        }).copy()


def _clear_counters(workflow_run_id: str) -> None:
    """清除 workflow 的计数器"""
    with _workflow_counters_lock:
        if workflow_run_id in _workflow_counters:
            del _workflow_counters[workflow_run_id]


def _append_to_workflow_trace(workflow_run_id: str, event: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None) -> None:
    """追加事件到单个 workflow 的 trace 文件"""
    try:
        event["timestamp_ms"] = int(time.time() * 1000)
        trace_path = _get_workflow_trace_path(workflow_run_id, cfg)
        if _TRACE_ASYNC:
            _ensure_trace_worker()
            item = {"trace_path": trace_path, "event": event}
            try:
                _trace_queue.put(item, timeout=0.2)
            except queue.Full:
                locked_append_jsonl(trace_path, event, fsync=_TRACE_FSYNC)
        else:
            locked_append_jsonl(trace_path, event, fsync=_TRACE_FSYNC)
    except Exception as e:
        logger.error(f"workflow trace 写入失败: {e}")


def _append_to_index(index_record: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None) -> None:
    """追加记录到索引文件"""
    try:
        index_record["timestamp_ms"] = int(time.time() * 1000)
        index_path = _get_index_path(cfg)
        os.makedirs(os.path.dirname(index_path), exist_ok=True)
        if _TRACE_ASYNC:
            _ensure_trace_worker()
            item = {"trace_path": index_path, "event": index_record}
            try:
                _trace_queue.put(item, timeout=0.2)
            except queue.Full:
                locked_append_jsonl(index_path, index_record, fsync=_TRACE_FSYNC)
        else:
            locked_append_jsonl(index_path, index_record, fsync=_TRACE_FSYNC)
    except Exception as e:
        logger.error(f"workflow index 写入失败: {e}")


def _append_to_artifact_index(artifact_record: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None) -> None:
    """追加记录到 artifact 索引文件
    
    索引记录包含: artifact_id, workflow_run_id, file_path, symbol, interval
    用于快速通过 artifact_id 查找文件路径。
    """
    try:
        artifact_record["timestamp_ms"] = int(time.time() * 1000)
        index_path = _get_artifact_index_path(cfg)
        os.makedirs(os.path.dirname(index_path), exist_ok=True)
        if _TRACE_ASYNC:
            _ensure_trace_worker()
            item = {"trace_path": index_path, "event": artifact_record}
            try:
                _trace_queue.put(item, timeout=0.2)
            except queue.Full:
                locked_append_jsonl(index_path, artifact_record, fsync=_TRACE_FSYNC)
        else:
            locked_append_jsonl(index_path, artifact_record, fsync=_TRACE_FSYNC)
    except Exception as e:
        logger.error(f"artifact index 写入失败: {e}")


def append_event(event: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None) -> None:
    """追加 trace 事件到对应 workflow 的 trace 文件"""
    workflow_run_id = event.get("workflow_run_id")
    if not workflow_run_id:
        logger.warning("append_event: 缺少 workflow_run_id")
        return
    
    event_type = event.get("type")
    if event_type == "node":
        _increment_counter(workflow_run_id, "nodes_count")
    elif event_type == "tool_call":
        _increment_counter(workflow_run_id, "tool_calls_count")
    elif event_type == "model_call":
        _increment_counter(workflow_run_id, "model_calls_count")
    elif event_type == "artifact":
        _increment_counter(workflow_run_id, "artifacts_count")
    
    _append_to_workflow_trace(workflow_run_id, event, cfg)


def record_trace(
    workflow_run_id: str,
    trace_id: str,
    parent_trace_id: Optional[str],
    trace_type: str,
    name: str,
    status: str,
    start_time: str,
    end_time: str,
    duration_ms: int,
    symbol: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> None:
    """记录完整的 trace 事件（单次写入）"""
    event = {
        "workflow_run_id": workflow_run_id,
        "trace_id": trace_id,
        "parent_trace_id": parent_trace_id,
        "type": trace_type,
        "name": name,
        "status": status,
        "start_time": start_time,
        "end_time": end_time,
        "duration_ms": duration_ms,
        "symbol": symbol,
        "payload": payload,
        "error": error,
    }
    append_event(event, cfg)


def record_trace_start(
    workflow_run_id: str,
    trace_id: str,
    parent_trace_id: Optional[str],
    trace_type: str,
    name: str,
    start_time: str,
    symbol: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> None:
    """记录 trace 开始事件（running 状态）"""
    event = {
        "workflow_run_id": workflow_run_id,
        "trace_id": trace_id,
        "parent_trace_id": parent_trace_id,
        "type": trace_type,
        "name": name,
        "status": "running",
        "start_time": start_time,
        "end_time": None,
        "duration_ms": None,
        "symbol": symbol,
        "payload": None,
        "error": None,
    }
    append_event(event, cfg)


def record_workflow_start(
    workflow_run_id: str,
    alert_record: Dict[str, Any],
    cfg: Optional[Dict[str, Any]] = None,
) -> None:
    """记录 workflow 开始"""
    start_time = now_iso()
    symbols = alert_record.get("symbols", [])
    pending_count = alert_record.get("pending_count", 0)
    
    with _workflow_counters_lock:
        _workflow_counters[workflow_run_id] = {
            "nodes_count": 0,
            "tool_calls_count": 0,
            "model_calls_count": 0,
            "artifacts_count": 0,
        }
    
    index_record = {
        "run_id": workflow_run_id,
        "start_time": start_time,
        "end_time": None,
        "duration_ms": None,
        "status": "running",
        "symbols": symbols,
        "pending_count": pending_count,
        "nodes_count": 0,
        "tool_calls_count": 0,
        "model_calls_count": 0,
        "artifacts_count": 0,
    }
    _append_to_index(index_record, cfg)
    
    event = {
        "workflow_run_id": workflow_run_id,
        "trace_id": workflow_run_id,
        "parent_trace_id": None,
        "type": "workflow",
        "name": "workflow",
        "status": "running",
        "start_time": start_time,
        "end_time": None,
        "duration_ms": None,
        "symbol": None,
        "payload": {
            "alert": {
                "ts": alert_record.get("ts"),
                "interval": alert_record.get("interval"),
                "symbols": symbols,
                "pending_count": pending_count,
            },
        },
        "error": None,
    }
    _append_to_workflow_trace(workflow_run_id, event, cfg)


def record_workflow_end(
    workflow_run_id: str,
    start_time: str,
    status: str,
    error: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> None:
    """记录 workflow 结束"""
    end_time = now_iso()
    duration_ms = calculate_duration_ms(start_time, end_time)
    
    counters = _get_counters(workflow_run_id)
    _clear_counters(workflow_run_id)
    
    index_record = {
        "run_id": workflow_run_id,
        "start_time": start_time,
        "end_time": end_time,
        "duration_ms": duration_ms,
        "status": status,
        "symbols": None,
        "pending_count": None,
        "nodes_count": counters.get("nodes_count", 0),
        "tool_calls_count": counters.get("tool_calls_count", 0),
        "model_calls_count": counters.get("model_calls_count", 0),
        "artifacts_count": counters.get("artifacts_count", 0),
        "error": error,
    }
    _append_to_index(index_record, cfg)
    
    event = {
        "workflow_run_id": workflow_run_id,
        "trace_id": workflow_run_id,
        "parent_trace_id": None,
        "type": "workflow",
        "name": "workflow",
        "status": status,
        "start_time": start_time,
        "end_time": end_time,
        "duration_ms": duration_ms,
        "symbol": None,
        "payload": None,
        "error": error,
    }
    _append_to_workflow_trace(workflow_run_id, event, cfg)


def save_image_artifact(
    workflow_run_id: str,
    parent_trace_id: str,
    symbol: str,
    interval: str,
    image_base64: str,
    image_id: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """保存图像 artifact
    
    Args:
        workflow_run_id: 顶层 workflow 的 run_id
        parent_trace_id: 父级 trace_id
        symbol: 交易对
        interval: K线周期
        image_base64: base64 编码的图像数据
        image_id: 图像唯一标识符，用于前端匹配（如 img_001）
        cfg: 配置
    """
    artifacts_dir = _get_artifacts_dir(cfg)
    os.makedirs(artifacts_dir, exist_ok=True)
    run_dir = os.path.join(artifacts_dir, workflow_run_id)
    os.makedirs(run_dir, exist_ok=True)
    
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{symbol}_{interval}_{ts}.png"
    file_path = os.path.join(run_dir, filename)
    
    with open(file_path, "wb") as f:
        f.write(base64.b64decode(image_base64))
    
    artifact_id = generate_trace_id("art")
    start_time = now_iso()
    
    artifact_payload = {
        "artifact_id": artifact_id,
        "symbol": symbol,
        "interval": interval,
        "file_path": file_path,
        "artifact_type": "kline_image",
        "image_id": image_id,
    }
    
    record_trace(
        workflow_run_id=workflow_run_id,
        trace_id=artifact_id,
        parent_trace_id=parent_trace_id,
        trace_type="artifact",
        name=f"{symbol}_{interval}",
        status="success",
        start_time=start_time,
        end_time=start_time,
        duration_ms=0,
        symbol=symbol,
        payload=artifact_payload,
        cfg=cfg,
    )
    
    _append_to_artifact_index({
        "artifact_id": artifact_id,
        "workflow_run_id": workflow_run_id,
        "file_path": file_path,
        "symbol": symbol,
        "interval": interval,
        "image_id": image_id,
    }, cfg)
    
    return {
        "artifact_id": artifact_id,
        "workflow_run_id": workflow_run_id,
        "parent_trace_id": parent_trace_id,
        "symbol": symbol,
        "interval": interval,
        "file_path": file_path,
        "image_id": image_id,
    }
