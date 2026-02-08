"""ORDER_TRADE_UPDATE 事件处理器

处理 Binance 普通订单的状态变化事件。

职责：
- 监听限价单成交事件
- 当 pending limit order 成交时，创建开仓记录并下 TP/SL 订单
- 当止盈限价单 (tp_order_id) 成交时，获取手续费并关闭记录
- 处理 TP/SL 订单取消事件

事件流程：
1. 开仓限价单成交 (FILLED) -> 查找 pending_orders -> 创建 TradeRecord -> 下 TP/SL
2. 止盈限价单成交 (FILLED) -> 查找 TradeRecord.tp_order_id -> 获取手续费 -> 关闭记录
3. TP/SL 订单取消 -> 清理本地记录
"""
from typing import TYPE_CHECKING, Any, Dict

from modules.agent.live_engine.core.models import OrderPurpose, OrderStatus, OrderType, RecordStatus
from modules.monitor.utils.logger import get_logger

if TYPE_CHECKING:
    from modules.agent.live_engine.core.repositories import LinkedOrderRepository, OrderRepository
    from modules.agent.live_engine.services.commission_service import CommissionService

    from ..services.record_service import RecordService

logger = get_logger('live_engine.order_handler')


class OrderUpdateHandler:
    """ORDER_TRADE_UPDATE 事件处理器

    职责：
    - 处理开仓限价单成交事件（创建开仓记录、下 TP/SL）
    - 处理止盈限价单成交事件（获取手续费、关闭记录）
    - 处理订单取消事件（清理本地记录）
    """

    def __init__(
        self,
        order_service,
        order_repository: 'OrderRepository' = None,
        record_service: 'RecordService' = None,
        linked_order_repo: 'LinkedOrderRepository' = None,
        commission_service: 'CommissionService' = None
    ):
        """初始化

        Args:
            order_service: 订单服务（用于 TP/SL 订单状态管理）
            order_repository: 订单仓库（用于查找 pending orders）
            record_service: 记录服务（用于创建开仓记录、下 TP/SL、关闭记录）
            linked_order_repo: 关联订单仓库
            commission_service: 手续费服务
        """
        self.order_service = order_service
        self.order_repository = order_repository
        self.record_service = record_service
        self.linked_order_repo = linked_order_repo
        self.commission_service = commission_service

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

            if order_status == 'FILLED':
                self._handle_order_filled(order_data)

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

    def _handle_order_filled(self, order_data: Dict):
        """处理订单成交事件

        按优先级检查：
        1. 检查 LinkedOrderRepository 中的订单（通过本地记录判断类型）
        2. 是否是开仓限价单（pending order）-> 创建开仓记录
        3. 是否是止盈限价单（tp_order_id）-> 获取手续费并关闭记录

        Args:
            order_data: 订单数据
        """
        if not self.record_service:
            return

        order_id = int(order_data.get('i', 0))
        symbol = order_data.get('s', '')
        filled_price = float(order_data.get('ap', 0))

        if self.linked_order_repo:
            linked_order = self.linked_order_repo.get_order_by_binance_id(order_id)
            if linked_order:
                self._handle_linked_order_filled(linked_order, order_data)
                return

        if self.order_repository:
            pending_order = self.order_repository.find_by_order_id(order_id)
            if pending_order and pending_order.order_kind == 'LIMIT':
                self._handle_entry_order_filled(order_data, pending_order)
                return

        record = self.record_service.find_record_by_tp_order_id(order_id)
        if record:
            self._handle_tp_limit_order_filled(symbol, order_id, filled_price, record)
            return

    def _handle_linked_order_filled(self, linked_order, order_data: Dict):
        """处理 LinkedOrderRepository 中的订单成交

        通过本地 Order 的 purpose 判断订单类型：
        - ENTRY: 入场订单
        - TAKE_PROFIT: 止盈订单
        - STOP_LOSS: 止损订单
        - CLOSE: 平仓订单
        """
        symbol = linked_order.symbol
        order_id = linked_order.binance_order_id
        purpose = linked_order.purpose

        logger.info(f"[OrderHandler] 🎯 订单成交 (LinkedOrder): {symbol} "
                   f"orderId={order_id} purpose={purpose.value}")

        if self.commission_service:
            self.commission_service.fetch_trades_for_order(linked_order)

        self.linked_order_repo.update_order(linked_order.id, status=OrderStatus.FILLED)

        if purpose == OrderPurpose.TAKE_PROFIT:
            self._handle_linked_tp_filled(linked_order)
        elif purpose == OrderPurpose.STOP_LOSS:
            self._handle_linked_sl_filled(linked_order)
        elif purpose == OrderPurpose.CLOSE:
            self._handle_linked_close_filled(linked_order)

    def _handle_linked_tp_filled(self, order):
        """处理止盈订单成交（LinkedOrder）"""
        if not order.record_id:
            return

        record = self.record_service.get_record(order.record_id)
        if not record:
            return

        self.record_service.cancel_remaining_tpsl(record, 'TP')

        close_price = order.avg_filled_price or order.price or record.tp_price
        self.record_service.close_record(
            record_id=order.record_id,
            close_price=close_price,
            close_reason='TP_CLOSED',
            exit_commission=order.commission,
            realized_pnl=order.realized_pnl
        )

        logger.info(f"[OrderHandler] 🎯 止盈平仓完成 (LinkedOrder): {order.symbol} "
                   f"@ {close_price} commission={order.commission:.6f}")

    def _handle_linked_sl_filled(self, order):
        """处理止损订单成交（LinkedOrder）"""
        if not order.record_id:
            return

        record = self.record_service.get_record(order.record_id)
        if not record:
            return

        self.record_service.cancel_remaining_tpsl(record, 'SL')

        close_price = order.avg_filled_price or order.stop_price or record.sl_price
        self.record_service.close_record(
            record_id=order.record_id,
            close_price=close_price,
            close_reason='SL_CLOSED',
            exit_commission=order.commission,
            realized_pnl=order.realized_pnl
        )

        logger.info(f"[OrderHandler] 🛑 止损平仓完成 (LinkedOrder): {order.symbol} "
                   f"@ {close_price} commission={order.commission:.6f}")

    def _handle_linked_close_filled(self, order):
        """处理手动平仓订单成交（LinkedOrder）"""
        if not order.record_id:
            return

        record = self.record_service.get_record(order.record_id)
        if not record:
            return

        close_price = order.avg_filled_price or record.entry_price
        self.record_service.close_record(
            record_id=order.record_id,
            close_price=close_price,
            close_reason='MANUAL_CLOSE',
            exit_commission=order.commission,
            realized_pnl=order.realized_pnl
        )

    def _handle_entry_order_filled(self, order_data: Dict, pending_order):
        """处理开仓限价单成交

        Args:
            order_data: 订单数据
            pending_order: 待成交的开仓订单
        """
        order_id = int(order_data.get('i', 0))
        symbol = order_data.get('s', '')

        filled_price = float(order_data.get('ap', 0))
        if filled_price == 0:
            filled_price = pending_order.trigger_price

        logger.info(f"[OrderHandler] 📦 开仓限价单成交: {symbol} orderId={order_id} price={filled_price}")

        entry_commission = 0.0
        if order_id:
            entry_commission = self.record_service.fetch_entry_commission(symbol, order_id)
            if entry_commission > 0:
                logger.info(f"[OrderHandler] 💰 开仓手续费: {entry_commission:.6f} USDT")

        self.record_service.create_record(
            symbol=pending_order.symbol,
            side=pending_order.side,
            qty=pending_order.quantity,
            entry_price=filled_price,
            leverage=pending_order.leverage,
            tp_price=pending_order.tp_price,
            sl_price=pending_order.sl_price,
            source=pending_order.source,
            entry_order_id=order_id,
            agent_order_id=pending_order.agent_order_id,
            entry_commission=entry_commission,
            auto_place_tpsl=True
        )

        self.order_repository.remove(pending_order.id)
        logger.info(f"[OrderHandler] ✅ 开仓记录已创建，pending order 已移除: {pending_order.id}")

    def _handle_tp_limit_order_filled(self, symbol: str, order_id: int, filled_price: float, record):
        """处理止盈限价单成交

        当止盈限价单成交时：
        1. 取消剩余的止损单
        2. 通过 order_id 查询 API 获取实际成交价格和手续费
        3. 关闭开仓记录

        Args:
            symbol: 交易对
            order_id: 订单ID
            filled_price: 成交价格（WebSocket 事件中的价格）
            record: 关联的开仓记录
        """
        logger.info(f"[OrderHandler] 🎯 止盈限价单成交: {symbol} orderId={order_id} price={filled_price}")

        self.record_service.cancel_remaining_tpsl(record, 'TP')

        exit_commission = 0.0
        realized_pnl = None
        avg_price = filled_price

        if order_id:
            exit_info = self.record_service.fetch_exit_info(symbol, order_id)
            if exit_info.get('close_price'):
                avg_price = exit_info['close_price']
            exit_commission = exit_info.get('exit_commission', 0.0)
            realized_pnl = exit_info.get('realized_pnl')
            logger.info(f"[OrderHandler] 📊 平仓信息: price={avg_price} fee={exit_commission} pnl={realized_pnl}")

        self.record_service.close_record(
            record_id=record.id,
            close_price=avg_price,
            close_reason=RecordStatus.TP_CLOSED.value,
            exit_commission=exit_commission,
            realized_pnl=realized_pnl
        )

    def _handle_tpsl_cancelled(self, symbol: str, order_id: int):
        """处理 TP/SL 订单取消事件

        Args:
            symbol: 交易对
            order_id: 订单ID
        """
        if symbol in self.order_service.tpsl_orders:
            orders = self.order_service.tpsl_orders[symbol]
            if orders.get('tp_order_id') == order_id:
                orders['tp_order_id'] = None
            elif orders.get('sl_order_id') == order_id:
                orders['sl_order_id'] = None

            if not orders.get('tp_order_id') and not orders.get('sl_order_id'):
                del self.order_service.tpsl_orders[symbol]
                logger.debug(f"{symbol} TP/SL 订单记录已完全清除")
