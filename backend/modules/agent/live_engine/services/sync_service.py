"""统一同步服务

合并原 sync/ 目录下的所有同步器：
- SyncManager → 定时同步调度
- TPSLSyncer → TP/SL 订单状态同步
- PositionSyncer → 持仓状态同步

作为 WebSocket 事件的兜底机制，定期检查订单和持仓状态。
"""
import threading
import time
from typing import TYPE_CHECKING, Any, Dict, Optional, Set

from modules.agent.live_engine.core.models import RecordStatus
from modules.monitor.utils.logger import get_logger

if TYPE_CHECKING:
    from modules.agent.live_engine.services.price_service import PriceService
    from modules.agent.live_engine.manager import PositionManager
    from modules.agent.live_engine.services.trade_info_service import TradeInfoService
    from modules.monitor.clients.binance_rest import BinanceRestClient
    from modules.agent.live_engine.core.models import TradeRecord
    from modules.agent.live_engine.core.repositories import OrderRepository

logger = get_logger('live_engine.sync_service')


class SyncService:
    """统一同步服务

    职责：
    - 定时同步调度（start/stop）
    - TP/SL 订单状态检查
    - 持仓状态检查
    - 支持按 source 过滤同步范围
    """

    SYNC_INTERVAL = 5
    POSITION_SYNC_MULTIPLIER = 6

    def __init__(
        self,
        rest_client: 'BinanceRestClient',
        price_service: 'PriceService',
        trade_info_service: 'TradeInfoService',
        position_manager: 'PositionManager',
        order_repository: 'OrderRepository' = None
    ):
        """初始化

        Args:
            rest_client: Binance REST 客户端
            price_service: 价格服务
            trade_info_service: 成交信息服务
            position_manager: 仓位管理器
            order_repository: 挂单仓库（可选）
        """
        self.rest_client = rest_client
        self.price_service = price_service
        self.trade_info_service = trade_info_service
        self.position_manager = position_manager
        self.order_repository = order_repository

        self._running = False
        self._thread = None
        self._source_filter: Optional[str] = None

    def set_source_filter(self, source: Optional[str]):
        """设置同步的来源过滤"""
        self._source_filter = source
        logger.info(f"[SyncService] 同步范围设置为: {source or '全部'}")

    def start(self, source: Optional[str] = None):
        """启动同步线程"""
        if self._running:
            logger.warning("[SyncService] 已在运行")
            return

        self._source_filter = source
        self._running = True
        self._thread = threading.Thread(target=self._sync_loop, daemon=True)
        self._thread.start()

        position_interval = self.SYNC_INTERVAL * self.POSITION_SYNC_MULTIPLIER
        logger.info(f"[SyncService] 已启动 (同步间隔={self.SYNC_INTERVAL}s, "
                   f"持仓同步间隔={position_interval}s, 范围={source or '全部'})")

    def stop(self):
        """停止同步线程"""
        if not self._running:
            return

        self._running = False
        if self._thread and self._thread.is_alive():
            time.sleep(0.5)

        logger.info("[SyncService] 已停止")

    def _sync_loop(self):
        """定时同步循环"""
        position_sync_counter = 0

        while self._running:
            try:
                time.sleep(self.SYNC_INTERVAL)

                if not self._running:
                    break

                self.sync_tpsl_orders(source=self._source_filter)
                self.sync_pending_orders(source=self._source_filter)

                position_sync_counter += 1
                if position_sync_counter >= self.POSITION_SYNC_MULTIPLIER:
                    position_sync_counter = 0
                    self.sync_positions(source=self._source_filter)

            except Exception as e:
                logger.error(f"[SyncService] 同步失败: {e}", exc_info=True)

        logger.info("[SyncService] 同步线程已退出")

    def force_sync(self, source: Optional[str] = None):
        """强制立即执行一次完整同步"""
        src = source if source is not None else self._source_filter
        logger.info(f"[SyncService] 执行强制同步 (范围={src or '全部'})...")

        try:
            self.sync_tpsl_orders(source=src)
            self.sync_pending_orders(source=src)
            self.sync_positions(source=src)
            logger.info("[SyncService] 强制同步完成")
        except Exception as e:
            logger.error(f"[SyncService] 强制同步失败: {e}")

    def sync_pending_orders(self, source: Optional[str] = None) -> int:
        """同步挂单状态

        检查本地的挂单记录在 Binance 是否仍然存在，
        清理已在交易所被取消的订单。

        Args:
            source: 过滤来源 ('live', 'reverse' 或 None 表示全部)

        Returns:
            清理的订单数量
        """
        if not self.order_repository:
            return 0

        try:
            local_orders = self.order_repository.get_all(source=source)
            if not local_orders:
                return 0

            api_open_orders = self.rest_client.get_open_orders()
            if api_open_orders is None:
                logger.warning("[SyncService] ⚠️ 查询限价单失败，跳过本次同步")
                return 0

            api_algo_orders = self.rest_client.get_algo_open_orders()
            if api_algo_orders is None:
                api_algo_orders = []

            active_order_ids = {o.get('orderId') for o in api_open_orders}
            active_algo_ids = {str(o.get('algoId')) for o in api_algo_orders}

            cleaned_count = 0
            for order in local_orders:
                is_active = False

                if order.order_id and order.order_id in active_order_ids:
                    is_active = True
                if order.algo_id and order.algo_id in active_algo_ids:
                    is_active = True

                if not is_active:
                    logger.info(f"[SyncService] 🧹 清理已取消的挂单: {order.symbol} "
                               f"order_id={order.order_id} algo_id={order.algo_id}")
                    self.order_repository.delete(order.id)
                    cleaned_count += 1

            if cleaned_count > 0:
                logger.info(f"[SyncService] ✅ 已清理 {cleaned_count} 个已取消的挂单")

            return cleaned_count

        except Exception as e:
            logger.error(f"[SyncService] 同步挂单失败: {e}")
            return 0

    def sync_tpsl_orders(self, source: Optional[str] = None) -> Set[str]:
        """同步 TP/SL 订单状态

        检查止盈止损订单是否已触发。

        Args:
            source: 过滤来源 ('live', 'reverse' 或 None 表示全部)

        Returns:
            活跃的条件单 ID 集合
        """
        try:
            open_records = self.position_manager.get_open_records(source=source)
            if not open_records:
                return set()

            api_algo_orders = self.rest_client.get_algo_open_orders()
            if api_algo_orders is None:
                logger.warning("[SyncService] ⚠️ 查询条件单失败（可能限流），跳过本次同步")
                return set()

            active_algo_ids = {str(o.get('algoId')) for o in api_algo_orders}

            for record in open_records:
                self._check_record_tpsl(record, active_algo_ids)

            return active_algo_ids

        except Exception as e:
            logger.error(f"[SyncService] TP/SL同步失败: {e}")
            return set()

    def _check_record_tpsl(self, record: 'TradeRecord', active_algo_ids: Set[str]):
        """检查单条记录的 TP/SL 状态"""
        tp_triggered = False
        sl_triggered = False

        if record.tp_order_id:
            tp_triggered = self._check_tp_limit_order(record)
        elif record.tp_algo_id:
            if record.tp_algo_id not in active_algo_ids:
                logger.info(f"[SyncService] 🔄 止盈条件单已触发/取消: {record.symbol} algoId={record.tp_algo_id}")
                tp_triggered = True

        if record.sl_algo_id and record.sl_algo_id not in active_algo_ids:
            logger.info(f"[SyncService] 🔄 止损条件单已触发/取消: {record.symbol} algoId={record.sl_algo_id}")
            sl_triggered = True

        if tp_triggered and not sl_triggered:
            self._handle_tp_triggered(record)
        elif sl_triggered and not tp_triggered:
            self._handle_sl_triggered(record)
        elif tp_triggered and sl_triggered:
            logger.warning(f"[SyncService] ⚠️ TP/SL 同时消失: {record.symbol}")
            self.position_manager.clear_tpsl_ids(record.id)

    def _check_tp_limit_order(self, record: 'TradeRecord') -> bool:
        """检查止盈限价单状态"""
        try:
            order_status = self.rest_client.get_order(record.symbol, record.tp_order_id)
            if order_status and order_status.get('status') == 'FILLED':
                logger.info(f"[SyncService] 🔄 止盈限价单已成交: {record.symbol} orderId={record.tp_order_id}")
                return True
            elif order_status and order_status.get('status') in ('CANCELED', 'EXPIRED'):
                logger.warning(f"[SyncService] ⚠️ 止盈限价单已取消/过期: {record.symbol}")
                self.position_manager._repository.update(record.id, tp_order_id=None)
        except Exception as e:
            logger.warning(f"[SyncService] 查询止盈限价单失败: {record.symbol} error={e}")
        return False

    def _handle_tp_triggered(self, record: 'TradeRecord'):
        """处理止盈触发"""
        close_price = self.price_service.get_mark_price_with_fallback(
            record.symbol, record.tp_price or record.entry_price
        )
        logger.info(f"[SyncService] 🎯 止盈触发: {record.symbol} @ {close_price}")

        self.position_manager._cancel_remaining_tpsl(record, 'TP')

        exit_commission = 0.0
        realized_pnl = None
        avg_price = close_price

        if record.tp_order_id:
            exit_info = self.trade_info_service.get_exit_info(record.symbol, record.tp_order_id)
            if exit_info.close_price:
                avg_price = exit_info.close_price
            exit_commission = exit_info.exit_commission
            realized_pnl = exit_info.realized_pnl
            if exit_commission > 0:
                logger.info(f"[SyncService] 📊 止盈手续费: {exit_commission:.6f} USDT")

        self.position_manager._close_record(
            record_id=record.id,
            close_price=avg_price,
            close_reason=RecordStatus.TP_CLOSED.value,
            exit_commission=exit_commission,
            realized_pnl=realized_pnl
        )

    def _handle_sl_triggered(self, record: 'TradeRecord'):
        """处理止损触发"""
        close_price = self.price_service.get_mark_price_with_fallback(
            record.symbol, record.sl_price or record.entry_price
        )
        logger.info(f"[SyncService] 🛑 止损触发: {record.symbol} @ {close_price}")

        self.position_manager._cancel_remaining_tpsl(record, 'SL')

        self.position_manager._close_record(
            record_id=record.id,
            close_price=close_price,
            close_reason=RecordStatus.SL_CLOSED.value,
            exit_commission=0.0,
            realized_pnl=None
        )

    def sync_positions(self, source: Optional[str] = None) -> int:
        """同步持仓状态

        检查本地记录对应的 Binance 持仓是否存在。

        Args:
            source: 过滤来源

        Returns:
            关闭的记录数量
        """
        try:
            open_records = self.position_manager.get_open_records(source=source)
            if not open_records:
                return 0

            bn_positions = self._get_binance_positions()
            closed_count = 0

            for record in open_records:
                position_side = 'SHORT' if record.side.upper() in ('SELL', 'SHORT') else 'LONG'
                key = f"{record.symbol}_{position_side}"

                if key in bn_positions:
                    bn_pos = bn_positions[key]
                    if bn_pos['mark_price'] > 0:
                        self.position_manager.update_mark_price(record.symbol, bn_pos['mark_price'])
                else:
                    logger.warning(f"[SyncService] ⚠️ 本地记录无对应持仓: {record.symbol} {position_side} source={record.source}")
                    self._close_orphan_record(record)
                    closed_count += 1

            return closed_count

        except Exception as e:
            logger.error(f"[SyncService] 持仓同步失败: {e}")
            return 0

    def _get_binance_positions(self) -> Dict[str, Dict[str, Any]]:
        """获取 Binance 持仓信息"""
        account_info = self.rest_client.get_account()
        positions = account_info.get('positions', [])

        result = {}
        for pos in positions:
            symbol = pos.get('symbol', '')
            position_side = pos.get('positionSide', 'BOTH')
            position_amt = float(pos.get('positionAmt', 0))

            if position_amt != 0:
                key = f"{symbol}_{position_side}"
                result[key] = {
                    'symbol': symbol,
                    'position_side': position_side,
                    'position_amt': position_amt,
                    'mark_price': float(pos.get('markPrice', 0))
                }

        return result

    def _close_orphan_record(self, record: 'TradeRecord'):
        """关闭无持仓的本地记录"""
        close_price = self.price_service.get_mark_price_with_fallback(
            record.symbol, record.entry_price
        )

        self.position_manager._cancel_remaining_tpsl(record, 'TP')
        self.position_manager._cancel_remaining_tpsl(record, 'SL')

        self.position_manager._close_record(
            record_id=record.id,
            close_price=close_price,
            close_reason=RecordStatus.POSITION_CLOSED_EXTERNALLY.value
        )
        logger.info(f"[SyncService] 📕 记录已关闭: {record.symbol} @ {close_price} source={record.source} (外部平仓)")

    def get_status(self) -> dict:
        """获取同步状态"""
        return {
            'running': self._running,
            'source_filter': self._source_filter,
            'sync_interval': self.SYNC_INTERVAL,
            'position_sync_interval': self.SYNC_INTERVAL * self.POSITION_SYNC_MULTIPLIER
        }
