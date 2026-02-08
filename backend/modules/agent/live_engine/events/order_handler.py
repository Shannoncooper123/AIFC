"""ORDER_TRADE_UPDATE 事件处理器

处理 Binance 普通订单的状态变化事件。

职责：
- 解析 ORDER_TRADE_UPDATE 事件
- 委托 TradeService 处理业务逻辑
"""
from typing import TYPE_CHECKING, Any, Dict

from modules.agent.live_engine.core.models import OrderPurpose, OrderType
from modules.agent.live_engine.services.trade_service import OrderEvent
from modules.monitor.utils.logger import get_logger

if TYPE_CHECKING:
    from modules.agent.live_engine.core.repositories import OrderRepository
    from modules.agent.live_engine.services.trade_service import TradeService

logger = get_logger('live_engine.order_handler')


class OrderUpdateHandler:
    """ORDER_TRADE_UPDATE 事件处理器

    职责：
    - 解析 ORDER_TRADE_UPDATE 事件
    - 根据订单类型委托 TradeService 处理
    """

    def __init__(
        self,
        trade_service: 'TradeService',
        order_repository: 'OrderRepository' = None
    ):
        """初始化

        Args:
            trade_service: 交易服务（处理业务逻辑）
            order_repository: 订单仓库（查找 pending orders）
        """
        self.trade_service = trade_service
        self.order_repository = order_repository

    def handle(self, data: Dict[str, Any]):
        """处理 ORDER_TRADE_UPDATE 事件

        Args:
            data: 订单更新事件数据
        """
        try:
            order_data = data.get('o', {})
            symbol = order_data.get('s')
            order_status = order_data.get('X')
            order_type = order_data.get('o')
            orig_type = order_data.get('ot')
            order_id = int(order_data.get('i', 0))

            event = OrderEvent(
                symbol=symbol,
                order_id=order_id,
                status=order_status,
                side=order_data.get('S', ''),
                order_type=order_type or orig_type or '',
                avg_price=float(order_data.get('ap', 0) or 0),
                filled_qty=float(order_data.get('z', 0) or 0)
            )

            if order_status == 'FILLED':
                self._handle_order_filled(event, order_data)

            tpsl_types = [
                OrderType.TAKE_PROFIT_MARKET.value,
                OrderType.STOP_MARKET.value,
                OrderType.TAKE_PROFIT.value,
                OrderType.STOP.value,
            ]
            is_tpsl_order = order_type in tpsl_types or orig_type in tpsl_types

            if is_tpsl_order and order_status == 'CANCELED':
                self._handle_tpsl_cancelled(symbol, order_id)

        except Exception as e:
            logger.error(f"处理订单更新事件失败: {e}", exc_info=True)

    def _handle_order_filled(self, event: OrderEvent, order_data: Dict):
        """处理订单成交事件"""
        order_id = event.order_id

        if self.trade_service.linked_order_repo:
            linked_order = self.trade_service.linked_order_repo.get_order_by_binance_id(order_id)
            if linked_order:
                self._handle_linked_order(linked_order, event)
                return

        if self.order_repository:
            pending_order = self.order_repository.find_by_order_id(order_id)
            if pending_order and pending_order.order_kind == 'LIMIT':
                self.trade_service.on_entry_limit_order_filled(event, pending_order)
                return

        record = self.trade_service.position_manager.find_record_by_tp_order_id(order_id)
        if record:
            logger.info(f"[OrderHandler] 🎯 止盈限价单成交: {event.symbol} orderId={order_id}")
            self.trade_service.on_tp_triggered(event, record)
            return

    def _handle_linked_order(self, linked_order, event: OrderEvent):
        """处理 LinkedOrderRepository 中的订单成交"""
        purpose = linked_order.purpose

        logger.info(f"[OrderHandler] 🎯 订单成交 (LinkedOrder): {event.symbol} "
                   f"orderId={event.order_id} purpose={purpose.value}")

        if purpose == OrderPurpose.TAKE_PROFIT:
            self.trade_service.on_linked_order_filled(linked_order, event)
        elif purpose == OrderPurpose.STOP_LOSS:
            self.trade_service.on_linked_order_filled(linked_order, event)
        elif purpose == OrderPurpose.CLOSE:
            self.trade_service.on_linked_order_filled(linked_order, event)

    def _handle_tpsl_cancelled(self, symbol: str, order_id: int):
        """处理 TP/SL 订单取消事件"""
        position_manager = self.trade_service.position_manager
        if symbol in position_manager.tpsl_orders:
            orders = position_manager.tpsl_orders[symbol]
            if orders.get('tp_order_id') == order_id:
                orders['tp_order_id'] = None
            elif orders.get('sl_order_id') == order_id:
                orders['sl_order_id'] = None

            if not orders.get('tp_order_id') and not orders.get('sl_order_id'):
                del position_manager.tpsl_orders[symbol]
                logger.debug(f"{symbol} TP/SL 订单记录已完全清除")
