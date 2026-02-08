"""服务层：业务逻辑实现

架构：
- PositionManager: 持仓管理（生命周期 + TP/SL + 数据）
- OrderManager: 挂单管理
- OrderExecutor: 订单执行（底层）
- PriceService: 价格获取
- TradeInfoService: 成交信息获取
- SyncService: 统一同步服务
- TradeService: 交易事件协调
- CommissionService: 手续费服务
"""

from modules.agent.live_engine.core import RecordStatus, TradeRecord
from modules.agent.live_engine.manager import (
    OrderExecutor,
    OrderManager,
    PositionManager,
    get_close_side,
    get_position_side,
)

from .account_service import AccountService
from .commission_service import CommissionService
from .price_service import PriceService
from .sync_service import SyncService
from .trade_info_service import EntryInfo, ExitInfo, TradeInfoService, TradeSummary
from .trade_service import TradeService

__all__ = [
    'PriceService',
    'OrderExecutor',
    'PositionManager',
    'OrderManager',
    'TradeInfoService',
    'TradeSummary',
    'EntryInfo',
    'ExitInfo',
    'SyncService',
    'AccountService',
    'get_position_side',
    'get_close_side',
    'CommissionService',
    'TradeRecord',
    'RecordStatus',
    'TradeService',
]
