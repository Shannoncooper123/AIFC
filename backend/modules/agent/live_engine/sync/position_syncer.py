"""持仓同步器

同步本地记录与 Binance 实际持仓状态。
支持按 source 过滤，可同时服务 live 和 reverse 两种来源。
"""

from typing import TYPE_CHECKING, Any, Dict, Optional

from modules.monitor.utils.logger import get_logger

if TYPE_CHECKING:
    from modules.monitor.clients.binance_rest import BinanceRestClient

    from ..services.record_service import RecordService, TradeRecord

logger = get_logger('live_engine.sync.position')


class PositionSyncer:
    """持仓同步器

    检查本地开仓记录对应的 Binance 持仓是否存在，
    如果不存在则关闭本地记录并取消相关订单。

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

    def sync(self, source: Optional[str] = None) -> int:
        """同步持仓状态

        Args:
            source: 过滤来源 ('live', 'reverse' 或 None 表示全部)

        Returns:
            关闭的记录数量
        """
        try:
            open_records = self.record_service.get_open_records(source=source)
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
                        self.record_service.update_mark_price(
                            record.symbol, bn_pos['mark_price']
                        )
                else:
                    logger.warning(f"[PositionSyncer] ⚠️ 本地记录无对应持仓: {record.symbol} {position_side} source={record.source}")
                    self._close_orphan_record(record)
                    closed_count += 1

            return closed_count

        except Exception as e:
            logger.error(f"[PositionSyncer] 同步失败: {e}")
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
        close_price = self._get_mark_price(record.symbol, record.entry_price)

        self.record_service.cancel_remaining_tpsl(record, 'TP')
        self.record_service.cancel_remaining_tpsl(record, 'SL')

        self.record_service.close_record(
            record_id=record.id,
            close_price=close_price,
            close_reason='POSITION_CLOSED_EXTERNALLY'
        )
        logger.info(f"[PositionSyncer] 📕 记录已关闭: {record.symbol} @ {close_price} source={record.source} (外部平仓)")

    def _get_mark_price(self, symbol: str, fallback: float) -> float:
        """获取标记价格"""
        try:
            data = self.rest_client.get_mark_price(symbol)
            return float(data.get('markPrice', fallback))
        except Exception:
            return fallback
