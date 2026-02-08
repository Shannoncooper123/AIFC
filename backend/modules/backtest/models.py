"""回测模块数据模型"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class BacktestStatus(str, Enum):
    """回测状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BacktestConfig:
    """回测配置"""
    symbols: List[str]
    start_time: datetime
    end_time: datetime
    interval: str = "15m"
    initial_balance: float = 10000.0
    concurrency: int = 5
    workflow_timeout: int = 600
    fixed_margin_usdt: float = 50.0
    fixed_leverage: int = 10
    reverse_mode: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbols": self.symbols,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "interval": self.interval,
            "initial_balance": self.initial_balance,
            "concurrency": self.concurrency,
            "workflow_timeout": self.workflow_timeout,
            "fixed_margin_usdt": self.fixed_margin_usdt,
            "fixed_leverage": self.fixed_leverage,
            "reverse_mode": self.reverse_mode,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BacktestConfig":
        return cls(
            symbols=data["symbols"],
            start_time=datetime.fromisoformat(data["start_time"]),
            end_time=datetime.fromisoformat(data["end_time"]),
            interval=data.get("interval", "15m"),
            initial_balance=data.get("initial_balance", 10000.0),
            concurrency=data.get("concurrency", 5),
            workflow_timeout=data.get("workflow_timeout", 600),
            fixed_margin_usdt=data.get("fixed_margin_usdt", 50.0),
            fixed_leverage=data.get("fixed_leverage", 10),
            reverse_mode=data.get("reverse_mode", False),
        )


@dataclass
class BacktestProgress:
    """回测进度"""
    current_time: datetime
    total_steps: int
    completed_steps: int
    current_step_info: str = ""
    current_running: int = 0
    max_concurrency: int = 0
    
    @property
    def progress_percent(self) -> float:
        if self.total_steps == 0:
            return 0.0
        return (self.completed_steps / self.total_steps) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_time": self.current_time.isoformat(),
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "progress_percent": round(self.progress_percent, 2),
            "current_step_info": self.current_step_info,
            "current_running": self.current_running,
            "max_concurrency": self.max_concurrency,
        }


@dataclass
class BacktestTradeRecord:
    """回测交易记录"""
    symbol: str
    side: str
    entry_price: float
    exit_price: Optional[float]
    size: float
    entry_time: datetime
    exit_time: Optional[datetime]
    realized_pnl: Optional[float]
    status: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "size": self.size,
            "entry_time": self.entry_time.isoformat(),
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "realized_pnl": self.realized_pnl,
            "status": self.status,
        }


@dataclass
class CancelledLimitOrder:
    """未成交的限价单记录
    
    记录在回测期间创建但未能成交的限价单，用于分析挂单策略的有效性。
    """
    order_id: str
    symbol: str
    side: str
    limit_price: float
    tp_price: float
    sl_price: float
    margin_usdt: float
    leverage: int
    created_time: datetime
    cancelled_time: datetime
    cancel_reason: str
    workflow_run_id: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "limit_price": self.limit_price,
            "tp_price": self.tp_price,
            "sl_price": self.sl_price,
            "margin_usdt": round(self.margin_usdt, 4),
            "leverage": self.leverage,
            "created_time": self.created_time.isoformat(),
            "cancelled_time": self.cancelled_time.isoformat(),
            "cancel_reason": self.cancel_reason,
            "workflow_run_id": self.workflow_run_id,
        }


@dataclass
class BacktestTradeResult:
    """单次回测交易结果（独立执行）
    
    包含完整的交易详情：
    - 订单类型（市价单/限价单）
    - 开仓/平仓价格和时间
    - 原始设置的止盈止损价格
    - 保证金和杠杆信息
    - R值（风险回报比）
    - 手续费
    """
    trade_id: str
    kline_time: datetime
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    tp_price: float
    sl_price: float
    size: float
    exit_time: datetime
    exit_type: str
    realized_pnl: float
    pnl_percent: float
    holding_bars: int
    workflow_run_id: str
    
    order_type: str = "market"
    margin_usdt: float = 0.0
    leverage: int = 10
    notional_usdt: float = 0.0
    original_tp_price: Optional[float] = None  # 实际执行的止盈价（反向后）
    original_sl_price: Optional[float] = None  # 实际执行的止损价（反向后）
    agent_side: Optional[str] = None  # Agent 原始方向（反向前）
    agent_tp_price: Optional[float] = None  # Agent 原始止盈价（反向前）
    agent_sl_price: Optional[float] = None  # Agent 原始止损价（反向前）
    limit_price: Optional[float] = None
    fees_total: float = 0.0
    r_multiple: Optional[float] = None
    tp_distance_percent: float = 0.0
    sl_distance_percent: float = 0.0
    close_reason: str = ""
    order_created_time: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "kline_time": self.kline_time.isoformat(),
            "symbol": self.symbol,
            "side": self.side,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "tp_price": self.tp_price,
            "sl_price": self.sl_price,
            "size": self.size,
            "exit_time": self.exit_time.isoformat(),
            "exit_type": self.exit_type,
            "realized_pnl": round(self.realized_pnl, 4),
            "pnl_percent": round(self.pnl_percent, 4),
            "holding_bars": self.holding_bars,
            "workflow_run_id": self.workflow_run_id,
            "order_type": self.order_type,
            "margin_usdt": round(self.margin_usdt, 4),
            "leverage": self.leverage,
            "notional_usdt": round(self.notional_usdt, 4),
            "original_tp_price": self.original_tp_price,
            "original_sl_price": self.original_sl_price,
            "agent_side": self.agent_side,
            "agent_tp_price": self.agent_tp_price,
            "agent_sl_price": self.agent_sl_price,
            "limit_price": self.limit_price,
            "fees_total": round(self.fees_total, 6),
            "r_multiple": round(self.r_multiple, 2) if self.r_multiple is not None else None,
            "tp_distance_percent": round(self.tp_distance_percent, 2),
            "sl_distance_percent": round(self.sl_distance_percent, 2),
            "close_reason": self.close_reason,
            "order_created_time": self.order_created_time.isoformat() if self.order_created_time else None,
        }


@dataclass
class SideStats:
    """做多/做空方向统计"""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "total_pnl": round(self.total_pnl, 4),
            "win_rate": round(self.win_rate, 4),
            "avg_win": round(self.avg_win, 4),
            "avg_loss": round(self.avg_loss, 4),
        }


@dataclass
class BacktestResult:
    """回测结果"""
    backtest_id: str
    config: BacktestConfig
    status: BacktestStatus
    start_timestamp: datetime
    end_timestamp: Optional[datetime] = None
    
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    final_balance: float = 0.0
    
    avg_win: float = 0.0
    avg_loss: float = 0.0
    total_klines_analyzed: int = 0
    completed_batches: int = 0
    total_batches: int = 0
    
    long_stats: SideStats = field(default_factory=SideStats)
    short_stats: SideStats = field(default_factory=SideStats)
    
    trades: List[BacktestTradeResult] = field(default_factory=list)
    cancelled_orders: List[CancelledLimitOrder] = field(default_factory=list)
    workflow_runs: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    
    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades
    
    @property
    def profit_factor(self) -> float:
        if self.avg_loss == 0:
            return 0.0
        return abs(self.avg_win / self.avg_loss) if self.avg_loss != 0 else 0.0
    
    @property
    def return_rate(self) -> float:
        if self.config.initial_balance == 0:
            return 0.0
        return (self.final_balance - self.config.initial_balance) / self.config.initial_balance * 100
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "backtest_id": self.backtest_id,
            "config": self.config.to_dict(),
            "status": self.status.value,
            "start_timestamp": self.start_timestamp.isoformat(),
            "end_timestamp": self.end_timestamp.isoformat() if self.end_timestamp else None,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "total_pnl": round(self.total_pnl, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "final_balance": round(self.final_balance, 4),
            "win_rate": round(self.win_rate, 4),
            "profit_factor": round(self.profit_factor, 2),
            "avg_win": round(self.avg_win, 4),
            "avg_loss": round(self.avg_loss, 4),
            "return_rate": round(self.return_rate, 2),
            "total_klines_analyzed": self.total_klines_analyzed,
            "completed_batches": self.completed_batches,
            "total_batches": self.total_batches,
            "long_stats": self.long_stats.to_dict(),
            "short_stats": self.short_stats.to_dict(),
            "trades": [t.to_dict() for t in self.trades],
            "cancelled_orders": [o.to_dict() for o in self.cancelled_orders],
            "workflow_runs": self.workflow_runs,
            "error_message": self.error_message,
        }
