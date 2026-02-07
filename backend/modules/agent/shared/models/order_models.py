"""订单相关数据模型

统一的订单模型，供 live_engine 和 reverse_engine 共用。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum


class AlgoOrderStatus(str, Enum):
    """条件单/策略单状态"""
    NEW = "NEW"
    TRIGGERED = "TRIGGERED"
    FILLED = "FILLED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class OrderKind(str, Enum):
    """订单类型：限价单或条件单"""
    LIMIT_ORDER = "LIMIT"
    CONDITIONAL_ORDER = "CONDITIONAL"


@dataclass
class PendingOrder:
    """待触发的入场订单（条件单或限价单）
    
    统一模型，支持两种订单类型：
    - CONDITIONAL: 条件单，使用 algo_id 跟踪
    - LIMIT: 限价单，使用 order_id 跟踪
    
    Attributes:
        id: 唯一标识（algo_id 或 LIMIT_{order_id}）
        symbol: 交易对
        side: 方向（BUY/SELL 或 long/short）
        trigger_price: 触发价格
        quantity: 数量
        status: 订单状态
        order_kind: 订单类型（LIMIT 或 CONDITIONAL）
        tp_price: 计划止盈价
        sl_price: 计划止损价
        leverage: 杠杆倍数
        margin_usdt: 保证金（USDT）
        order_id: Binance 限价单 ID（限价单类型）
        algo_id: Binance 条件单 ID（条件单类型）
        source: 来源（live/reverse）
        agent_order_id: 关联的 Agent 订单 ID
    """
    id: str
    symbol: str
    side: str
    trigger_price: float
    quantity: float
    status: AlgoOrderStatus
    
    order_kind: OrderKind = OrderKind.CONDITIONAL_ORDER
    
    tp_price: Optional[float] = None
    sl_price: Optional[float] = None
    leverage: int = 10
    margin_usdt: float = 50.0
    
    order_id: Optional[int] = None
    algo_id: Optional[str] = None
    
    source: str = 'live'
    agent_order_id: Optional[str] = None
    agent_limit_price: Optional[float] = None
    agent_side: Optional[str] = None
    
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    expires_at: Optional[str] = None
    triggered_at: Optional[str] = None
    filled_at: Optional[str] = None
    filled_price: Optional[float] = None
    
    extra_data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'symbol': self.symbol,
            'side': self.side,
            'trigger_price': self.trigger_price,
            'quantity': self.quantity,
            'status': self.status.value if isinstance(self.status, AlgoOrderStatus) else self.status,
            'order_kind': self.order_kind.value if isinstance(self.order_kind, OrderKind) else self.order_kind,
            'tp_price': self.tp_price,
            'sl_price': self.sl_price,
            'leverage': self.leverage,
            'margin_usdt': self.margin_usdt,
            'order_id': self.order_id,
            'algo_id': self.algo_id,
            'source': self.source,
            'agent_order_id': self.agent_order_id,
            'agent_limit_price': self.agent_limit_price,
            'agent_side': self.agent_side,
            'created_at': self.created_at,
            'expires_at': self.expires_at,
            'triggered_at': self.triggered_at,
            'filled_at': self.filled_at,
            'filled_price': self.filled_price,
            'extra_data': self.extra_data,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PendingOrder':
        """从字典创建"""
        status = data.get('status', 'NEW')
        if isinstance(status, str):
            status = AlgoOrderStatus(status)
        
        order_kind = data.get('order_kind', 'CONDITIONAL')
        if isinstance(order_kind, str):
            try:
                order_kind = OrderKind(order_kind)
            except ValueError:
                order_kind = OrderKind.CONDITIONAL_ORDER
        
        return cls(
            id=data['id'],
            symbol=data['symbol'],
            side=data['side'],
            trigger_price=data['trigger_price'],
            quantity=data['quantity'],
            status=status,
            order_kind=order_kind,
            tp_price=data.get('tp_price'),
            sl_price=data.get('sl_price'),
            leverage=data.get('leverage', 10),
            margin_usdt=data.get('margin_usdt', 50.0),
            order_id=data.get('order_id') or data.get('binance_order_id'),
            algo_id=data.get('algo_id'),
            source=data.get('source', 'live'),
            agent_order_id=data.get('agent_order_id'),
            agent_limit_price=data.get('agent_limit_price'),
            agent_side=data.get('agent_side'),
            created_at=data.get('created_at', datetime.now().isoformat()),
            expires_at=data.get('expires_at'),
            triggered_at=data.get('triggered_at'),
            filled_at=data.get('filled_at'),
            filled_price=data.get('filled_price'),
            extra_data=data.get('extra_data', {}),
        )
    
    @property
    def is_limit_order(self) -> bool:
        """是否为限价单"""
        return self.order_kind == OrderKind.LIMIT_ORDER
    
    @property
    def is_conditional_order(self) -> bool:
        """是否为条件单"""
        return self.order_kind == OrderKind.CONDITIONAL_ORDER
