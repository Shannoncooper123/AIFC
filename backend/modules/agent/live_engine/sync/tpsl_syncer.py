"""TP/SL 订单同步器

负责同步止盈止损订单的状态，作为 WebSocket 的兜底机制。
支持按 source 过滤，可同时服务 live 和 reverse 两种来源。
"""

from typing import TYPE_CHECKING, Optional, Set

from modules.agent.live_engine.core.models import RecordStatus
from modules.monitor.utils.logger import get_logger

if TYPE_CHECKING:
    from modules.monitor.clients.binance_rest import BinanceRestClient

    from ..services.record_service import RecordService, TradeRecord

logger = get_logger('live_engine.sync.tpsl')


class TPSLSyncer:
    """TP/SL 订单同步器

    检查止盈止损订单是否已触发：
    - 止盈 (TP): 优先检查限价单 (tp_order_id)，其次条件单 (tp_algo_id)
    - 止损 (SL): 检查条件单 (sl_algo_id)

    支持按 source 过滤，实现 live 和 reverse 记录的独立同步。
    """

    def __init__(self, rest_client: 'BinanceRestClient',
                 record_service: 'RecordService'):
        """初始化

        Args:
            rest_client: Binance REST 客户端
            record_service: 记录服务
        """
        self.rest_client = rest_client
        self.record_service = record_service

    def sync(self, source: Optional[str] = None) -> Set[str]:
        """同步 TP/SL 订单状态

        Args:
            source: 过滤来源 ('live', 'reverse' 或 None 表示全部)

        Returns:
            活跃的条件单 ID 集合（用于孤儿清理）
        """
        try:
            open_records = self.record_service.get_open_records(source=source)
            if not open_records:
                return set()

            api_algo_orders = self.rest_client.get_algo_open_orders()
            if api_algo_orders is None:
                logger.warning("[TPSLSyncer] ⚠️ 查询条件单失败（可能限流），跳过本次同步")
                return set()

            active_algo_ids = {str(o.get('algoId')) for o in api_algo_orders}

            for record in open_records:
                self._check_record_tp_sl(record, active_algo_ids)

            return active_algo_ids

        except Exception as e:
            logger.error(f"[TPSLSyncer] 同步失败: {e}")
            return set()

    def _check_record_tp_sl(self, record: 'TradeRecord', active_algo_ids: Set[str]):
        """检查单条记录的 TP/SL 状态"""
        tp_triggered = False
        sl_triggered = False

        if record.tp_order_id:
            tp_triggered = self._check_tp_limit_order(record)
        elif record.tp_algo_id:
            if record.tp_algo_id not in active_algo_ids:
                logger.info(f"[TPSLSyncer] 🔄 止盈条件单已触发/取消: {record.symbol} algoId={record.tp_algo_id}")
                tp_triggered = True

        if record.sl_algo_id and record.sl_algo_id not in active_algo_ids:
            logger.info(f"[TPSLSyncer] 🔄 止损条件单已触发/取消: {record.symbol} algoId={record.sl_algo_id}")
            sl_triggered = True

        if tp_triggered and not sl_triggered:
            self._handle_tp_triggered(record)
        elif sl_triggered and not tp_triggered:
            self._handle_sl_triggered(record)
        elif tp_triggered and sl_triggered:
            logger.warning(f"[TPSLSyncer] ⚠️ TP/SL 同时消失: {record.symbol}")
            self.record_service.clear_tpsl_ids(record.id)

    def _check_tp_limit_order(self, record: 'TradeRecord') -> bool:
        """检查止盈限价单状态"""
        try:
            order_status = self.rest_client.get_order(record.symbol, record.tp_order_id)
            if order_status and order_status.get('status') == 'FILLED':
                logger.info(f"[TPSLSyncer] 🔄 止盈限价单已成交: {record.symbol} orderId={record.tp_order_id}")
                return True
            elif order_status and order_status.get('status') in ('CANCELED', 'EXPIRED'):
                logger.warning(f"[TPSLSyncer] ⚠️ 止盈限价单已取消/过期: {record.symbol}")
                self.record_service.update_record_tpsl_ids(record.id, tp_order_id=None)
        except Exception as e:
            logger.warning(f"[TPSLSyncer] 查询止盈限价单失败: {record.symbol} error={e}")
        return False

    def _handle_tp_triggered(self, record: 'TradeRecord'):
        """处理止盈触发

        尝试通过 tp_order_id 或 API 获取实际成交价格和手续费。
        """
        close_price = self._get_mark_price(record.symbol, record.tp_price)
        logger.info(f"[TPSLSyncer] 🎯 止盈触发: {record.symbol} @ {close_price}")

        self.record_service.cancel_remaining_tpsl(record, 'TP')

        exit_commission = 0.0
        realized_pnl = None
        avg_price = close_price

        if record.tp_order_id:
            exit_info = self.record_service.fetch_exit_info(record.symbol, record.tp_order_id)
            if exit_info.get('close_price'):
                avg_price = exit_info['close_price']
            exit_commission = exit_info.get('exit_commission', 0.0)
            realized_pnl = exit_info.get('realized_pnl')
            if exit_commission > 0:
                logger.info(f"[TPSLSyncer] 📊 止盈手续费: {exit_commission:.6f} USDT")

        self.record_service.close_record(
            record_id=record.id,
            close_price=avg_price,
            close_reason='TP_CLOSED',
            exit_commission=exit_commission,
            realized_pnl=realized_pnl
        )

    def _handle_sl_triggered(self, record: 'TradeRecord'):
        """处理止损触发

        Note:
            止损用的是条件单(sl_algo_id)，触发后会生成市价单。
            在兜底同步中，我们没有这个市价单ID（WebSocket 事件可能丢失了）。
            因此无法精确获取 exit_commission，只能让 close_record 本地计算 PnL。
            这是兜底机制的已知限制，主要流程仍依赖 WebSocket 事件的 AlgoOrderHandler。
        """
        close_price = self._get_mark_price(record.symbol, record.sl_price)
        logger.info(f"[TPSLSyncer] 🛑 止损触发: {record.symbol} @ {close_price}")

        self.record_service.cancel_remaining_tpsl(record, 'SL')

        self.record_service.close_record(
            record_id=record.id,
            close_price=close_price,
            close_reason=RecordStatus.SL_CLOSED.value,
            exit_commission=0.0,
            realized_pnl=None
        )

    def _get_mark_price(self, symbol: str, fallback: Optional[float]) -> float:
        """获取标记价格"""
        try:
            data = self.rest_client.get_mark_price(symbol)
            return float(data.get('markPrice', fallback or 0))
        except Exception:
            return fallback or 0
