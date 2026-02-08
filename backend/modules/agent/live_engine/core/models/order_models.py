"""订单相关数据模型

统一的订单模型，供 live_engine 和 reverse_engine 共用。

数据层次结构:
- TradeRecord (持仓) → 关联多个 Order (订单)
- Order (订单) → 关联多个 Trade (成交)
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class AlgoOrderStatus(str, Enum):
    """条件单/策略单状态（用于 PendingOrder）"""
    NEW = "NEW"
    TRIGGERED = "TRIGGERED"
    FILLED = "FILLED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class OrderKind(str, Enum):
    """订单类型：限价单或条件单（用于 PendingOrder）"""
    LIMIT_ORDER = "LIMIT"
    CONDITIONAL_ORDER = "CONDITIONAL"


class OrderType(str, Enum):
    """Binance 订单类型"""
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    STOP = "STOP"
    STOP_MARKET = "STOP_MARKET"
    TAKE_PROFIT = "TAKE_PROFIT"
    TAKE_PROFIT_MARKET = "TAKE_PROFIT_MARKET"
    TRAILING_STOP_MARKET = "TRAILING_STOP_MARKET"


class OrderPurpose(str, Enum):
    """订单用途"""
    ENTRY = "ENTRY"
    TAKE_PROFIT = "TAKE_PROFIT"
    STOP_LOSS = "STOP_LOSS"
    CLOSE = "CLOSE"


class OrderStatus(str, Enum):
    """订单状态"""
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    TRIGGERED = "TRIGGERED"
    REJECTED = "REJECTED"


@dataclass
class Trade:
    """成交记录模型 - 关联到 Order

    每笔成交都有独立的记录，包含价格、数量、手续费等信息。
    多笔成交聚合到 Order 上。
    """
    id: str
    order_id: str
    binance_trade_id: int
    symbol: str

    price: float
    qty: float
    quote_qty: float

    commission: float
    commission_asset: str
    realized_pnl: float

    side: str
    is_maker: bool
    timestamp: int

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'order_id': self.order_id,
            'binance_trade_id': self.binance_trade_id,
            'symbol': self.symbol,
            'price': self.price,
            'qty': self.qty,
            'quote_qty': self.quote_qty,
            'commission': self.commission,
            'commission_asset': self.commission_asset,
            'realized_pnl': self.realized_pnl,
            'side': self.side,
            'is_maker': self.is_maker,
            'timestamp': self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Trade':
        """从字典创建"""
        return cls(
            id=data['id'],
            order_id=data['order_id'],
            binance_trade_id=data['binance_trade_id'],
            symbol=data['symbol'],
            price=float(data['price']),
            qty=float(data['qty']),
            quote_qty=float(data.get('quote_qty', 0)),
            commission=float(data['commission']),
            commission_asset=data.get('commission_asset', 'USDT'),
            realized_pnl=float(data.get('realized_pnl', 0)),
            side=data['side'],
            is_maker=data.get('is_maker', False),
            timestamp=int(data['timestamp']),
        )

    @classmethod
    def from_binance(cls, data: Dict[str, Any], order_id: str, local_id: str) -> 'Trade':
        """从 Binance API 响应创建

        Args:
            data: Binance userTrades API 返回的成交数据
            order_id: 关联的本地 Order ID
            local_id: 本地生成的唯一 ID
        """
        return cls(
            id=local_id,
            order_id=order_id,
            binance_trade_id=int(data['id']),
            symbol=data['symbol'],
            price=float(data['price']),
            qty=float(data['qty']),
            quote_qty=float(data.get('quoteQty', 0)),
            commission=float(data['commission']),
            commission_asset=data.get('commissionAsset', 'USDT'),
            realized_pnl=float(data.get('realizedPnl', 0)),
            side=data['side'],
            is_maker=data.get('maker', False),
            timestamp=int(data['time']),
        )


@dataclass
class Order:
    """订单模型 - 关联到 TradeRecord

    每个订单可以有多笔成交 (Trade)，手续费从成交聚合到订单。
    订单关联到持仓 (TradeRecord)，订单手续费聚合到持仓。

    Attributes:
        id: 本地唯一标识
        record_id: 关联的 TradeRecord ID
        symbol: 交易对
        binance_order_id: Binance 普通订单 ID
        binance_algo_id: Binance 条件单 ID
        order_type: 订单类型 (LIMIT/MARKET/STOP_MARKET 等)
        purpose: 订单用途 (ENTRY/TAKE_PROFIT/STOP_LOSS/CLOSE)
        status: 订单状态
        side: 方向 (BUY/SELL)
        position_side: 持仓方向 (LONG/SHORT/BOTH)
        price: 委托价格
        stop_price: 触发价格（条件单）
        quantity: 委托数量
        filled_qty: 已成交数量
        avg_filled_price: 平均成交价格
        commission: 聚合的总手续费
        realized_pnl: 聚合的已实现盈亏
        reduce_only: 是否只减仓
        created_at: 创建时间
        updated_at: 更新时间
        trades: 关联的成交记录列表
    """
    id: str
    record_id: Optional[str]
    symbol: str

    binance_order_id: Optional[int] = None
    binance_algo_id: Optional[str] = None

    order_type: OrderType = OrderType.MARKET
    purpose: OrderPurpose = OrderPurpose.ENTRY
    status: OrderStatus = OrderStatus.NEW

    side: str = "BUY"
    position_side: str = "LONG"

    price: float = 0.0
    stop_price: float = 0.0
    quantity: float = 0.0
    filled_qty: float = 0.0
    avg_filled_price: float = 0.0

    commission: float = 0.0
    realized_pnl: float = 0.0

    reduce_only: bool = False

    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    trades: List[Trade] = field(default_factory=list)
    extra_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'record_id': self.record_id,
            'symbol': self.symbol,
            'binance_order_id': self.binance_order_id,
            'binance_algo_id': self.binance_algo_id,
            'order_type': self.order_type.value if isinstance(self.order_type, OrderType) else self.order_type,
            'purpose': self.purpose.value if isinstance(self.purpose, OrderPurpose) else self.purpose,
            'status': self.status.value if isinstance(self.status, OrderStatus) else self.status,
            'side': self.side,
            'position_side': self.position_side,
            'price': self.price,
            'stop_price': self.stop_price,
            'quantity': self.quantity,
            'filled_qty': self.filled_qty,
            'avg_filled_price': self.avg_filled_price,
            'commission': self.commission,
            'realized_pnl': self.realized_pnl,
            'reduce_only': self.reduce_only,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'trades': [t.to_dict() for t in self.trades],
            'extra_data': self.extra_data,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Order':
        """从字典创建"""
        order_type = data.get('order_type', 'MARKET')
        if isinstance(order_type, str):
            try:
                order_type = OrderType(order_type)
            except ValueError:
                order_type = OrderType.MARKET

        purpose = data.get('purpose', 'ENTRY')
        if isinstance(purpose, str):
            try:
                purpose = OrderPurpose(purpose)
            except ValueError:
                purpose = OrderPurpose.ENTRY

        status = data.get('status', 'NEW')
        if isinstance(status, str):
            try:
                status = OrderStatus(status)
            except ValueError:
                status = OrderStatus.NEW

        trades_data = data.get('trades', [])
        trades = [Trade.from_dict(t) for t in trades_data]

        return cls(
            id=data['id'],
            record_id=data.get('record_id'),
            symbol=data['symbol'],
            binance_order_id=data.get('binance_order_id'),
            binance_algo_id=data.get('binance_algo_id'),
            order_type=order_type,
            purpose=purpose,
            status=status,
            side=data.get('side', 'BUY'),
            position_side=data.get('position_side', 'LONG'),
            price=float(data.get('price', 0)),
            stop_price=float(data.get('stop_price', 0)),
            quantity=float(data.get('quantity', 0)),
            filled_qty=float(data.get('filled_qty', 0)),
            avg_filled_price=float(data.get('avg_filled_price', 0)),
            commission=float(data.get('commission', 0)),
            realized_pnl=float(data.get('realized_pnl', 0)),
            reduce_only=data.get('reduce_only', False),
            created_at=data.get('created_at', datetime.now().isoformat()),
            updated_at=data.get('updated_at', datetime.now().isoformat()),
            trades=trades,
            extra_data=data.get('extra_data', {}),
        )

    @property
    def is_limit_order(self) -> bool:
        """是否为限价单"""
        return self.order_type == OrderType.LIMIT

    @property
    def is_algo_order(self) -> bool:
        """是否为条件单"""
        return self.order_type in (
            OrderType.STOP,
            OrderType.STOP_MARKET,
            OrderType.TAKE_PROFIT,
            OrderType.TAKE_PROFIT_MARKET,
            OrderType.TRAILING_STOP_MARKET,
        )

    @property
    def is_filled(self) -> bool:
        """是否已完全成交"""
        return self.status == OrderStatus.FILLED

    @property
    def is_open(self) -> bool:
        """是否为挂单状态"""
        return self.status in (OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED)

    def aggregate_trades(self):
        """从成交记录聚合手续费和盈亏"""
        if not self.trades:
            return

        total_commission = sum(t.commission for t in self.trades)
        total_pnl = sum(t.realized_pnl for t in self.trades)
        total_qty = sum(t.qty for t in self.trades)
        total_value = sum(t.price * t.qty for t in self.trades)

        self.commission = total_commission
        self.realized_pnl = total_pnl
        self.filled_qty = total_qty
        if total_qty > 0:
            self.avg_filled_price = total_value / total_qty


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
