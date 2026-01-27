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
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbols": self.symbols,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "interval": self.interval,
            "initial_balance": self.initial_balance,
            "concurrency": self.concurrency,
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
        )


@dataclass
class BacktestProgress:
    """回测进度"""
    current_time: datetime
    total_steps: int
    completed_steps: int
    current_step_info: str = ""
    
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
class BacktestTradeResult:
    """单次回测交易结果（独立执行）"""
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
    
    trades: List[BacktestTradeResult] = field(default_factory=list)
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
            "trades": [t.to_dict() for t in self.trades],
            "workflow_runs": self.workflow_runs,
            "error_message": self.error_message,
        }
