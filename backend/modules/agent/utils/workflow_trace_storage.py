import base64
import contextvars
import json
import os
import time
import random
import string
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from modules.agent.trade_simulator.utils.file_utils import locked_append_jsonl
from modules.config.settings import get_config
from modules.monitor.utils.logger import get_logger

logger = get_logger("agent.workflow_trace")

_current_run_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("workflow_run_id", default=None)
_current_span_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("workflow_span_id", default=None)
_current_symbol: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("workflow_symbol", default=None)
_sequence_counter: contextvars.ContextVar[int] = contextvars.ContextVar("workflow_sequence", default=0)
_span_start_times: contextvars.ContextVar[Dict[str, float]] = contextvars.ContextVar("span_start_times", default={})


def generate_run_id() -> str:
    """生成唯一的 run_id"""
    now = datetime.now(timezone.utc)
    timestamp_part = now.strftime("%Y%m%d_%H%M%S")
    random_suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"run_{timestamp_part}_{random_suffix}"


def generate_span_id() -> str:
    """生成唯一的 span_id"""
    random_suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"span_{random_suffix}"


def set_current_run_id(run_id: Optional[str]) -> None:
    _current_run_id.set(run_id)
    _sequence_counter.set(0)


def get_current_run_id() -> Optional[str]:
    return _current_run_id.get()


def set_current_span_id(span_id: Optional[str]) -> None:
    _current_span_id.set(span_id)


def get_current_span_id() -> Optional[str]:
    return _current_span_id.get()


def set_current_symbol(symbol: Optional[str]) -> None:
    _current_symbol.set(symbol)


def get_current_symbol() -> Optional[str]:
    return _current_symbol.get()


def _next_sequence() -> int:
    """获取下一个序列号"""
    current = _sequence_counter.get()
    _sequence_counter.set(current + 1)
    return current


def _get_trace_path(cfg: Optional[Dict[str, Any]] = None) -> str:
    if cfg is None:
        cfg = get_config()
    agent_cfg = cfg.get("agent", {})
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    trace_path = agent_cfg.get("workflow_trace_path", "logs/workflow_runs.jsonl")
    if not os.path.isabs(trace_path):
        trace_path = os.path.join(base_dir, trace_path)
    return trace_path


def _get_artifacts_dir(cfg: Optional[Dict[str, Any]] = None) -> str:
    if cfg is None:
        cfg = get_config()
    agent_cfg = cfg.get("agent", {})
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    artifacts_dir = agent_cfg.get("workflow_artifacts_dir", "logs/workflow_artifacts")
    if not os.path.isabs(artifacts_dir):
        artifacts_dir = os.path.join(base_dir, artifacts_dir)
    return artifacts_dir


def get_trace_path(cfg: Optional[Dict[str, Any]] = None) -> str:
    return _get_trace_path(cfg)


def get_artifacts_dir(cfg: Optional[Dict[str, Any]] = None) -> str:
    return _get_artifacts_dir(cfg)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_timestamp_ms() -> int:
    """返回当前时间戳（毫秒）"""
    return int(time.time() * 1000)


def _sanitize_payload(payload: Dict[str, Any], text_limit: int = 0) -> Dict[str, Any]:
    """直接返回 payload，不做任何截断"""
    return payload


def append_event(event: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None) -> None:
    try:
        event["seq"] = _next_sequence()
        event["timestamp_ms"] = _now_timestamp_ms()
        trace_path = _get_trace_path(cfg)
        locked_append_jsonl(trace_path, event)
    except Exception as e:
        logger.error(f"workflow trace 写入失败: {e}")


def start_run(run_id: str, alert_record: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None) -> None:
    """记录 workflow run 开始"""
    set_current_run_id(run_id)
    event = {
        "type": "run_start",
        "run_id": run_id,
        "ts": _now_iso(),
        "alert": {
            "ts": alert_record.get("ts"),
            "interval": alert_record.get("interval"),
            "symbols": alert_record.get("symbols", []),
            "pending_count": alert_record.get("pending_count", 0),
        },
    }
    append_event(event, cfg)


def end_run(run_id: str, status: str, cfg: Optional[Dict[str, Any]] = None, error: Optional[str] = None) -> None:
    """记录 workflow run 结束"""
    event = {
        "type": "run_end",
        "run_id": run_id,
        "ts": _now_iso(),
        "status": status,
        "error": error,
    }
    append_event(event, cfg)


def start_span(
    run_id: str,
    node: str,
    span_id: Optional[str] = None,
    parent_span_id: Optional[str] = None,
    symbol: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None
) -> str:
    """开始一个 span（节点执行）"""
    if span_id is None:
        span_id = generate_span_id()
    
    set_current_span_id(span_id)
    if symbol:
        set_current_symbol(symbol)
    
    start_times = _span_start_times.get()
    start_times[span_id] = _now_timestamp_ms()
    _span_start_times.set(start_times)
    
    event = {
        "type": "span_start",
        "run_id": run_id,
        "span_id": span_id,
        "parent_span_id": parent_span_id,
        "node": node,
        "symbol": symbol or get_current_symbol(),
        "ts": _now_iso(),
    }
    append_event(event, cfg)
    return span_id


def end_span(
    run_id: str,
    span_id: str,
    status: str = "success",
    output_summary: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None
) -> None:
    """结束一个 span"""
    start_times = _span_start_times.get()
    start_time = start_times.pop(span_id, None)
    _span_start_times.set(start_times)
    
    duration_ms = None
    if start_time:
        duration_ms = _now_timestamp_ms() - start_time
    
    event = {
        "type": "span_end",
        "run_id": run_id,
        "span_id": span_id,
        "status": status,
        "duration_ms": duration_ms,
        "ts": _now_iso(),
        "output_summary": output_summary,
        "error": error,
    }
    append_event(event, cfg)


def record_node_event(
    run_id: str,
    node: str,
    phase: str,
    payload: Dict[str, Any],
    symbol: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None
) -> None:
    """记录节点事件（兼容旧接口）"""
    event = {
        "type": "node_event",
        "run_id": run_id,
        "span_id": get_current_span_id(),
        "node": node,
        "phase": phase,
        "symbol": symbol or get_current_symbol(),
        "ts": _now_iso(),
        "payload": _sanitize_payload(payload, 2000),
    }
    append_event(event, cfg)


def record_context_snapshot(run_id: str, snapshot: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None) -> None:
    """记录上下文快照"""
    event = {
        "type": "context_snapshot",
        "run_id": run_id,
        "span_id": get_current_span_id(),
        "ts": _now_iso(),
        "payload": _sanitize_payload(snapshot, 2000),
    }
    append_event(event, cfg)


def record_tool_call(
    run_id: str,
    node: str,
    tool_record: Dict[str, Any],
    symbol: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None
) -> None:
    """记录工具调用"""
    tool_name = tool_record.get("tool_name", "unknown")
    tool_input = tool_record.get("input", {})
    model_span_id = tool_record.get("model_span_id")
    
    inferred_symbol = symbol or get_current_symbol()
    if not inferred_symbol and isinstance(tool_input, dict):
        inferred_symbol = tool_input.get("symbol")
    
    event = {
        "type": "tool_call",
        "run_id": run_id,
        "span_id": get_current_span_id(),
        "model_span_id": model_span_id,
        "node": node,
        "symbol": inferred_symbol,
        "tool_name": tool_name,
        "ts": _now_iso(),
        "payload": _sanitize_payload(tool_record, 2000),
    }
    append_event(event, cfg)


def record_model_call(
    run_id: str,
    node: str,
    model_record: Dict[str, Any],
    symbol: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None
) -> None:
    """记录模型调用"""
    event = {
        "type": "model_call",
        "run_id": run_id,
        "span_id": get_current_span_id(),
        "node": node,
        "symbol": symbol or get_current_symbol(),
        "ts": _now_iso(),
        "payload": _sanitize_payload(model_record, 2000),
    }
    append_event(event, cfg)


def save_image_artifact(
    run_id: str,
    symbol: str,
    interval: str,
    image_base64: str,
    cfg: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """保存图像 artifact"""
    artifacts_dir = _get_artifacts_dir(cfg)
    os.makedirs(artifacts_dir, exist_ok=True)
    run_dir = os.path.join(artifacts_dir, run_id)
    os.makedirs(run_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{symbol}_{interval}_{ts}.png"
    file_path = os.path.join(run_dir, filename)
    with open(file_path, "wb") as f:
        f.write(base64.b64decode(image_base64))
    artifact_id = f"{run_id}_{symbol}_{interval}_{ts}"
    artifact = {
        "artifact_id": artifact_id,
        "run_id": run_id,
        "span_id": get_current_span_id(),
        "symbol": symbol,
        "interval": interval,
        "file_path": file_path,
        "created_at": _now_iso(),
        "type": "kline_image",
    }
    append_event({"type": "artifact", "run_id": run_id, "ts": _now_iso(), "payload": artifact}, cfg)
    return artifact
