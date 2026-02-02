"""反向交易数据模型"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum


class AlgoOrderStatus(str, Enum):
    """条件单状态"""
    NEW = "NEW"
    TRIGGERED = "TRIGGERED"
    FILLED = "FILLED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class TradeRecordStatus(str, Enum):
    """开仓记录状态"""
    OPEN = "OPEN"
    TP_CLOSED = "TP_CLOSED"
    SL_CLOSED = "SL_CLOSED"
    MANUAL_CLOSED = "MANUAL_CLOSED"
    LIQUIDATED = "LIQUIDATED"


@dataclass
class ReverseAlgoOrder:
    """反向交易条件单"""
    algo_id: str
    symbol: str
    side: str
    trigger_price: float
    quantity: float
    status: AlgoOrderStatus
    
    tp_price: Optional[float] = None
    sl_price: Optional[float] = None
    leverage: int = 10
    margin_usdt: float = 50.0
    
    agent_order_id: Optional[str] = None
    agent_limit_price: Optional[float] = None
    agent_side: Optional[str] = None
    
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    expires_at: Optional[str] = None
    triggered_at: Optional[str] = None
    filled_at: Optional[str] = None
    filled_price: Optional[float] = None
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'algo_id': self.algo_id,
            'symbol': self.symbol,
            'side': self.side,
            'trigger_price': self.trigger_price,
            'quantity': self.quantity,
            'status': self.status.value if isinstance(self.status, AlgoOrderStatus) else self.status,
            'tp_price': self.tp_price,
            'sl_price': self.sl_price,
            'leverage': self.leverage,
            'margin_usdt': self.margin_usdt,
            'agent_order_id': self.agent_order_id,
            'agent_limit_price': self.agent_limit_price,
            'agent_side': self.agent_side,
            'created_at': self.created_at,
            'expires_at': self.expires_at,
            'triggered_at': self.triggered_at,
            'filled_at': self.filled_at,
            'filled_price': self.filled_price
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ReverseAlgoOrder':
        """从字典创建"""
        status = data.get('status', 'NEW')
        if isinstance(status, str):
            status = AlgoOrderStatus(status)
        
        return cls(
            algo_id=data['algo_id'],
            symbol=data['symbol'],
            side=data['side'],
            trigger_price=data['trigger_price'],
            quantity=data['quantity'],
            status=status,
            tp_price=data.get('tp_price'),
            sl_price=data.get('sl_price'),
            leverage=data.get('leverage', 10),
            margin_usdt=data.get('margin_usdt', 50.0),
            agent_order_id=data.get('agent_order_id'),
            agent_limit_price=data.get('agent_limit_price'),
            agent_side=data.get('agent_side'),
            created_at=data.get('created_at', datetime.now().isoformat()),
            expires_at=data.get('expires_at'),
            triggered_at=data.get('triggered_at'),
            filled_at=data.get('filled_at'),
            filled_price=data.get('filled_price')
        )


@dataclass
class ReversePosition:
    """反向交易持仓"""
    id: str
    symbol: str
    side: str
    qty: float
    entry_price: float
    leverage: int
    margin_usdt: float
    notional_usdt: float
    
    tp_price: Optional[float] = None
    sl_price: Optional[float] = None
    tp_order_id: Optional[int] = None
    sl_order_id: Optional[int] = None
    
    latest_mark_price: Optional[float] = None
    open_time: str = field(default_factory=lambda: datetime.now().isoformat())
    
    algo_order_id: Optional[str] = None
    agent_order_id: Optional[str] = None
    
    def unrealized_pnl(self, mark_price: Optional[float] = None) -> float:
        """计算未实现盈亏"""
        price = mark_price or self.latest_mark_price or self.entry_price
        if self.side == 'long':
            return (price - self.entry_price) * self.qty
        else:
            return (self.entry_price - price) * self.qty
    
    def roe(self, mark_price: Optional[float] = None) -> float:
        """计算收益率"""
        pnl = self.unrealized_pnl(mark_price)
        if self.margin_usdt > 0:
            return pnl / self.margin_usdt
        return 0.0
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'id': self.id,
            'symbol': self.symbol,
            'side': self.side,
            'qty': self.qty,
            'entry_price': self.entry_price,
            'leverage': self.leverage,
            'margin_usdt': self.margin_usdt,
            'notional_usdt': self.notional_usdt,
            'tp_price': self.tp_price,
            'sl_price': self.sl_price,
            'tp_order_id': self.tp_order_id,
            'sl_order_id': self.sl_order_id,
            'latest_mark_price': self.latest_mark_price,
            'open_time': self.open_time,
            'algo_order_id': self.algo_order_id,
            'agent_order_id': self.agent_order_id
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ReversePosition':
        """从字典创建"""
        return cls(
            id=data['id'],
            symbol=data['symbol'],
            side=data['side'],
            qty=data['qty'],
            entry_price=data['entry_price'],
            leverage=data['leverage'],
            margin_usdt=data['margin_usdt'],
            notional_usdt=data['notional_usdt'],
            tp_price=data.get('tp_price'),
            sl_price=data.get('sl_price'),
            tp_order_id=data.get('tp_order_id'),
            sl_order_id=data.get('sl_order_id'),
            latest_mark_price=data.get('latest_mark_price'),
            open_time=data.get('open_time', datetime.now().isoformat()),
            algo_order_id=data.get('algo_order_id'),
            agent_order_id=data.get('agent_order_id')
        )


@dataclass
class ReverseTradeHistory:
    """反向交易历史记录"""
    id: str
    symbol: str
    side: str
    qty: float
    entry_price: float
    exit_price: float
    leverage: int
    margin_usdt: float
    
    realized_pnl: float
    pnl_percent: float
    
    open_time: str
    close_time: str
    close_reason: str
    
    algo_order_id: Optional[str] = None
    agent_order_id: Optional[str] = None
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'id': self.id,
            'symbol': self.symbol,
            'side': self.side,
            'qty': self.qty,
            'entry_price': self.entry_price,
            'exit_price': self.exit_price,
            'leverage': self.leverage,
            'margin_usdt': self.margin_usdt,
            'realized_pnl': self.realized_pnl,
            'pnl_percent': self.pnl_percent,
            'open_time': self.open_time,
            'close_time': self.close_time,
            'close_reason': self.close_reason,
            'algo_order_id': self.algo_order_id,
            'agent_order_id': self.agent_order_id
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ReverseTradeHistory':
        """从字典创建"""
        return cls(
            id=data['id'],
            symbol=data['symbol'],
            side=data['side'],
            qty=data['qty'],
            entry_price=data['entry_price'],
            exit_price=data['exit_price'],
            leverage=data['leverage'],
            margin_usdt=data['margin_usdt'],
            realized_pnl=data['realized_pnl'],
            pnl_percent=data['pnl_percent'],
            open_time=data['open_time'],
            close_time=data['close_time'],
            close_reason=data['close_reason'],
            algo_order_id=data.get('algo_order_id'),
            agent_order_id=data.get('agent_order_id')
        )


@dataclass
class ReverseTradeRecord:
    """独立开仓记录
    
    每个条件单触发后创建一条独立记录，用于自主管理 TP/SL。
    不依赖 Binance 的持仓合并，每条记录有独立的 TP/SL 价格。
    """
    id: str
    symbol: str
    side: str
    qty: float
    entry_price: float
    tp_price: float
    sl_price: float
    leverage: int
    margin_usdt: float
    notional_usdt: float
    status: TradeRecordStatus
    
    algo_order_id: str
    agent_order_id: Optional[str] = None
    
    open_time: str = field(default_factory=lambda: datetime.now().isoformat())
    close_time: Optional[str] = None
    close_price: Optional[float] = None
    realized_pnl: Optional[float] = None
    close_reason: Optional[str] = None
    
    latest_mark_price: Optional[float] = None
    
    def unrealized_pnl(self, mark_price: Optional[float] = None) -> float:
        """计算未实现盈亏"""
        price = mark_price or self.latest_mark_price or self.entry_price
        if self.side.upper() in ('LONG', 'BUY'):
            return (price - self.entry_price) * self.qty
        else:
            return (self.entry_price - price) * self.qty
    
    def roe(self, mark_price: Optional[float] = None) -> float:
        """计算收益率"""
        pnl = self.unrealized_pnl(mark_price)
        if self.margin_usdt > 0:
            return pnl / self.margin_usdt
        return 0.0
    
    def is_tp_triggered(self, mark_price: float) -> bool:
        """检查是否触发止盈
        
        Args:
            mark_price: 当前标记价格
            
        Returns:
            是否触发止盈
        """
        if self.status != TradeRecordStatus.OPEN:
            return False
        
        if self.side.upper() in ('LONG', 'BUY'):
            return mark_price >= self.tp_price
        else:
            return mark_price <= self.tp_price
    
    def is_sl_triggered(self, mark_price: float) -> bool:
        """检查是否触发止损
        
        Args:
            mark_price: 当前标记价格
            
        Returns:
            是否触发止损
        """
        if self.status != TradeRecordStatus.OPEN:
            return False
        
        if self.side.upper() in ('LONG', 'BUY'):
            return mark_price <= self.sl_price
        else:
            return mark_price >= self.sl_price
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'id': self.id,
            'symbol': self.symbol,
            'side': self.side,
            'qty': self.qty,
            'entry_price': self.entry_price,
            'tp_price': self.tp_price,
            'sl_price': self.sl_price,
            'leverage': self.leverage,
            'margin_usdt': self.margin_usdt,
            'notional_usdt': self.notional_usdt,
            'status': self.status.value if isinstance(self.status, TradeRecordStatus) else self.status,
            'algo_order_id': self.algo_order_id,
            'agent_order_id': self.agent_order_id,
            'open_time': self.open_time,
            'close_time': self.close_time,
            'close_price': self.close_price,
            'realized_pnl': self.realized_pnl,
            'close_reason': self.close_reason,
            'latest_mark_price': self.latest_mark_price
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ReverseTradeRecord':
        """从字典创建"""
        status = data.get('status', 'OPEN')
        if isinstance(status, str):
            status = TradeRecordStatus(status)
        
        return cls(
            id=data['id'],
            symbol=data['symbol'],
            side=data['side'],
            qty=data['qty'],
            entry_price=data['entry_price'],
            tp_price=data['tp_price'],
            sl_price=data['sl_price'],
            leverage=data['leverage'],
            margin_usdt=data['margin_usdt'],
            notional_usdt=data['notional_usdt'],
            status=status,
            algo_order_id=data['algo_order_id'],
            agent_order_id=data.get('agent_order_id'),
            open_time=data.get('open_time', datetime.now().isoformat()),
            close_time=data.get('close_time'),
            close_price=data.get('close_price'),
            realized_pnl=data.get('realized_pnl'),
            close_reason=data.get('close_reason'),
            latest_mark_price=data.get('latest_mark_price')
        )
