"""订单同步服务

负责定期同步限价单和条件单的状态，作为 WebSocket 的兜底机制。
通过对比 Binance API 返回的挂单和本地 LinkedOrderRepository 的订单状态，
检测 WebSocket 可能丢失的订单成交/取消事件。

API 接口:
- GET /fapi/v1/openOrders: 查询所有限价挂单
- GET /fapi/v1/openAlgoOrders: 查询所有条件挂单
- GET /fapi/v1/order: 查询单个订单详情

同步逻辑:
1. 获取所有限价挂单和条件挂单
2. 对比本地 LinkedOrderRepository 中处于 OPEN 状态的订单
3. 如果本地有但 API 没有，说明订单已成交/取消
4. 根据订单用途 (purpose) 触发相应的处理流程
"""

from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Set

from modules.agent.live_engine.core.models import (
    Order,
    OrderPurpose,
    OrderStatus,
    RecordStatus,
)
from modules.monitor.utils.logger import get_logger

if TYPE_CHECKING:
    from modules.agent.live_engine.core.repositories import LinkedOrderRepository
    from modules.agent.live_engine.services import CommissionService, RecordService
    from modules.monitor.clients.binance_rest import BinanceRestClient

logger = get_logger('live_engine.sync.order_sync')


class OrderSyncService:
    """订单同步服务

    职责:
    - 定期同步限价单和条件单状态
    - 检测 WebSocket 丢失的订单事件
    - 根据订单用途触发相应处理

    与 TPSLSyncer 的区别:
    - TPSLSyncer: 基于 TradeRecord 的 tp_order_id/sl_algo_id 同步
    - OrderSyncService: 基于 LinkedOrderRepository 的 Order 对象同步
    """

    def __init__(
        self,
        rest_client: 'BinanceRestClient',
        linked_order_repo: 'LinkedOrderRepository',
        commission_service: 'CommissionService',
        record_service: 'RecordService',
    ):
        """初始化

        Args:
            rest_client: Binance REST 客户端
            linked_order_repo: 关联订单仓库
            commission_service: 手续费服务
            record_service: 记录服务
        """
        self.rest_client = rest_client
        self.linked_order_repo = linked_order_repo
        self.commission_service = commission_service
        self.record_service = record_service

        self._on_order_filled_callbacks: List[Callable[[Order], None]] = []

    def on_order_filled(self, callback: Callable[[Order], None]):
        """注册订单成交回调

        当检测到订单成交时调用此回调。

        Args:
            callback: 回调函数，参数为成交的订单
        """
        self._on_order_filled_callbacks.append(callback)

    def sync(self) -> Dict[str, int]:
        """执行同步

        Returns:
            同步结果统计 {synced_limit, synced_algo, filled_orders}
        """
        result = {
            'synced_limit': 0,
            'synced_algo': 0,
            'filled_orders': 0,
        }

        try:
            limit_filled = self._sync_limit_orders()
            algo_filled = self._sync_algo_orders()

            result['synced_limit'] = len(limit_filled)
            result['synced_algo'] = len(algo_filled)
            result['filled_orders'] = len(limit_filled) + len(algo_filled)

            if result['filled_orders'] > 0:
                logger.info(f"[OrderSyncService] 同步完成: "
                           f"limit={result['synced_limit']} algo={result['synced_algo']}")

        except Exception as e:
            logger.error(f"[OrderSyncService] 同步失败: {e}")

        return result

    def _sync_limit_orders(self) -> List[Order]:
        """同步限价单

        Returns:
            已成交/取消的订单列表
        """
        local_open_limits = self.linked_order_repo.get_open_limit_orders()
        if not local_open_limits:
            return []

        try:
            api_open_orders = self.rest_client.get_open_orders()
        except Exception as e:
            logger.warning(f"[OrderSyncService] 获取限价挂单失败: {e}")
            return []

        api_order_ids = {int(o.get('orderId', 0)) for o in api_open_orders}

        filled_orders = []
        for order in local_open_limits:
            if order.binance_order_id and order.binance_order_id not in api_order_ids:
                filled_order = self._handle_order_disappeared(order)
                if filled_order:
                    filled_orders.append(filled_order)

        return filled_orders

    def _sync_algo_orders(self) -> List[Order]:
        """同步条件单

        Returns:
            已触发/取消的订单列表
        """
        local_open_algos = self.linked_order_repo.get_open_algo_orders()
        if not local_open_algos:
            return []

        api_algo_orders = self.rest_client.get_algo_open_orders()
        if api_algo_orders is None:
            logger.warning("[OrderSyncService] 查询条件单失败（可能限流），跳过本次同步")
            return []

        api_algo_ids = {str(o.get('algoId')) for o in api_algo_orders}

        triggered_orders = []
        for order in local_open_algos:
            if order.binance_algo_id and order.binance_algo_id not in api_algo_ids:
                triggered_order = self._handle_algo_order_disappeared(order)
                if triggered_order:
                    triggered_orders.append(triggered_order)

        return triggered_orders

    def _handle_order_disappeared(self, order: Order) -> Optional[Order]:
        """处理限价单消失（成交或取消）

        Args:
            order: 本地订单

        Returns:
            处理后的订单，如果无法处理返回 None
        """
        order_detail = self._get_order_detail(order)
        if not order_detail:
            return None

        status = order_detail.get('status', '')

        if status == 'FILLED':
            return self._handle_order_filled(order, order_detail)
        elif status in ('CANCELED', 'EXPIRED'):
            return self._handle_order_cancelled(order, status)
        else:
            logger.warning(f"[OrderSyncService] 未知订单状态: {order.symbol} "
                          f"orderId={order.binance_order_id} status={status}")
            return None

    def _handle_algo_order_disappeared(self, order: Order) -> Optional[Order]:
        """处理条件单消失（触发或取消）

        条件单触发后会生成一个新的市价单，但我们可能没有这个市价单的 ID。
        在兜底同步中，我们需要通过其他方式获取成交信息。

        Args:
            order: 本地订单

        Returns:
            处理后的订单，如果无法处理返回 None
        """
        logger.info(f"[OrderSyncService] 🔄 条件单已触发/取消: {order.symbol} "
                   f"algoId={order.binance_algo_id} purpose={order.purpose.value}")

        self.linked_order_repo.update_order(order.id, status=OrderStatus.TRIGGERED)
        order.status = OrderStatus.TRIGGERED

        if order.purpose == OrderPurpose.STOP_LOSS:
            self._handle_stop_loss_triggered(order)
        elif order.purpose == OrderPurpose.TAKE_PROFIT:
            self._handle_take_profit_triggered(order)
        elif order.purpose == OrderPurpose.ENTRY:
            self._handle_entry_triggered(order)
        elif order.purpose == OrderPurpose.CLOSE:
            self._handle_close_triggered(order)

        for callback in self._on_order_filled_callbacks:
            try:
                callback(order)
            except Exception as e:
                logger.error(f"[OrderSyncService] 订单成交回调失败: {e}")

        return order

    def _handle_order_filled(self, order: Order, order_detail: Dict) -> Order:
        """处理订单成交

        Args:
            order: 本地订单
            order_detail: API 返回的订单详情

        Returns:
            更新后的订单
        """
        logger.info(f"[OrderSyncService] 🔄 限价单已成交: {order.symbol} "
                   f"orderId={order.binance_order_id} purpose={order.purpose.value}")

        self.commission_service.fetch_trades_for_order(order)

        self.linked_order_repo.update_order(order.id, status=OrderStatus.FILLED)
        order.status = OrderStatus.FILLED

        if order.purpose == OrderPurpose.ENTRY:
            self._handle_entry_filled(order, order_detail)
        elif order.purpose == OrderPurpose.TAKE_PROFIT:
            self._handle_take_profit_filled(order, order_detail)
        elif order.purpose == OrderPurpose.STOP_LOSS:
            self._handle_stop_loss_filled(order, order_detail)
        elif order.purpose == OrderPurpose.CLOSE:
            self._handle_close_filled(order, order_detail)

        for callback in self._on_order_filled_callbacks:
            try:
                callback(order)
            except Exception as e:
                logger.error(f"[OrderSyncService] 订单成交回调失败: {e}")

        return order

    def _handle_order_cancelled(self, order: Order, status: str) -> Order:
        """处理订单取消

        Args:
            order: 本地订单
            status: 订单状态 (CANCELED/EXPIRED)

        Returns:
            更新后的订单
        """
        logger.info(f"[OrderSyncService] 🚫 限价单已取消: {order.symbol} "
                   f"orderId={order.binance_order_id} status={status}")

        new_status = OrderStatus.CANCELLED if status == 'CANCELED' else OrderStatus.EXPIRED
        self.linked_order_repo.update_order(order.id, status=new_status)
        order.status = new_status

        return order

    def _handle_entry_filled(self, order: Order, order_detail: Dict):
        """处理入场订单成交

        入场订单成交意味着开仓，但如果 WebSocket 丢失了这个事件，
        可能 TradeRecord 还没有创建。这种情况比较复杂，暂时只记录日志。
        """
        logger.info(f"[OrderSyncService] 📗 入场订单成交 (同步检测): {order.symbol} "
                   f"commission={order.commission:.6f}")

    def _handle_entry_triggered(self, order: Order):
        """处理入场条件单触发"""
        logger.info(f"[OrderSyncService] 📗 入场条件单触发 (同步检测): {order.symbol}")

    def _handle_take_profit_filled(self, order: Order, order_detail: Dict):
        """处理止盈订单成交"""
        if not order.record_id:
            logger.warning(f"[OrderSyncService] 止盈订单无关联记录: {order.symbol}")
            return

        record = self.record_service.get_record(order.record_id)
        if not record:
            logger.warning(f"[OrderSyncService] 找不到关联记录: {order.record_id}")
            return

        self.record_service.cancel_remaining_tpsl(record, 'TP')

        close_price = order.avg_filled_price or float(order_detail.get('avgPrice', 0))
        self.record_service.close_record(
            record_id=order.record_id,
            close_price=close_price,
            close_reason='TP_CLOSED',
            exit_commission=order.commission,
            realized_pnl=order.realized_pnl
        )

        logger.info(f"[OrderSyncService] 🎯 止盈平仓完成 (同步检测): {order.symbol} "
                   f"@ {close_price} commission={order.commission:.6f}")

    def _handle_take_profit_triggered(self, order: Order):
        """处理止盈条件单触发"""
        if not order.record_id:
            logger.warning(f"[OrderSyncService] 止盈条件单无关联记录: {order.symbol}")
            return

        record = self.record_service.get_record(order.record_id)
        if not record:
            logger.warning(f"[OrderSyncService] 找不到关联记录: {order.record_id}")
            return

        self.record_service.cancel_remaining_tpsl(record, 'TP')

        close_price = self._get_mark_price(order.symbol, order.stop_price)
        self.record_service.close_record(
            record_id=order.record_id,
            close_price=close_price,
            close_reason='TP_CLOSED',
            exit_commission=0.0,
            realized_pnl=None
        )

        logger.info(f"[OrderSyncService] 🎯 止盈平仓完成 (同步检测): {order.symbol} @ {close_price}")

    def _handle_stop_loss_filled(self, order: Order, order_detail: Dict):
        """处理止损订单成交"""
        if not order.record_id:
            logger.warning(f"[OrderSyncService] 止损订单无关联记录: {order.symbol}")
            return

        record = self.record_service.get_record(order.record_id)
        if not record:
            logger.warning(f"[OrderSyncService] 找不到关联记录: {order.record_id}")
            return

        self.record_service.cancel_remaining_tpsl(record, 'SL')

        close_price = order.avg_filled_price or float(order_detail.get('avgPrice', 0))
        self.record_service.close_record(
            record_id=order.record_id,
            close_price=close_price,
            close_reason='SL_CLOSED',
            exit_commission=order.commission,
            realized_pnl=order.realized_pnl
        )

        logger.info(f"[OrderSyncService] 🛑 止损平仓完成 (同步检测): {order.symbol} "
                   f"@ {close_price} commission={order.commission:.6f}")

    def _handle_stop_loss_triggered(self, order: Order):
        """处理止损条件单触发

        止损条件单触发后会生成市价单，但我们没有这个市价单的 ID。
        只能使用标记价格作为平仓价格。
        """
        if not order.record_id:
            logger.warning(f"[OrderSyncService] 止损条件单无关联记录: {order.symbol}")
            return

        record = self.record_service.get_record(order.record_id)
        if not record:
            logger.warning(f"[OrderSyncService] 找不到关联记录: {order.record_id}")
            return

        self.record_service.cancel_remaining_tpsl(record, 'SL')

        close_price = self._get_mark_price(order.symbol, order.stop_price)
        self.record_service.close_record(
            record_id=order.record_id,
            close_price=close_price,
            close_reason=RecordStatus.SL_CLOSED.value,
            exit_commission=0.0,
            realized_pnl=None
        )

        logger.info(f"[OrderSyncService] 🛑 止损平仓完成 (同步检测): {order.symbol} @ {close_price}")

    def _handle_close_filled(self, order: Order, order_detail: Dict):
        """处理平仓订单成交"""
        if not order.record_id:
            return

        record = self.record_service.get_record(order.record_id)
        if not record:
            return

        close_price = order.avg_filled_price or float(order_detail.get('avgPrice', 0))
        self.record_service.close_record(
            record_id=order.record_id,
            close_price=close_price,
            close_reason='MANUAL_CLOSE',
            exit_commission=order.commission,
            realized_pnl=order.realized_pnl
        )

        logger.info(f"[OrderSyncService] 📕 手动平仓完成 (同步检测): {order.symbol} "
                   f"@ {close_price} commission={order.commission:.6f}")

    def _handle_close_triggered(self, order: Order):
        """处理平仓条件单触发"""
        if not order.record_id:
            return

        record = self.record_service.get_record(order.record_id)
        if not record:
            return

        close_price = self._get_mark_price(order.symbol, order.stop_price)
        self.record_service.close_record(
            record_id=order.record_id,
            close_price=close_price,
            close_reason=RecordStatus.MANUAL_CLOSED.value,
            exit_commission=0.0,
            realized_pnl=None
        )

        logger.info(f"[OrderSyncService] 📕 手动平仓完成 (同步检测): {order.symbol} @ {close_price}")

    def _get_order_detail(self, order: Order) -> Optional[Dict]:
        """获取订单详情

        Args:
            order: 本地订单

        Returns:
            订单详情，获取失败返回 None
        """
        if not order.binance_order_id:
            return None

        try:
            return self.rest_client.get_order(order.symbol, order.binance_order_id)
        except Exception as e:
            logger.warning(f"[OrderSyncService] 获取订单详情失败: {order.symbol} "
                          f"orderId={order.binance_order_id} error={e}")
            return None

    def _get_mark_price(self, symbol: str, fallback: Optional[float]) -> float:
        """获取标记价格

        Args:
            symbol: 交易对
            fallback: 默认值

        Returns:
            标记价格
        """
        try:
            data = self.rest_client.get_mark_price(symbol)
            return float(data.get('markPrice', fallback or 0))
        except Exception:
            return fallback or 0

    def get_active_order_ids(self) -> Dict[str, Set]:
        """获取 API 返回的所有活跃订单 ID

        用于外部清理孤儿订单。

        Returns:
            {limit_order_ids: Set[int], algo_order_ids: Set[str]}
        """
        result = {
            'limit_order_ids': set(),
            'algo_order_ids': set(),
        }

        try:
            api_open_orders = self.rest_client.get_open_orders()
            result['limit_order_ids'] = {int(o.get('orderId', 0)) for o in api_open_orders}
        except Exception as e:
            logger.warning(f"[OrderSyncService] 获取限价挂单失败: {e}")

        api_algo_orders = self.rest_client.get_algo_open_orders()
        if api_algo_orders is not None:
            result['algo_order_ids'] = {str(o.get('algoId')) for o in api_algo_orders}

        return result
