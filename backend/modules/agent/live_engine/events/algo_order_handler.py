"""ALGO_UPDATE 事件处理器

处理 Binance 条件单（Algo Order）的状态变化事件。

职责：
- 解析 ALGO_UPDATE 事件
- 委托 TradeService 处理业务逻辑
"""

from typing import TYPE_CHECKING, Any, Dict, Optional

from modules.agent.live_engine.services.trade_service import OrderEvent
from modules.monitor.utils.logger import get_logger

if TYPE_CHECKING:
    from modules.agent.live_engine.core.repositories import OrderRepository
    from modules.agent.live_engine.services.trade_service import TradeService

logger = get_logger('live_engine.algo_order_handler')


class AlgoOrderHandler:
    """ALGO_UPDATE 事件处理器

    职责：
    - 解析 ALGO_UPDATE 事件
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
        """处理 ALGO_UPDATE 事件

        Args:
            data: 事件数据
        """
        try:
            order_info = data.get('o', {})

            status = order_info.get('X', '')
            algo_id = str(order_info.get('aid', ''))
            symbol = order_info.get('s', '')

            if not algo_id:
                logger.debug("[AlgoOrderHandler] 收到无效的 ALGO_UPDATE 事件: 缺少 algo_id")
                return

            logger.debug(f"[AlgoOrderHandler] ALGO_UPDATE: {symbol} status={status} algoId={algo_id}")

            event = OrderEvent(
                symbol=symbol,
                order_id=self._extract_order_id(order_info),
                algo_id=algo_id,
                status=status,
                side=order_info.get('S', ''),
                order_type=order_info.get('o', ''),
                avg_price=float(order_info.get('ap', 0) or 0),
                filled_qty=float(order_info.get('aq', 0) or 0),
                reject_reason=order_info.get('rm', '')
            )

            if self.trade_service.linked_order_repo:
                linked_order = self.trade_service.linked_order_repo.get_order_by_binance_algo_id(algo_id)
                if linked_order:
                    self._handle_linked_order(linked_order, event)
                    return

            if self.order_repository:
                pending_order = self.order_repository.find_by_algo_id(algo_id)
                if pending_order and pending_order.order_kind == 'CONDITIONAL':
                    self._handle_entry_order(pending_order, event)
                    return

            record = self.trade_service.position_manager.find_record_by_tp_algo_id(algo_id)
            if record:
                self._handle_tpsl_order(record, event, 'TP')
                return

            record = self.trade_service.position_manager.find_record_by_sl_algo_id(algo_id)
            if record:
                self._handle_tpsl_order(record, event, 'SL')
                return

            logger.debug(f"[AlgoOrderHandler] algoId={algo_id} 不在任何跟踪列表中")

        except Exception as e:
            logger.error(f"[AlgoOrderHandler] 处理事件失败: {e}", exc_info=True)

    def _handle_linked_order(self, linked_order, event: OrderEvent):
        """处理 LinkedOrderRepository 中的条件单更新"""
        from modules.agent.live_engine.core.models import OrderPurpose

        status = event.status
        purpose = linked_order.purpose

        if status in ('TRIGGERED', 'FILLED', 'FINISHED'):
            logger.info(f"[AlgoOrderHandler] 🎯 条件单触发 (LinkedOrder): {event.symbol} "
                       f"algoId={event.algo_id} purpose={purpose.value}")

            if purpose == OrderPurpose.TAKE_PROFIT:
                self.trade_service.on_linked_order_filled(linked_order, event)
            elif purpose == OrderPurpose.STOP_LOSS:
                self.trade_service.on_linked_order_filled(linked_order, event)
            elif purpose == OrderPurpose.CLOSE:
                self.trade_service.on_linked_order_filled(linked_order, event)

        elif status in ('CANCELLED', 'EXPIRED', 'REJECTED'):
            logger.info(f"[AlgoOrderHandler] 🚫 条件单取消/过期/拒绝: {event.symbol} "
                       f"algoId={event.algo_id} status={status}")
            self.trade_service.on_linked_order_cancelled(linked_order)

    def _handle_entry_order(self, pending_order, event: OrderEvent):
        """处理开仓条件单状态更新"""
        status = event.status
        symbol = pending_order.symbol

        if status == 'FINISHED':
            if not event.order_id:
                logger.warning(f"[AlgoOrderHandler] ⚠️ 条件单 FINISHED 但无触发订单 ID: {symbol} algoId={event.algo_id}")
                self.order_repository.remove(pending_order.id)
                return

            self.trade_service.on_entry_algo_order_finished(event, pending_order)

        elif status in ('CANCELLED', 'CANCELED', 'EXPIRED', 'REJECTED'):
            logger.info(f"[AlgoOrderHandler] 开仓条件单 {status}: {symbol} algoId={event.algo_id}")
            self.trade_service.on_entry_order_cancelled(pending_order)

    def _handle_tpsl_order(self, record, event: OrderEvent, order_type: str):
        """处理止盈/止损条件单状态更新"""
        status = event.status
        symbol = record.symbol

        if status in ('TRIGGERED', 'FILLED'):
            if order_type == 'TP':
                self.trade_service.on_tp_triggered(event, record)
            else:
                self.trade_service.on_sl_triggered(event, record)

        elif status in ('CANCELLED', 'EXPIRED', 'REJECTED'):
            logger.info(f"[AlgoOrderHandler] {order_type} 单 {status}: {symbol} algoId={event.algo_id}")
            self.trade_service.on_tpsl_order_cancelled(record, order_type)

    def _extract_order_id(self, order_info: Dict) -> Optional[int]:
        """从 ALGO_UPDATE 事件中提取触发后生成的市价单 ID"""
        ai = order_info.get('ai', '')
        if ai and ai != '':
            try:
                return int(ai)
            except (ValueError, TypeError):
                pass
        return None
