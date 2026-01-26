"""API 请求/响应模型"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ServiceName(str, Enum):
    """服务名称枚举"""
    MONITOR = "monitor"
    AGENT = "agent"
    WORKFLOW = "workflow"


class ServiceStatus(str, Enum):
    """服务状态枚举"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class ServiceInfo(BaseModel):
    """服务信息"""
    name: str
    status: ServiceStatus = ServiceStatus.STOPPED
    thread_id: Optional[int] = None
    started_at: Optional[str] = None
    error: Optional[str] = None


class SystemStatusResponse(BaseModel):
    """系统状态响应"""
    status: str = "ok"
    services: Dict[str, ServiceInfo]
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


class ServiceActionRequest(BaseModel):
    """服务操作请求"""
    action: str = Field(..., pattern="^(start|stop|restart)$")


class ServiceActionResponse(BaseModel):
    """服务操作响应"""
    success: bool
    message: str
    service: ServiceInfo


class LogsResponse(BaseModel):
    """日志响应"""
    service: str
    lines: List[str]
    total: int


class AlertEntry(BaseModel):
    """告警条目"""
    symbol: str
    price: float
    price_change_rate: float
    triggered_indicators: List[str]
    engulfing_type: Optional[str] = None
    timestamp: Optional[str] = None


class AlertRecord(BaseModel):
    """告警记录"""
    ts: str
    interval: str
    entries: List[AlertEntry]


class AlertsResponse(BaseModel):
    """告警列表响应"""
    alerts: List[AlertRecord]
    total: int


class PositionSide(str, Enum):
    """持仓方向"""
    LONG = "long"
    SHORT = "short"


class Position(BaseModel):
    """持仓信息 - 字段名与前端 types/positions.ts 对齐"""
    symbol: str
    side: str
    size: float = Field(description="持仓数量")
    entry_price: float
    mark_price: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    leverage: int = 1
    margin: Optional[float] = Field(default=None, description="已用保证金")
    liquidation_price: Optional[float] = None
    take_profit: Optional[float] = Field(default=None, description="止盈价格")
    stop_loss: Optional[float] = Field(default=None, description="止损价格")
    opened_at: Optional[str] = Field(default=None, description="开仓时间")
    open_run_id: Optional[str] = None


class PositionsResponse(BaseModel):
    """持仓列表响应"""
    positions: List[Position]
    total: int
    pending_orders: List[Dict[str, Any]] = Field(default_factory=list)


class PositionHistoryEntry(BaseModel):
    """历史持仓条目 - 字段名与前端 types/positions.ts 对齐"""
    symbol: str
    side: str
    size: float = Field(description="持仓数量")
    entry_price: float
    exit_price: float = Field(description="平仓价格")
    realized_pnl: float
    pnl_percent: float
    opened_at: str = Field(description="开仓时间")
    closed_at: str = Field(description="平仓时间")
    close_reason: Optional[str] = None
    open_run_id: Optional[str] = None
    close_run_id: Optional[str] = None


class PositionHistoryResponse(BaseModel):
    """历史持仓响应"""
    positions: List[PositionHistoryEntry]
    total: int
    total_pnl: float


class AccountSummary(BaseModel):
    """账户摘要"""
    total_balance: float
    available_balance: float
    unrealized_pnl: float
    margin_used: float
    margin_ratio: Optional[float] = None


class TradeStateResponse(BaseModel):
    """交易状态响应"""
    account: AccountSummary
    positions: List[Position]
    pending_orders: List[Dict[str, Any]]


class ConfigSection(BaseModel):
    """配置节"""
    name: str
    data: Dict[str, Any]


class ConfigResponse(BaseModel):
    """配置响应"""
    sections: List[ConfigSection]


class ConfigUpdateRequest(BaseModel):
    """配置更新请求"""
    section: str
    data: Dict[str, Any]


class ConfigUpdateResponse(BaseModel):
    """配置更新响应"""
    success: bool
    message: str


class ErrorResponse(BaseModel):
    """错误响应"""
    error: str
    detail: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


class WorkflowRunSummary(BaseModel):
    """Workflow 运行摘要"""
    run_id: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_ms: Optional[int] = None
    status: Optional[str] = None
    symbols: List[str] = Field(default_factory=list)
    pending_count: int = 0
    nodes_count: int = 0
    tool_calls_count: int = 0
    model_calls_count: int = 0
    artifacts_count: int = 0


class WorkflowRunEvent(BaseModel):
    """Workflow 事件（原始格式，兼容旧接口）"""
    type: str
    run_id: str
    ts: str
    seq: Optional[int] = None
    timestamp_ms: Optional[int] = None
    span_id: Optional[str] = None
    parent_span_id: Optional[str] = None
    node: Optional[str] = None
    phase: Optional[str] = None
    symbol: Optional[str] = None
    tool_name: Optional[str] = None
    duration_ms: Optional[int] = None
    payload: Optional[Dict[str, Any]] = None
    status: Optional[str] = None
    error: Optional[str] = None
    output_summary: Optional[Dict[str, Any]] = None


class WorkflowTraceItem(BaseModel):
    """
    Workflow Trace 项（新的层级化结构）
    
    type 字段标识类型：
    - node: LangGraph 节点
    - agent: Agent 调用
    - model_call: 模型调用
    - tool_call: 工具调用
    - artifact: 图片等产物
    """
    trace_id: str
    parent_trace_id: Optional[str] = None
    type: str
    name: str
    symbol: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_ms: Optional[int] = None
    status: Optional[str] = None
    error: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    children: List["WorkflowTraceItem"] = Field(default_factory=list)
    artifacts: List["WorkflowArtifact"] = Field(default_factory=list)


class WorkflowTimeline(BaseModel):
    """Workflow 时间线（树形结构）"""
    run_id: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_ms: Optional[int] = None
    status: Optional[str] = None
    symbols: List[str] = Field(default_factory=list)
    traces: List[WorkflowTraceItem] = Field(default_factory=list)


class WorkflowSpanChild(BaseModel):
    """Span 子事件（兼容旧接口）"""
    type: str
    ts: str
    seq: int
    tool_name: Optional[str] = None
    symbol: Optional[str] = None
    duration_ms: Optional[int] = None
    status: Optional[str] = None
    error: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None


class WorkflowSpan(BaseModel):
    """Workflow Span（兼容旧接口）"""
    span_id: str
    parent_span_id: Optional[str] = None
    node: str
    symbol: Optional[str] = None
    start_time: str
    end_time: Optional[str] = None
    duration_ms: Optional[int] = None
    status: str = "running"
    error: Optional[str] = None
    output_summary: Optional[Dict[str, Any]] = None
    children: List[WorkflowSpanChild] = Field(default_factory=list)
    artifacts: List["WorkflowArtifact"] = Field(default_factory=list)
    nested_spans: List["WorkflowSpan"] = Field(default_factory=list)


class WorkflowRunsResponse(BaseModel):
    """Workflow 运行列表响应"""
    runs: List[WorkflowRunSummary]
    total: int


class WorkflowRunDetailResponse(BaseModel):
    """Workflow 运行详情响应（兼容旧接口）"""
    run_id: str
    events: List[WorkflowRunEvent]


class WorkflowTimelineResponse(BaseModel):
    """Workflow 时间线响应（新接口）"""
    timeline: WorkflowTimeline


class WorkflowArtifact(BaseModel):
    """Workflow Artifact"""
    artifact_id: str
    run_id: str
    type: str
    file_path: str
    trace_id: Optional[str] = None
    parent_trace_id: Optional[str] = None
    span_id: Optional[str] = None
    symbol: Optional[str] = None
    interval: Optional[str] = None
    image_id: Optional[str] = None
    created_at: Optional[str] = None


WorkflowTraceItem.model_rebuild()
WorkflowSpan.model_rebuild()
