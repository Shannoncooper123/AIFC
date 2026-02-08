"""ALGO_UPDATE 事件处理器

处理 Binance 条件单（Algo Order）的状态变化事件。

职责：
- 监听 ALGO_UPDATE 事件（条件单状态变化）
- 区分三种条件单：开仓条件单、止盈条件单、止损条件单
- 开仓条件单触发后创建记录并下 TP/SL
- 止盈/止损触发后自动关闭记录并取消另一个条件单

事件流程：
1. 开仓条件单触发 (TRIGGERED/FILLED) -> 查找 pending_orders -> 创建 TradeRecord -> 下 TP/SL
2. TP 条件单触发 -> 关闭记录 (TP_CLOSED) -> 取消 SL 条件单
3. SL 条件单触发 -> 关闭记录 (SL_CLOSED) -> 取消 TP 条件单

ALGO_UPDATE 事件格式：
{
    "e": "ALGO_UPDATE",
    "o": {
        "s": "BTCUSDT",       # symbol
        "aid": "123456",      # algo_id
        "X": "FILLED",        # status: NEW/TRIGGERED/TRIGGERING/FILLED/CANCELLED/EXPIRED/REJECTED
        "ap": "50000.0",      # avg_price
        "ai": "789",          # 触发后生成的市价单 order_id
        "S": "BUY",           # side
        "o": "STOP_MARKET",   # order_type
        "aq": "0.1",          # filled_qty
        "rm": "reason"        # reject_reason（仅 REJECTED 状态）
    }
}
"""

from typing import TYPE_CHECKING, Any, Dict, Optional

from modules.agent.live_engine.core.models import OrderPurpose, OrderStatus, RecordStatus
from modules.monitor.utils.logger import get_logger

if TYPE_CHECKING:
    from modules.agent.live_engine.core.repositories import LinkedOrderRepository, OrderRepository
    from modules.agent.live_engine.services.commission_service import CommissionService

    from ..services.order_manager import OrderManager
    from ..services.record_service import RecordService

logger = get_logger('live_engine.algo_order_handler')


class AlgoOrderHandler:
    """ALGO_UPDATE 事件处理器

    职责：
    - 处理条件单状态变化事件
    - 开仓条件单触发后创建记录并下 TP/SL
    - 止盈止损触发后自动关闭记录
    """

    def __init__(
        self,
        record_service: 'RecordService',
        order_manager: 'OrderManager' = None,
        order_repository: 'OrderRepository' = None,
        linked_order_repo: 'LinkedOrderRepository' = None,
        commission_service: 'CommissionService' = None
    ):
        """初始化

        Args:
            record_service: 记录服务
            order_manager: 订单管理器（用于取消订单）
            order_repository: 订单仓库（用于查找 pending orders）
            linked_order_repo: 关联订单仓库
            commission_service: 手续费服务
        """
        self.record_service = record_service
        self.order_manager = order_manager
        self.order_repository = order_repository
        self.linked_order_repo = linked_order_repo
        self.commission_service = commission_service

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

            if self.linked_order_repo:
                linked_order = self.linked_order_repo.get_order_by_binance_algo_id(algo_id)
                if linked_order:
                    self._handle_linked_algo_update(linked_order, status, order_info)
                    return

            if self.order_repository:
                pending_order = self.order_repository.find_by_algo_id(algo_id)
                if pending_order and pending_order.order_kind == 'CONDITIONAL':
                    self._handle_entry_algo_update(algo_id, pending_order, status, order_info)
                    return

            tp_record = self.record_service.find_record_by_tp_algo_id(algo_id)
            if tp_record:
                self._handle_tp_order_update(algo_id, tp_record, status, order_info)
                return

            sl_record = self.record_service.find_record_by_sl_algo_id(algo_id)
            if sl_record:
                self._handle_sl_order_update(algo_id, sl_record, status, order_info)
                return

            logger.debug(f"[AlgoOrderHandler] algoId={algo_id} 不在任何跟踪列表中")

        except Exception as e:
            logger.error(f"[AlgoOrderHandler] 处理事件失败: {e}", exc_info=True)

    def _handle_linked_algo_update(self, linked_order, status: str, order_info: Dict):
        """处理 LinkedOrderRepository 中的条件单更新

        通过本地 Order 的 purpose 判断订单类型，避免依赖 Binance 的 order_type
        """
        symbol = linked_order.symbol
        algo_id = linked_order.binance_algo_id
        purpose = linked_order.purpose

        if status in ('TRIGGERED', 'FILLED', 'FINISHED'):
            logger.info(f"[AlgoOrderHandler] 🎯 条件单触发 (LinkedOrder): {symbol} "
                       f"algoId={algo_id} purpose={purpose.value}")

            triggered_order_id = self._extract_order_id(order_info)

            if triggered_order_id and self.commission_service:
                linked_order.binance_order_id = triggered_order_id
                self.linked_order_repo.update_order(
                    linked_order.id,
                    binance_order_id=triggered_order_id,
                    status=OrderStatus.FILLED
                )
                self.commission_service.fetch_trades_for_order(linked_order)
            else:
                self.linked_order_repo.update_order(linked_order.id, status=OrderStatus.TRIGGERED)

            if purpose == OrderPurpose.ENTRY:
                self._handle_linked_entry_triggered(linked_order, order_info)
            elif purpose == OrderPurpose.TAKE_PROFIT:
                self._handle_linked_tp_triggered(linked_order, order_info)
            elif purpose == OrderPurpose.STOP_LOSS:
                self._handle_linked_sl_triggered(linked_order, order_info)
            elif purpose == OrderPurpose.CLOSE:
                self._handle_linked_close_triggered(linked_order, order_info)

        elif status == 'CANCELLED':
            logger.info(f"[AlgoOrderHandler] 🚫 条件单取消 (LinkedOrder): {symbol} "
                       f"algoId={algo_id} purpose={purpose.value}")
            self.linked_order_repo.update_order(linked_order.id, status=OrderStatus.CANCELLED)

        elif status == 'EXPIRED':
            logger.info(f"[AlgoOrderHandler] ⏰ 条件单过期 (LinkedOrder): {symbol} "
                       f"algoId={algo_id} purpose={purpose.value}")
            self.linked_order_repo.update_order(linked_order.id, status=OrderStatus.EXPIRED)

        elif status == 'REJECTED':
            reason = order_info.get('rm', '')
            logger.warning(f"[AlgoOrderHandler] ⚠️ 条件单被拒绝 (LinkedOrder): {symbol} "
                          f"algoId={algo_id} purpose={purpose.value} reason={reason}")
            self.linked_order_repo.update_order(linked_order.id, status=OrderStatus.CANCELLED)

    def _handle_linked_entry_triggered(self, order, order_info: Dict):
        """处理入场条件单触发（LinkedOrder）"""
        logger.info(f"[AlgoOrderHandler] 📗 入场条件单触发 (LinkedOrder): {order.symbol}")

    def _handle_linked_tp_triggered(self, order, order_info: Dict):
        """处理止盈条件单触发（LinkedOrder）"""
        if not order.record_id:
            return

        record = self.record_service.get_record(order.record_id)
        if not record:
            return

        self.record_service.cancel_remaining_tpsl(record, 'TP')

        avg_price = float(order_info.get('ap', 0))
        if avg_price == 0:
            avg_price = order.stop_price or record.tp_price

        self.record_service.close_record(
            record_id=order.record_id,
            close_price=avg_price,
            close_reason='TP_CLOSED',
            exit_commission=order.commission,
            realized_pnl=order.realized_pnl
        )

        logger.info(f"[AlgoOrderHandler] 🎯 止盈平仓完成 (LinkedOrder): {order.symbol} "
                   f"@ {avg_price} commission={order.commission:.6f}")

    def _handle_linked_sl_triggered(self, order, order_info: Dict):
        """处理止损条件单触发（LinkedOrder）"""
        if not order.record_id:
            return

        record = self.record_service.get_record(order.record_id)
        if not record:
            return

        self.record_service.cancel_remaining_tpsl(record, 'SL')

        avg_price = float(order_info.get('ap', 0))
        if avg_price == 0:
            avg_price = order.stop_price or record.sl_price

        self.record_service.close_record(
            record_id=order.record_id,
            close_price=avg_price,
            close_reason='SL_CLOSED',
            exit_commission=order.commission,
            realized_pnl=order.realized_pnl
        )

        logger.info(f"[AlgoOrderHandler] 🛑 止损平仓完成 (LinkedOrder): {order.symbol} "
                   f"@ {avg_price} commission={order.commission:.6f}")

    def _handle_linked_close_triggered(self, order, order_info: Dict):
        """处理平仓条件单触发（LinkedOrder）"""
        if not order.record_id:
            return

        record = self.record_service.get_record(order.record_id)
        if not record:
            return

        avg_price = float(order_info.get('ap', 0))
        if avg_price == 0:
            avg_price = order.stop_price or record.entry_price

        self.record_service.close_record(
            record_id=order.record_id,
            close_price=avg_price,
            close_reason='MANUAL_CLOSE',
            exit_commission=order.commission,
            realized_pnl=order.realized_pnl
        )

    def _handle_entry_algo_update(self, algo_id: str, pending_order, status: str, order_info: Dict):
        """处理开仓条件单状态更新

        Args:
            algo_id: 条件单ID
            pending_order: pending order 对象
            status: 状态
            order_info: 订单信息
        """
        symbol = pending_order.symbol

        if status in ('TRIGGERED', 'FILLED'):
            filled_price = float(order_info.get('ap', pending_order.trigger_price))
            triggered_order_id = self._extract_order_id(order_info)

            logger.info(f"[AlgoOrderHandler] 📦 开仓条件单触发: {symbol} algoId={algo_id} "
                       f"price={filled_price} orderId={triggered_order_id}")

            entry_commission = 0.0
            if triggered_order_id:
                entry_commission = self.record_service.fetch_entry_commission(symbol, triggered_order_id)
                if entry_commission > 0:
                    logger.info(f"[AlgoOrderHandler] 💰 开仓手续费: {entry_commission:.6f} USDT")

            self.record_service.create_record(
                symbol=pending_order.symbol,
                side=pending_order.side,
                qty=pending_order.quantity,
                entry_price=filled_price,
                leverage=pending_order.leverage,
                tp_price=pending_order.tp_price,
                sl_price=pending_order.sl_price,
                source=pending_order.source,
                entry_algo_id=algo_id,
                entry_order_id=triggered_order_id,
                agent_order_id=pending_order.agent_order_id,
                entry_commission=entry_commission,
                auto_place_tpsl=True
            )

            self.order_repository.remove(pending_order.id)
            logger.info(f"[AlgoOrderHandler] ✅ 开仓记录已创建，pending order 已移除: {pending_order.id}")

        elif status == 'CANCELLED':
            logger.info(f"[AlgoOrderHandler] 开仓条件单已取消: {symbol} algoId={algo_id}")
            self.order_repository.remove(pending_order.id)

        elif status == 'EXPIRED':
            logger.info(f"[AlgoOrderHandler] 开仓条件单已过期: {symbol} algoId={algo_id}")
            self.order_repository.remove(pending_order.id)

        elif status == 'REJECTED':
            reason = order_info.get('rm', '')
            logger.warning(f"[AlgoOrderHandler] ⚠️ 开仓条件单被拒绝: {symbol} algoId={algo_id} reason={reason}")
            self.order_repository.remove(pending_order.id)

    def _extract_order_id(self, order_info: Dict) -> Optional[int]:
        """从 ALGO_UPDATE 事件中提取触发后生成的市价单 ID

        Args:
            order_info: ALGO_UPDATE 事件的订单信息

        Returns:
            订单ID，如果无法获取则返回 None
        """
        ai = order_info.get('ai', '')
        if ai and ai != '':
            try:
                return int(ai)
            except (ValueError, TypeError):
                pass
        return None

    def _handle_tp_order_update(self, algo_id: str, record, status: str, order_info: Dict):
        """处理止盈条件单状态更新

        Args:
            algo_id: 条件单ID
            record: 关联的开仓记录
            status: 状态
            order_info: 订单信息
        """
        symbol = record.symbol

        if status in ('TRIGGERED', 'FILLED'):
            avg_price = float(order_info.get('ap', 0))
            if avg_price == 0:
                avg_price = record.tp_price or record.entry_price

            order_id = self._extract_order_id(order_info)
            logger.info(f"[AlgoOrderHandler] 🎯 {symbol} 止盈触发 @ {avg_price} orderId={order_id}")

            self.record_service.cancel_remaining_tpsl(record, 'TP')

            exit_commission = 0.0
            realized_pnl = None
            if order_id:
                exit_info = self.record_service.fetch_exit_info(symbol, order_id)
                if exit_info.get('close_price'):
                    avg_price = exit_info['close_price']
                exit_commission = exit_info.get('exit_commission', 0.0)
                realized_pnl = exit_info.get('realized_pnl')
                logger.info(f"[AlgoOrderHandler] 📊 平仓信息: price={avg_price} fee={exit_commission} pnl={realized_pnl}")

            self.record_service.close_record(
                record_id=record.id,
                close_price=avg_price,
                close_reason=RecordStatus.TP_CLOSED.value,
                exit_commission=exit_commission,
                realized_pnl=realized_pnl
            )

        elif status == 'CANCELLED':
            logger.info(f"[AlgoOrderHandler] 止盈单已取消: {symbol} algoId={algo_id}")
            self.record_service.update_record_tpsl_ids(record.id, tp_algo_id=None)

        elif status == 'EXPIRED':
            logger.info(f"[AlgoOrderHandler] 止盈单已过期: {symbol} algoId={algo_id}")
            self.record_service.update_record_tpsl_ids(record.id, tp_algo_id=None)

        elif status == 'REJECTED':
            reason = order_info.get('rm', '')
            logger.warning(f"[AlgoOrderHandler] ⚠️ 止盈单被拒绝: {symbol} algoId={algo_id} reason={reason}")
            self.record_service.update_record_tpsl_ids(record.id, tp_algo_id=None)

    def _handle_sl_order_update(self, algo_id: str, record, status: str, order_info: Dict):
        """处理止损条件单状态更新

        Args:
            algo_id: 条件单ID
            record: 关联的开仓记录
            status: 状态
            order_info: 订单信息
        """
        symbol = record.symbol

        if status in ('TRIGGERED', 'FILLED'):
            avg_price = float(order_info.get('ap', 0))
            if avg_price == 0:
                avg_price = record.sl_price or record.entry_price

            order_id = self._extract_order_id(order_info)
            logger.info(f"[AlgoOrderHandler] 🛑 {symbol} 止损触发 @ {avg_price} orderId={order_id}")

            self.record_service.cancel_remaining_tpsl(record, 'SL')

            exit_commission = 0.0
            realized_pnl = None
            if order_id:
                exit_info = self.record_service.fetch_exit_info(symbol, order_id)
                if exit_info.get('close_price'):
                    avg_price = exit_info['close_price']
                exit_commission = exit_info.get('exit_commission', 0.0)
                realized_pnl = exit_info.get('realized_pnl')
                logger.info(f"[AlgoOrderHandler] 📊 平仓信息: price={avg_price} fee={exit_commission} pnl={realized_pnl}")

            self.record_service.close_record(
                record_id=record.id,
                close_price=avg_price,
                close_reason=RecordStatus.SL_CLOSED.value,
                exit_commission=exit_commission,
                realized_pnl=realized_pnl
            )

        elif status == 'CANCELLED':
            logger.info(f"[AlgoOrderHandler] 止损单已取消: {symbol} algoId={algo_id}")
            self.record_service.update_record_tpsl_ids(record.id, sl_algo_id=None)

        elif status == 'EXPIRED':
            logger.info(f"[AlgoOrderHandler] 止损单已过期: {symbol} algoId={algo_id}")
            self.record_service.update_record_tpsl_ids(record.id, sl_algo_id=None)

        elif status == 'REJECTED':
            reason = order_info.get('rm', '')
            logger.warning(f"[AlgoOrderHandler] ⚠️ 止损单被拒绝: {symbol} algoId={algo_id} reason={reason}")
            self.record_service.update_record_tpsl_ids(record.id, sl_algo_id=None)
