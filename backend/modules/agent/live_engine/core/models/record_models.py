"""交易记录数据模型

统一的开仓记录模型，供 live_engine 和 reverse_engine 共用。
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class RecordStatus(str, Enum):
    """记录状态"""
    OPEN = 'OPEN'
    TP_CLOSED = 'TP_CLOSED'
    SL_CLOSED = 'SL_CLOSED'
    MANUAL_CLOSED = 'MANUAL_CLOSED'
    LIQUIDATED = 'LIQUIDATED'
    POSITION_CLOSED_EXTERNALLY = 'POSITION_CLOSED_EXTERNALLY'


@dataclass
class TradeRecord:
    """独立开仓记录

    每条记录代表一次独立的开仓操作，有独立的 TP/SL 订单。
    支持 live_engine 和 reverse_engine 两种来源。

    Attributes:
        id: 唯一标识
        symbol: 交易对
        side: 方向（BUY/SELL 或 LONG/SHORT）
        qty: 数量
        entry_price: 入场价格
        tp_price: 止盈价格
        sl_price: 止损价格
        leverage: 杠杆倍数
        margin_usdt: 保证金（USDT）
        status: 记录状态
        source: 来源（live/reverse）
    """
    id: str
    symbol: str
    side: str
    qty: float
    entry_price: float

    tp_price: Optional[float] = None
    sl_price: Optional[float] = None
    leverage: int = 10
    margin_usdt: float = 0.0
    notional_usdt: float = 0.0
    status: RecordStatus = RecordStatus.OPEN

    source: str = 'live'

    entry_order_id: Optional[int] = None
    entry_algo_id: Optional[str] = None
    tp_order_id: Optional[int] = None
    tp_algo_id: Optional[str] = None
    sl_order_id: Optional[int] = None
    sl_algo_id: Optional[str] = None

    open_time: str = field(default_factory=lambda: datetime.now().isoformat())
    close_time: Optional[str] = None
    close_price: Optional[float] = None
    close_reason: Optional[str] = None

    entry_commission: float = 0.0
    exit_commission: float = 0.0
    total_commission: float = 0.0
    realized_pnl: Optional[float] = None

    latest_mark_price: Optional[float] = None

    agent_order_id: Optional[str] = None
    extra_data: Dict[str, Any] = field(default_factory=dict)

    def unrealized_pnl(self, mark_price: Optional[float] = None) -> float:
        """计算未实现盈亏"""
        price = mark_price or self.latest_mark_price or self.entry_price
        if self.side.upper() in ('LONG', 'BUY'):
            return (price - self.entry_price) * self.qty
        else:
            return (self.entry_price - price) * self.qty

    def roe(self, mark_price: Optional[float] = None) -> float:
        """计算 ROE (Return on Equity)"""
        pnl = self.unrealized_pnl(mark_price)
        if self.margin_usdt > 0:
            return pnl / self.margin_usdt
        return 0.0

    def is_tp_triggered(self, mark_price: float) -> bool:
        """检查是否触发止盈"""
        if self.status != RecordStatus.OPEN or not self.tp_price:
            return False

        if self.side.upper() in ('LONG', 'BUY'):
            return mark_price >= self.tp_price
        else:
            return mark_price <= self.tp_price

    def is_sl_triggered(self, mark_price: float) -> bool:
        """检查是否触发止损"""
        if self.status != RecordStatus.OPEN or not self.sl_price:
            return False

        if self.side.upper() in ('LONG', 'BUY'):
            return mark_price <= self.sl_price
        else:
            return mark_price >= self.sl_price

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['status'] = self.status.value if isinstance(self.status, RecordStatus) else self.status
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TradeRecord':
        """从字典创建"""
        status = data.get('status', 'OPEN')
        if isinstance(status, str):
            status = RecordStatus(status)

        return cls(
            id=data['id'],
            symbol=data['symbol'],
            side=data['side'],
            qty=data['qty'],
            entry_price=data['entry_price'],
            tp_price=data.get('tp_price'),
            sl_price=data.get('sl_price'),
            leverage=data.get('leverage', 10),
            margin_usdt=data.get('margin_usdt', 0.0),
            notional_usdt=data.get('notional_usdt', 0.0),
            status=status,
            source=data.get('source', 'live'),
            entry_order_id=data.get('entry_order_id'),
            entry_algo_id=data.get('entry_algo_id') or data.get('algo_order_id'),
            tp_order_id=data.get('tp_order_id'),
            tp_algo_id=data.get('tp_algo_id'),
            sl_order_id=data.get('sl_order_id'),
            sl_algo_id=data.get('sl_algo_id'),
            open_time=data.get('open_time', datetime.now().isoformat()),
            close_time=data.get('close_time'),
            close_price=data.get('close_price'),
            close_reason=data.get('close_reason'),
            entry_commission=data.get('entry_commission', 0.0),
            exit_commission=data.get('exit_commission', 0.0),
            total_commission=data.get('total_commission', 0.0),
            realized_pnl=data.get('realized_pnl'),
            latest_mark_price=data.get('latest_mark_price'),
            agent_order_id=data.get('agent_order_id'),
            extra_data=data.get('extra_data', {}),
        )

    @property
    def is_open(self) -> bool:
        """记录是否处于开仓状态"""
        return self.status == RecordStatus.OPEN

    @property
    def is_closed(self) -> bool:
        """记录是否已关闭"""
        return self.status != RecordStatus.OPEN
