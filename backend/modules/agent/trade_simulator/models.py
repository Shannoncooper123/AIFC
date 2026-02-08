"""交易模拟模型定义（全仓保证金）"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional


@dataclass
class PendingOrder:
    """限价单/条件单模型
    
    order_kind 说明：
    - LIMIT: 限价单 (Maker)，价格需要回撤到触发价才成交
        - 做多: 当前价 > 触发价，等价格下跌到触发价
        - 做空: 当前价 < 触发价，等价格上涨到触发价
    - CONDITIONAL: 条件单 (Taker)，价格突破触发价时成交
        - 做多: 当前价 <= 触发价，等价格上涨到触发价
        - 做空: 当前价 >= 触发价，等价格下跌到触发价
    
    反向模式说明：
    - agent_side: Agent 原始方向（反向前）
    - agent_tp_price: Agent 原始止盈价（反向前）
    - agent_sl_price: Agent 原始止损价（反向前）
    """
    id: str
    symbol: str
    side: str  # "long" or "short"（实际执行方向，反向后）
    order_type: str = "limit"  # 保留兼容性
    order_kind: str = "LIMIT"  # "LIMIT" (Maker) 或 "CONDITIONAL" (Taker)
    limit_price: float = 0.0  # 挂单/触发价格
    margin_usdt: float = 0.0  # 保证金金额
    leverage: int = 10  # 杠杆倍数
    tp_price: Optional[float] = None  # 实际止盈价（反向后）
    sl_price: Optional[float] = None  # 实际止损价（反向后）
    agent_side: Optional[str] = None  # Agent 原始方向
    agent_tp_price: Optional[float] = None  # Agent 原始止盈价
    agent_sl_price: Optional[float] = None  # Agent 原始止损价
    create_time: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "pending"  # "pending", "filled", "cancelled"
    filled_time: Optional[str] = None
    filled_price: Optional[float] = None
    position_id: Optional[str] = None  # 成交后关联的持仓ID
    create_run_id: Optional[str] = None  # 创建限价单时的workflow run_id
    fill_run_id: Optional[str] = None  # 成交时的workflow run_id（异步触发时为None）


@dataclass
class Position:
    id: str
    symbol: str
    side: str  # "long" or "short"（实际执行方向）
    qty: float  # base quantity
    entry_price: float
    tp_price: Optional[float] = None  # 实际止盈价
    sl_price: Optional[float] = None  # 实际止损价
    original_sl_price: Optional[float] = None  # 开仓时的原始止损价（反向后），用于计算R值
    original_tp_price: Optional[float] = None  # 开仓时的原始止盈价（反向后）
    agent_side: Optional[str] = None  # Agent 原始方向（反向前）
    agent_tp_price: Optional[float] = None  # Agent 原始止盈价（反向前）
    agent_sl_price: Optional[float] = None  # Agent 原始止损价（反向前）
    operation_history: list = field(default_factory=list)  # 操作历史记录
    open_time: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "open"  # "open" or "closed"
    close_price: Optional[float] = None
    close_time: Optional[str] = None
    realized_pnl: float = 0.0
    fees_open: float = 0.0
    fees_close: float = 0.0
    leverage: int = 1
    notional_usdt: float = 0.0
    margin_used: float = 0.0
    latest_mark_price: Optional[float] = None
    close_reason: Optional[str] = None  # 平仓原因（Agent主动平仓/止盈/止损）
    open_run_id: Optional[str] = None  # 开仓时的workflow run_id
    close_run_id: Optional[str] = None  # 平仓时的workflow run_id（止盈止损自动触发时为None）

    def unrealized_pnl(self, mark_price: Optional[float] = None) -> float:
        mp = mark_price or self.latest_mark_price or self.entry_price
        if self.side == "long":
            return self.qty * (mp - self.entry_price)
        else:
            return self.qty * (self.entry_price - mp)

    def roe(self, mark_price: Optional[float] = None) -> float:
        mu = self.margin_used if self.margin_used > 0 else 1e-9
        return self.unrealized_pnl(mark_price) / mu


@dataclass
class Account:
    balance: float = 10000.0
    equity: float = 10000.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    reserved_margin_sum: float = 0.0
    positions_count: int = 0
    total_fees: float = 0.0  # 累计手续费

    def to_dict(self) -> Dict:
        return {
            "balance": round(self.balance, 6),
            "equity": round(self.equity, 6),
            "realized_pnl": round(self.realized_pnl, 6),
            "unrealized_pnl": round(self.unrealized_pnl, 6),
            "reserved_margin_sum": round(self.reserved_margin_sum, 6),
            "positions_count": int(self.positions_count),
            "total_fees": round(self.total_fees, 6),
        }
