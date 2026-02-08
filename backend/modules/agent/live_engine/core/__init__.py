"""Agent 共享模块

提供 live_engine 和 reverse_engine 共用的工具类和基础设施。

模块结构：
- models/: 统一数据模型（TradeRecord, PendingOrder, Order, Trade）
- repositories/: 数据访问层（RecordRepository, OrderRepository, LinkedOrderRepository）
- persistence/: 持久化工具（JsonStateManager）
- exchange_utils.py: 交易所工具（ExchangeInfoCache）
"""

from .exchange_utils import ExchangeInfoCache
from .models import (
    AlgoOrderStatus,
    Order,
    OrderKind,
    OrderPurpose,
    OrderStatus,
    OrderType,
    PendingOrder,
    Position,
    RecordStatus,
    Trade,
    TradeRecord,
)
from .persistence import JsonStateManager
from .repositories import (
    LinkedOrderRepository,
    OrderRepository,
    RecordRepository,
)

__all__ = [
    'ExchangeInfoCache',
    'JsonStateManager',
    'AlgoOrderStatus',
    'OrderKind',
    'PendingOrder',
    'Position',
    'RecordStatus',
    'TradeRecord',
    'RecordRepository',
    'OrderRepository',
    'LinkedOrderRepository',
    'Order',
    'Trade',
    'OrderType',
    'OrderPurpose',
    'OrderStatus',
]
