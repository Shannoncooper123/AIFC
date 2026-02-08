"""持仓管理器

统一管理持仓的完整生命周期：
- 数据存储（内部 Repository）
- 业务操作（开仓、平仓、TP/SL）
- 查询统计（汇总、历史、统计）

单一数据源原则：所有持仓数据都由本地管理，不依赖交易所。

架构：
- position_manager.py: 入口类，属性和代理方法
- position_operations.py: 开仓、平仓、记录管理
- tpsl_operations.py: TP/SL 订单管理
- position_query.py: 查询和统计
"""
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from modules.agent.live_engine.core import RecordRepository, RecordStatus, TradeRecord
from modules.monitor.utils.logger import get_logger

if TYPE_CHECKING:
    from modules.agent.live_engine.core.repositories import LinkedOrderRepository
    from modules.agent.live_engine.manager.order import OrderExecutor
    from modules.agent.live_engine.services.commission_service import CommissionService
    from modules.agent.live_engine.services.price_service import PriceService
    from modules.agent.live_engine.services.trade_info_service import TradeInfoService
    from modules.monitor.clients.binance_rest import BinanceRestClient

logger = get_logger('live_engine.position_manager')


class PositionManager:
    """持仓管理器

    统一管理持仓的完整生命周期（开仓 → 更新 TP/SL → 平仓）和数据存储。
    是所有持仓数据的唯一入口。
    """

    def __init__(
        self,
        order_executor: 'OrderExecutor',
        price_service: 'PriceService',
        trade_info_service: 'TradeInfoService',
        rest_client: 'BinanceRestClient',
        config: Dict = None,
        repository: Optional[RecordRepository] = None,
        linked_order_repo: 'LinkedOrderRepository' = None,
        commission_service: 'CommissionService' = None
    ):
        self.order_executor = order_executor
        self.price_service = price_service
        self.trade_info_service = trade_info_service
        self.rest_client = rest_client
        self.config = config or {}
        self.linked_order_repo = linked_order_repo
        self.commission_service = commission_service

        self._repository = repository or RecordRepository()
        self.tpsl_orders: Dict[str, Dict[str, Optional[int]]] = {}

        from modules.agent.live_engine.manager.position.tpsl_operations import restore_from_state
        restore_from_state(self)

    @property
    def records(self) -> Dict[str, TradeRecord]:
        return {r.id: r for r in self._repository.get_all()}

    def get_record(self, record_id: str) -> Optional[TradeRecord]:
        return self._repository.get(record_id)

    def get_open_records(self, source: Optional[str] = None) -> List[TradeRecord]:
        return self._repository.get_open_records(source)

    def get_open_records_by_symbol(self, symbol: str, source: Optional[str] = None) -> List[TradeRecord]:
        records = self._repository.find_by_symbol(symbol, source)
        return [r for r in records if r.status == RecordStatus.OPEN]

    def find_record_by_tp_order_id(self, tp_order_id: int) -> Optional[TradeRecord]:
        return self._repository.find_by_tp_order_id(tp_order_id)

    def find_record_by_tp_algo_id(self, tp_algo_id: str) -> Optional[TradeRecord]:
        return self._repository.find_by_tp_algo_id(tp_algo_id)

    def find_record_by_sl_algo_id(self, sl_algo_id: str) -> Optional[TradeRecord]:
        return self._repository.find_by_sl_algo_id(sl_algo_id)

    def update_mark_price(self, symbol: str, mark_price: float):
        self._repository.update_mark_price(symbol, mark_price)

    def fetch_entry_info(self, symbol: str, order_id: int) -> Dict[str, Any]:
        from modules.agent.live_engine.manager.position.position_operations import fetch_entry_info
        return fetch_entry_info(self, symbol, order_id)

    def open_position(
        self, symbol: str, side: str, quote_notional_usdt: float, leverage: int,
        tp_price: Optional[float] = None, sl_price: Optional[float] = None, source: str = 'live'
    ) -> Dict[str, Any]:
        from modules.agent.live_engine.manager.position.position_operations import open_position
        return open_position(self, symbol, side, quote_notional_usdt, leverage, tp_price, sl_price, source)

    def close_position(
        self, position_id: Optional[str] = None, symbol: Optional[str] = None, close_reason: Optional[str] = None
    ) -> Dict[str, Any]:
        from modules.agent.live_engine.manager.position.position_operations import close_position
        return close_position(self, position_id, symbol, close_reason)

    def close_record(self, record_id: str, source: Optional[str] = None) -> bool:
        from modules.agent.live_engine.manager.position.position_operations import close_single_record
        return close_single_record(self, record_id, source)

    def close_all_by_symbol(self, symbol: str, source: Optional[str] = None) -> int:
        from modules.agent.live_engine.manager.position.position_operations import close_all_by_symbol
        return close_all_by_symbol(self, symbol, source)

    def _create_record(
        self, symbol: str, side: str, qty: float, entry_price: float,
        leverage: int = 10, tp_price: Optional[float] = None, sl_price: Optional[float] = None,
        source: str = 'live', entry_order_id: Optional[int] = None, entry_algo_id: Optional[str] = None,
        agent_order_id: Optional[str] = None, entry_commission: float = 0.0,
        auto_place_tpsl: bool = True, extra_data: Optional[Dict] = None
    ) -> 'TradeRecord':
        from modules.agent.live_engine.manager.position.position_operations import create_record
        return create_record(
            self, symbol=symbol, side=side, qty=qty, entry_price=entry_price,
            leverage=leverage, tp_price=tp_price, sl_price=sl_price, source=source,
            entry_order_id=entry_order_id, entry_algo_id=entry_algo_id,
            agent_order_id=agent_order_id, entry_commission=entry_commission,
            auto_place_tpsl=auto_place_tpsl, extra_data=extra_data
        )

    def _close_record(
        self, record_id: str, close_price: float, close_reason: str,
        exit_commission: float = 0.0, realized_pnl: Optional[float] = None
    ) -> Optional['TradeRecord']:
        from modules.agent.live_engine.manager.position.position_operations import close_record
        return close_record(
            self, record_id=record_id, close_price=close_price,
            close_reason=close_reason, exit_commission=exit_commission, realized_pnl=realized_pnl
        )

    def _cancel_remaining_tpsl(self, record: 'TradeRecord', triggered_type: Optional[str]):
        from modules.agent.live_engine.manager.position.position_operations import _cancel_remaining_tpsl
        return _cancel_remaining_tpsl(self, record, triggered_type)

    def update_tp_sl(self, symbol: str, tp_price: Optional[float] = None, sl_price: Optional[float] = None) -> Dict[str, Any]:
        from modules.agent.live_engine.manager.position.tpsl_operations import update_tp_sl
        return update_tp_sl(self, symbol, tp_price, sl_price)

    def place_tp_sl_for_position(
        self, symbol: str, side: str, quantity: float,
        tp_price: Optional[float] = None, sl_price: Optional[float] = None, use_limit_for_tp: bool = True
    ) -> Dict[str, Any]:
        from modules.agent.live_engine.manager.position.tpsl_operations import place_tp_sl_for_position
        return place_tp_sl_for_position(self, symbol, side, quantity, tp_price, sl_price, use_limit_for_tp)

    def cancel_tpsl_orders(self, symbol: str):
        from modules.agent.live_engine.manager.position.tpsl_operations import cancel_tpsl_orders
        return cancel_tpsl_orders(self, symbol)

    def sync_tpsl_orders(self):
        from modules.agent.live_engine.manager.position.tpsl_operations import sync_tpsl_orders
        return sync_tpsl_orders(self)

    def cleanup_orphan_orders(self, active_symbols: Set[str]) -> int:
        from modules.agent.live_engine.manager.position.tpsl_operations import cleanup_orphan_orders
        return cleanup_orphan_orders(self, active_symbols)

    def get_tpsl_prices(self, symbol: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        from modules.agent.live_engine.manager.position.tpsl_operations import get_tpsl_prices
        return get_tpsl_prices(self, symbol)

    def update_local_tracking(self, symbol: str, tp_order_id: int = None, sl_order_id: int = None):
        from modules.agent.live_engine.manager.position.tpsl_operations import update_local_tracking
        return update_local_tracking(self, symbol, tp_order_id, sl_order_id)

    def clear_local_tracking(self, symbol: str):
        from modules.agent.live_engine.manager.position.tpsl_operations import clear_local_tracking
        return clear_local_tracking(self, symbol)

    def handle_order_cancelled(self, symbol: str, order_id: int):
        from modules.agent.live_engine.manager.position.tpsl_operations import handle_order_cancelled
        return handle_order_cancelled(self, symbol, order_id)

    def clear_tpsl_ids(self, record_id: str):
        from modules.agent.live_engine.manager.position.tpsl_operations import clear_tpsl_ids
        return clear_tpsl_ids(self, record_id)

    def get_summary(self, source: Optional[str] = None) -> List[Dict[str, Any]]:
        from modules.agent.live_engine.manager.position.position_query import get_summary
        return get_summary(self, source)

    def get_statistics(self, source: Optional[str] = None) -> Dict[str, Any]:
        from modules.agent.live_engine.manager.position.position_query import get_statistics
        return get_statistics(self, source)

    def get_history(self, source: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        from modules.agent.live_engine.manager.position.position_query import get_history
        return get_history(self, source, limit)

    def get_open_symbols(self, source: Optional[str] = None) -> Set[str]:
        from modules.agent.live_engine.manager.position.position_query import get_open_symbols
        return get_open_symbols(self, source)

    def get_pending_orders_summary(self, order_repository, source: Optional[str] = None) -> Dict[str, Any]:
        from modules.agent.live_engine.manager.position.position_query import get_pending_orders_summary
        return get_pending_orders_summary(self, order_repository, source)
