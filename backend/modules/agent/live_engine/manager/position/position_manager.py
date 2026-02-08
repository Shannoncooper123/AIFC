"""持仓管理器

统一管理持仓的完整生命周期：
- 数据存储（内部 Repository）
- 业务操作（开仓、平仓、TP/SL）
- 查询统计（汇总、历史、统计）

单一数据源原则：所有持仓数据都由本地管理，不依赖交易所。
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
        """初始化

        Args:
            order_executor: 订单执行器
            price_service: 价格服务
            trade_info_service: 成交信息服务
            rest_client: Binance REST 客户端
            config: 配置字典
            repository: 记录仓库（可选）
            linked_order_repo: 关联订单仓库（可选）
            commission_service: 手续费服务（可选）
        """
        self.order_executor = order_executor
        self.price_service = price_service
        self.trade_info_service = trade_info_service
        self.rest_client = rest_client
        self.config = config or {}
        self.linked_order_repo = linked_order_repo
        self.commission_service = commission_service

        self._repository = repository or RecordRepository()
        self.tpsl_orders: Dict[str, Dict[str, Optional[int]]] = {}

        self._restore_from_state()

    @property
    def records(self) -> Dict[str, TradeRecord]:
        """获取所有记录的字典"""
        return {r.id: r for r in self._repository.get_all()}

    def get_record(self, record_id: str) -> Optional[TradeRecord]:
        """获取记录"""
        return self._repository.get(record_id)

    def get_open_records(self, source: Optional[str] = None) -> List[TradeRecord]:
        """获取开仓中的记录"""
        return self._repository.get_open_records(source)

    def get_open_records_by_symbol(self, symbol: str, source: Optional[str] = None) -> List[TradeRecord]:
        """获取指定交易对的开仓记录"""
        records = self._repository.find_by_symbol(symbol, source)
        return [r for r in records if r.status == RecordStatus.OPEN]

    def find_record_by_tp_order_id(self, tp_order_id: int) -> Optional[TradeRecord]:
        """根据止盈订单ID查找记录"""
        return self._repository.find_by_tp_order_id(tp_order_id)

    def find_record_by_tp_algo_id(self, tp_algo_id: str) -> Optional[TradeRecord]:
        """根据止盈策略单ID查找记录"""
        return self._repository.find_by_tp_algo_id(tp_algo_id)

    def find_record_by_sl_algo_id(self, sl_algo_id: str) -> Optional[TradeRecord]:
        """根据止损策略单ID查找记录"""
        return self._repository.find_by_sl_algo_id(sl_algo_id)

    def update_mark_price(self, symbol: str, mark_price: float):
        """更新标记价格"""
        self._repository.update_mark_price(symbol, mark_price)

    def open_position(
        self,
        symbol: str,
        side: str,
        quote_notional_usdt: float,
        leverage: int,
        tp_price: Optional[float] = None,
        sl_price: Optional[float] = None,
        source: str = 'live'
    ) -> Dict[str, Any]:
        """市价开仓"""
        from modules.agent.live_engine.manager.position.position_operations import open_position
        return open_position(self, symbol, side, quote_notional_usdt, leverage, tp_price, sl_price, source)

    def close_position(
        self,
        position_id: Optional[str] = None,
        symbol: Optional[str] = None,
        close_reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """市价平仓"""
        from modules.agent.live_engine.manager.position.position_operations import close_position
        return close_position(self, position_id, symbol, close_reason)

    def close_record(self, record_id: str, source: Optional[str] = None) -> bool:
        """关闭指定的交易记录"""
        from modules.agent.live_engine.manager.position.position_operations import close_single_record
        return close_single_record(self, record_id, source)

    def close_all_by_symbol(self, symbol: str, source: Optional[str] = None) -> int:
        """关闭指定交易对的所有开仓记录"""
        from modules.agent.live_engine.manager.position.position_operations import close_all_by_symbol
        return close_all_by_symbol(self, symbol, source)

    def update_tp_sl(
        self,
        symbol: str,
        tp_price: Optional[float] = None,
        sl_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """更新止盈止损价格"""
        from modules.agent.live_engine.manager.position.tpsl_operations import update_tp_sl
        return update_tp_sl(self, symbol, tp_price, sl_price)

    def place_tp_sl_for_position(
        self,
        symbol: str,
        side: str,
        quantity: float,
        tp_price: Optional[float] = None,
        sl_price: Optional[float] = None,
        use_limit_for_tp: bool = True
    ) -> Dict[str, Any]:
        """为持仓下止盈止损单"""
        from modules.agent.live_engine.manager.position.tpsl_operations import place_tp_sl_for_position
        return place_tp_sl_for_position(self, symbol, side, quantity, tp_price, sl_price, use_limit_for_tp)

    def cancel_tpsl_orders(self, symbol: str):
        """撤销指定币种的 TP/SL 订单"""
        from modules.agent.live_engine.manager.position.tpsl_operations import cancel_tpsl_orders
        return cancel_tpsl_orders(self, symbol)

    def sync_tpsl_orders(self):
        """同步 TP/SL 订单状态"""
        from modules.agent.live_engine.manager.position.tpsl_operations import sync_tpsl_orders
        return sync_tpsl_orders(self)

    def cleanup_orphan_orders(self, active_symbols: Set[str]) -> int:
        """清理孤儿订单"""
        from modules.agent.live_engine.manager.position.tpsl_operations import cleanup_orphan_orders
        return cleanup_orphan_orders(self, active_symbols)

    def get_tpsl_prices(self, symbol: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """查询当前挂单中的 TP/SL 价格和订单 ID"""
        from modules.agent.live_engine.manager.position.tpsl_operations import get_tpsl_prices
        return get_tpsl_prices(self, symbol)

    def update_local_tracking(self, symbol: str, tp_order_id: int = None, sl_order_id: int = None):
        """更新本地跟踪记录"""
        from modules.agent.live_engine.manager.position.tpsl_operations import update_local_tracking
        return update_local_tracking(self, symbol, tp_order_id, sl_order_id)

    def clear_local_tracking(self, symbol: str):
        """清除本地跟踪记录"""
        from modules.agent.live_engine.manager.position.tpsl_operations import clear_local_tracking
        return clear_local_tracking(self, symbol)

    def handle_order_cancelled(self, symbol: str, order_id: int):
        """处理订单取消事件"""
        from modules.agent.live_engine.manager.position.tpsl_operations import handle_order_cancelled
        return handle_order_cancelled(self, symbol, order_id)

    def get_summary(self, source: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取开仓记录汇总"""
        from modules.agent.live_engine.manager.position.position_query import get_summary
        return get_summary(self, source)

    def get_statistics(self, source: Optional[str] = None) -> Dict[str, Any]:
        """获取统计信息"""
        from modules.agent.live_engine.manager.position.position_query import get_statistics
        return get_statistics(self, source)

    def get_history(self, source: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """获取已关闭的交易记录历史"""
        from modules.agent.live_engine.manager.position.position_query import get_history
        return get_history(self, source, limit)

    def get_open_symbols(self, source: Optional[str] = None) -> Set[str]:
        """获取当前持仓的交易对集合"""
        from modules.agent.live_engine.manager.position.position_query import get_open_symbols
        return get_open_symbols(self, source)

    def get_pending_orders_summary(self, order_repository, source: Optional[str] = None) -> Dict[str, Any]:
        """获取待处理订单汇总"""
        from modules.agent.live_engine.manager.position.position_query import get_pending_orders_summary
        return get_pending_orders_summary(self, order_repository, source)

    def _restore_from_state(self):
        """从 trade_state.json 恢复订单 ID 记录"""
        try:
            import json
            import os

            state_path = self.config.get('agent', {}).get('trade_state_path', 'agent/trade_state.json')
            if not os.path.exists(state_path):
                return

            with open(state_path, 'r', encoding='utf-8') as f:
                state_data = json.load(f)

            positions = state_data.get('positions', {})
            restored_count = 0

            for symbol, pos_data in positions.items():
                tp_id = pos_data.get('tp_order_id')
                sl_id = pos_data.get('sl_order_id')

                if tp_id or sl_id:
                    self.tpsl_orders[symbol] = {
                        'tp_order_id': tp_id,
                        'sl_order_id': sl_id
                    }
                    restored_count += 1
                    logger.info(f"恢复订单 ID 记录: {symbol} tp={tp_id}, sl={sl_id}")

            if restored_count > 0:
                logger.info(f"✓ 从 trade_state.json 恢复了 {restored_count} 个币种的订单 ID 记录")

        except Exception as e:
            logger.warning(f"从 trade_state.json 恢复订单 ID 失败: {e}")
