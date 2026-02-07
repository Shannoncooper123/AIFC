"""Agent 共享模块

提供 live_engine 和 reverse_engine 共用的工具类和基础设施。

模块结构：
- models/: 统一数据模型（TradeRecord, PendingOrder）
- repositories/: 数据访问层（RecordRepository, OrderRepository）
- persistence/: 持久化工具（JsonStateManager）
- exchange_utils.py: 交易所工具（ExchangeInfoCache）
"""

from .exchange_utils import ExchangeInfoCache
from .persistence import JsonStateManager

from .models import (
    AlgoOrderStatus,
    OrderKind,
    PendingOrder,
    RecordStatus,
    TradeRecord,
)

from .repositories import (
    RecordRepository,
    OrderRepository,
)

__all__ = [
    'ExchangeInfoCache',
    'JsonStateManager',
    'AlgoOrderStatus',
    'OrderKind',
    'PendingOrder',
    'RecordStatus',
    'TradeRecord',
    'RecordRepository',
    'OrderRepository',
]
