"""
Workflow Trace 存储模块

提供 trace 事件的记录和存储功能。

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
import base64
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


def _get_trace_path(cfg: Optional[Dict[str, Any]] = None) -> str:
    """获取 trace 文件路径"""
    if cfg is None:
        cfg = get_config()
    agent_cfg = cfg.get("agent", {})
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    trace_path = agent_cfg.get("workflow_trace_path", "logs/workflow_runs.jsonl")
    if not os.path.isabs(trace_path):
        trace_path = os.path.join(base_dir, trace_path)
    return trace_path


def _get_artifacts_dir(cfg: Optional[Dict[str, Any]] = None) -> str:
    """获取 artifacts 目录路径"""
    if cfg is None:
        cfg = get_config()
    agent_cfg = cfg.get("agent", {})
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    artifacts_dir = agent_cfg.get("workflow_artifacts_dir", "logs/workflow_artifacts")
    if not os.path.isabs(artifacts_dir):
        artifacts_dir = os.path.join(base_dir, artifacts_dir)
    return artifacts_dir


def get_trace_path(cfg: Optional[Dict[str, Any]] = None) -> str:
    """公开的获取 trace 文件路径接口"""
    return _get_trace_path(cfg)


def get_artifacts_dir(cfg: Optional[Dict[str, Any]] = None) -> str:
    """公开的获取 artifacts 目录路径接口"""
    return _get_artifacts_dir(cfg)


def append_event(event: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None) -> None:
    """追加 trace 事件到 JSONL 文件"""
    try:
        event["timestamp_ms"] = int(time.time() * 1000)
        trace_path = _get_trace_path(cfg)
        locked_append_jsonl(trace_path, event)
    except Exception as e:
        logger.error(f"workflow trace 写入失败: {e}")


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
    event = {
        "workflow_run_id": workflow_run_id,
        "trace_id": workflow_run_id,
        "parent_trace_id": None,
        "type": "workflow",
        "name": "workflow",
        "status": "running",
        "start_time": now_iso(),
        "end_time": None,
        "duration_ms": None,
        "symbol": None,
        "payload": {
            "alert": {
                "ts": alert_record.get("ts"),
                "interval": alert_record.get("interval"),
                "symbols": alert_record.get("symbols", []),
                "pending_count": alert_record.get("pending_count", 0),
            },
        },
        "error": None,
    }
    append_event(event, cfg)


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
    
    record_trace(
        workflow_run_id=workflow_run_id,
        trace_id=workflow_run_id,
        parent_trace_id=None,
        trace_type="workflow",
        name="workflow",
        status=status,
        start_time=start_time,
        end_time=end_time,
        duration_ms=duration_ms,
        error=error,
        cfg=cfg,
    )


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
    
    return {
        "artifact_id": artifact_id,
        "workflow_run_id": workflow_run_id,
        "parent_trace_id": parent_trace_id,
        "symbol": symbol,
        "interval": interval,
        "file_path": file_path,
        "image_id": image_id,
    }
