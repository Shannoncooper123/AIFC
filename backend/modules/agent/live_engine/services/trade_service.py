"""交易事件协调服务

处理交易所事件回调，协调 PositionManager 和 OrderManager。

事件流程图：
    ┌─────────────────┐
    │   Handler 层     │  事件解析
    └────────┬────────┘
             │ 调用
             ▼
    ┌─────────────────┐
    │  TradeService   │  事件协调
    └────────┬────────┘
             │ 调用
             ▼
    ┌─────────────────┐
    │  Manager 层      │  业务操作
    └─────────────────┘
"""
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Optional

from modules.agent.live_engine.core.models import OrderPurpose, OrderStatus, RecordStatus
from modules.monitor.utils.logger import get_logger

if TYPE_CHECKING:
    from modules.agent.live_engine.core.repositories import LinkedOrderRepository
    from modules.agent.live_engine.manager import OrderManager, PositionManager
    from modules.agent.live_engine.services.commission_service import CommissionService

logger = get_logger('live_engine.trade_service')


@dataclass
class OrderEvent:
    """订单事件数据"""
    symbol: str
    order_id: Optional[int] = None
    algo_id: Optional[str] = None
    status: str = ''
    avg_price: float = 0.0
    filled_qty: float = 0.0
    order_type: str = ''
    side: str = ''
    position_side: str = ''
    purpose: Optional[OrderPurpose] = None
    reject_reason: str = ''

    @classmethod
    def from_order_update(cls, data: Dict) -> 'OrderEvent':
        """从 ORDER_TRADE_UPDATE 事件解析"""
        order_data = data.get('o', {})
        return cls(
            symbol=order_data.get('s', ''),
            order_id=int(order_data.get('i', 0)) if order_data.get('i') else None,
            status=order_data.get('X', ''),
            avg_price=float(order_data.get('ap', 0)),
            filled_qty=float(order_data.get('z', 0)),
            order_type=order_data.get('o', ''),
            side=order_data.get('S', ''),
            position_side=order_data.get('ps', '')
        )

    @classmethod
    def from_algo_update(cls, data: Dict) -> 'OrderEvent':
        """从 ALGO_UPDATE 事件解析"""
        order_info = data.get('o', {})
        ai = order_info.get('ai', '')
        return cls(
            symbol=order_info.get('s', ''),
            algo_id=str(order_info.get('aid', '')),
            order_id=int(ai) if ai and ai != '' else None,
            status=order_info.get('X', ''),
            avg_price=float(order_info.get('ap', 0)),
            filled_qty=float(order_info.get('aq', 0)),
            order_type=order_info.get('o', ''),
            side=order_info.get('S', ''),
            reject_reason=order_info.get('rm', '')
        )


class TradeService:
    """交易事件协调服务

    处理 Handler 层的事件回调，协调 PositionManager 和 OrderManager。
    不包含具体的开平仓逻辑，仅负责事件处理和流程协调。
    """

    def __init__(
        self,
        position_manager: 'PositionManager',
        order_manager: 'OrderManager',
        linked_order_repo: 'LinkedOrderRepository' = None,
        commission_service: 'CommissionService' = None
    ):
        """初始化

        Args:
            position_manager: 持仓管理器
            order_manager: 挂单管理器
            linked_order_repo: 关联订单仓库（可选）
            commission_service: 手续费服务（可选）
        """
        self.position_manager = position_manager
        self.order_manager = order_manager
        self.linked_order_repo = linked_order_repo
        self.commission_service = commission_service

    def on_entry_limit_order_filled(self, event: OrderEvent, pending_order) -> bool:
        """处理入场限价单成交

        Args:
            event: 订单事件
            pending_order: pending order 对象

        Returns:
            是否处理成功
        """
        symbol = pending_order.symbol
        order_id = event.order_id

        filled_price = event.avg_price
        if not filled_price or filled_price == 0:
            filled_price = pending_order.trigger_price

        logger.info(f"[TradeService] 📦 入场限价单成交: {symbol} orderId={order_id} price={filled_price}")

        entry_commission = 0.0
        if order_id:
            entry_info = self.position_manager.fetch_entry_info(symbol, order_id)
            if entry_info.get('avg_price') and entry_info['avg_price'] > 0:
                filled_price = entry_info['avg_price']
            entry_commission = entry_info.get('commission', 0) or 0
            if entry_commission > 0:
                logger.info(f"[TradeService] 💰 开仓手续费: {entry_commission:.6f} USDT")

        if not filled_price:
            logger.error(f"[TradeService] ❌ 无法确定成交价格: {symbol}")
            self.order_manager.remove_pending_order(pending_order.id)
            return False

        self.position_manager._create_record(
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

        self.order_manager.remove_pending_order(pending_order.id)

        logger.info(f"[TradeService] ✅ 开仓记录已创建: {pending_order.id}")
        return True

    def on_entry_algo_order_finished(self, event: OrderEvent, pending_order) -> bool:
        """处理入场条件单完成

        Args:
            event: 订单事件
            pending_order: pending order 对象

        Returns:
            是否处理成功
        """
        symbol = pending_order.symbol
        algo_id = event.algo_id
        triggered_order_id = event.order_id

        if not triggered_order_id:
            logger.warning(f"[TradeService] ⚠️ 条件单 FINISHED 但无触发订单 ID: {symbol} algoId={algo_id}")
            self.order_manager.remove_pending_order(pending_order.id)
            return False

        entry_info = self.position_manager.fetch_entry_info(symbol, triggered_order_id)
        filled_price = entry_info.get('avg_price')
        entry_commission = entry_info.get('commission', 0) or 0

        if filled_price and filled_price > 0:
            logger.info(f"[TradeService] 📊 成交价: {filled_price} (来自 REST API)")
        else:
            filled_price = pending_order.trigger_price
            logger.warning(f"[TradeService] ⚠️ REST API 无成交记录，使用触发价: {filled_price}")

        if not filled_price:
            logger.error(f"[TradeService] ❌ 无法确定成交价格: {symbol}")
            self.order_manager.remove_pending_order(pending_order.id)
            return False

        logger.info(f"[TradeService] 📦 入场条件单完成: {symbol} algoId={algo_id} "
                   f"price={filled_price} orderId={triggered_order_id} commission={entry_commission:.6f}")

        self.position_manager._create_record(
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

        self.order_manager.remove_pending_order(pending_order.id)

        logger.info(f"[TradeService] ✅ 开仓记录已创建: {pending_order.id}")
        return True

    def on_entry_order_cancelled(self, pending_order) -> bool:
        """处理入场订单取消/过期/拒绝

        Args:
            pending_order: pending order 对象

        Returns:
            是否处理成功
        """
        self.order_manager.remove_pending_order(pending_order.id)
        logger.info(f"[TradeService] 📕 入场订单已移除: {pending_order.id}")
        return True

    def on_tp_triggered(self, event: OrderEvent, record) -> bool:
        """处理止盈触发

        Args:
            event: 订单事件
            record: 关联的交易记录

        Returns:
            是否处理成功
        """
        symbol = record.symbol
        order_id = event.order_id

        avg_price = event.avg_price
        if avg_price == 0:
            avg_price = record.tp_price or record.entry_price

        logger.info(f"[TradeService] 🎯 {symbol} 止盈触发 @ {avg_price} orderId={order_id}")

        self.position_manager._cancel_remaining_tpsl(record, 'TP')

        exit_commission = 0.0
        realized_pnl = None
        if order_id:
            exit_info = self.position_manager.fetch_exit_info(symbol, order_id)
            if exit_info.get('close_price'):
                avg_price = exit_info['close_price']
            exit_commission = exit_info.get('exit_commission', 0.0)
            realized_pnl = exit_info.get('realized_pnl')
            logger.info(f"[TradeService] 📊 平仓信息: price={avg_price} fee={exit_commission} pnl={realized_pnl}")

        self.position_manager._close_record(
            record_id=record.id,
            close_price=avg_price,
            close_reason=RecordStatus.TP_CLOSED.value,
            exit_commission=exit_commission,
            realized_pnl=realized_pnl
        )

        logger.info(f"[TradeService] ✅ 止盈平仓完成: {symbol}")
        return True

    def on_sl_triggered(self, event: OrderEvent, record) -> bool:
        """处理止损触发

        Args:
            event: 订单事件
            record: 关联的交易记录

        Returns:
            是否处理成功
        """
        symbol = record.symbol
        order_id = event.order_id

        avg_price = event.avg_price
        if avg_price == 0:
            avg_price = record.sl_price or record.entry_price

        logger.info(f"[TradeService] 🛑 {symbol} 止损触发 @ {avg_price} orderId={order_id}")

        self.position_manager._cancel_remaining_tpsl(record, 'SL')

        exit_commission = 0.0
        realized_pnl = None
        if order_id:
            exit_info = self.position_manager.fetch_exit_info(symbol, order_id)
            if exit_info.get('close_price'):
                avg_price = exit_info['close_price']
            exit_commission = exit_info.get('exit_commission', 0.0)
            realized_pnl = exit_info.get('realized_pnl')
            logger.info(f"[TradeService] 📊 平仓信息: price={avg_price} fee={exit_commission} pnl={realized_pnl}")

        self.position_manager._close_record(
            record_id=record.id,
            close_price=avg_price,
            close_reason=RecordStatus.SL_CLOSED.value,
            exit_commission=exit_commission,
            realized_pnl=realized_pnl
        )

        logger.info(f"[TradeService] ✅ 止损平仓完成: {symbol}")
        return True

    def on_manual_close(self, event: OrderEvent, record) -> bool:
        """处理手动平仓

        Args:
            event: 订单事件
            record: 关联的交易记录

        Returns:
            是否处理成功
        """
        symbol = record.symbol
        order_id = event.order_id

        avg_price = event.avg_price
        if avg_price == 0:
            avg_price = record.entry_price

        logger.info(f"[TradeService] 📕 {symbol} 手动平仓 @ {avg_price}")

        exit_commission = 0.0
        realized_pnl = None
        if order_id:
            exit_info = self.position_manager.fetch_exit_info(symbol, order_id)
            if exit_info.get('close_price'):
                avg_price = exit_info['close_price']
            exit_commission = exit_info.get('exit_commission', 0.0)
            realized_pnl = exit_info.get('realized_pnl')

        self.position_manager._close_record(
            record_id=record.id,
            close_price=avg_price,
            close_reason=RecordStatus.MANUAL_CLOSED.value,
            exit_commission=exit_commission,
            realized_pnl=realized_pnl
        )

        logger.info(f"[TradeService] ✅ 手动平仓完成: {symbol}")
        return True

    def on_tpsl_order_cancelled(self, record, order_type: str) -> bool:
        """处理 TP/SL 订单取消

        Args:
            record: 关联的交易记录
            order_type: 订单类型 ('TP' 或 'SL')

        Returns:
            是否处理成功
        """
        if order_type == 'TP':
            self.position_manager._repository.update(record.id, tp_algo_id=None, tp_order_id=None)
            logger.info(f"[TradeService] 止盈单已取消: {record.symbol}")
        elif order_type == 'SL':
            self.position_manager._repository.update(record.id, sl_algo_id=None)
            logger.info(f"[TradeService] 止损单已取消: {record.symbol}")
        return True

    def on_linked_order_filled(self, linked_order, event: OrderEvent) -> bool:
        """处理 LinkedOrder 成交

        Args:
            linked_order: 关联订单对象
            event: 订单事件

        Returns:
            是否处理成功
        """
        purpose = linked_order.purpose
        symbol = linked_order.symbol

        if self.commission_service and event.order_id:
            linked_order.binance_order_id = event.order_id
            self.commission_service.fetch_trades_for_order(linked_order)

        if self.linked_order_repo:
            self.linked_order_repo.update_order(
                linked_order.id,
                binance_order_id=event.order_id,
                status=OrderStatus.FILLED
            )

        if not linked_order.record_id:
            return True

        record = self.position_manager.get_record(linked_order.record_id)
        if not record:
            return False

        if purpose == OrderPurpose.TAKE_PROFIT:
            self.position_manager._cancel_remaining_tpsl(record, 'TP')
            close_price = linked_order.avg_filled_price or linked_order.price or record.tp_price
            self.position_manager._close_record(
                record_id=record.id,
                close_price=close_price,
                close_reason=RecordStatus.TP_CLOSED.value,
                exit_commission=linked_order.commission,
                realized_pnl=linked_order.realized_pnl
            )
            logger.info(f"[TradeService] 🎯 止盈平仓完成 (LinkedOrder): {symbol} @ {close_price}")

        elif purpose == OrderPurpose.STOP_LOSS:
            self.position_manager._cancel_remaining_tpsl(record, 'SL')
            close_price = linked_order.avg_filled_price or linked_order.stop_price or record.sl_price
            self.position_manager._close_record(
                record_id=record.id,
                close_price=close_price,
                close_reason=RecordStatus.SL_CLOSED.value,
                exit_commission=linked_order.commission,
                realized_pnl=linked_order.realized_pnl
            )
            logger.info(f"[TradeService] 🛑 止损平仓完成 (LinkedOrder): {symbol} @ {close_price}")

        elif purpose == OrderPurpose.CLOSE:
            close_price = linked_order.avg_filled_price or record.entry_price
            self.position_manager._close_record(
                record_id=record.id,
                close_price=close_price,
                close_reason=RecordStatus.MANUAL_CLOSED.value,
                exit_commission=linked_order.commission,
                realized_pnl=linked_order.realized_pnl
            )
            logger.info(f"[TradeService] 📕 手动平仓完成 (LinkedOrder): {symbol} @ {close_price}")

        return True

    def on_linked_order_cancelled(self, linked_order) -> bool:
        """处理 LinkedOrder 取消

        Args:
            linked_order: 关联订单对象

        Returns:
            是否处理成功
        """
        if self.linked_order_repo:
            self.linked_order_repo.update_order(linked_order.id, status=OrderStatus.CANCELLED)
        logger.info(f"[TradeService] 🚫 订单取消 (LinkedOrder): {linked_order.symbol} "
                   f"purpose={linked_order.purpose.value}")
        return True
