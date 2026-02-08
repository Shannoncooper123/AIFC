"""成交信息服务

统一管理从 Binance API 获取成交记录（Trades）的逻辑。

职责：
- 获取订单的成交记录
- 计算成交汇总（加权平均价、手续费、已实现盈亏）
- 提供开仓/平仓信息查询接口
"""
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from modules.monitor.utils.logger import get_logger

if TYPE_CHECKING:
    from modules.monitor.clients.binance_rest import BinanceRestClient

logger = get_logger('live_engine.trade_info_service')


@dataclass
class TradeSummary:
    """成交汇总"""
    avg_price: Optional[float]
    total_qty: float
    total_commission: float
    realized_pnl: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            'avg_price': self.avg_price,
            'total_qty': self.total_qty,
            'total_commission': self.total_commission,
            'realized_pnl': self.realized_pnl
        }


@dataclass
class EntryInfo:
    """开仓信息"""
    avg_price: Optional[float]
    commission: float


@dataclass
class ExitInfo:
    """平仓信息"""
    close_price: Optional[float]
    exit_commission: float
    realized_pnl: float


class TradeInfoService:
    """成交信息服务

    统一管理所有成交信息的获取和计算。
    """

    def __init__(self, rest_client: 'BinanceRestClient'):
        """初始化

        Args:
            rest_client: Binance REST 客户端
        """
        self.rest_client = rest_client

    def fetch_trades_by_order_id(
        self,
        symbol: str,
        order_id: int
    ) -> List[Dict]:
        """获取订单的原始成交记录

        Args:
            symbol: 交易对
            order_id: Binance 订单 ID

        Returns:
            原始成交记录列表
        """
        try:
            trades = self.rest_client.get_user_trades(symbol=symbol, order_id=order_id)
            return trades if trades else []
        except Exception as e:
            logger.warning(f"[TradeInfoService] 获取成交失败: {symbol} orderId={order_id} error={e}")
            return []

    def calculate_summary(self, trades: List[Dict]) -> TradeSummary:
        """计算成交汇总

        Args:
            trades: 原始成交记录列表

        Returns:
            成交汇总
        """
        if not trades:
            return TradeSummary(
                avg_price=None,
                total_qty=0.0,
                total_commission=0.0,
                realized_pnl=0.0
            )

        total_qty = sum(float(t.get('qty', 0)) for t in trades)
        total_value = sum(float(t.get('price', 0)) * float(t.get('qty', 0)) for t in trades)
        total_commission = sum(float(t.get('commission', 0)) for t in trades)
        realized_pnl = sum(float(t.get('realizedPnl', 0)) for t in trades)

        avg_price = total_value / total_qty if total_qty > 0 else None

        return TradeSummary(
            avg_price=avg_price,
            total_qty=total_qty,
            total_commission=total_commission,
            realized_pnl=realized_pnl
        )

    def get_trade_summary(self, symbol: str, order_id: int) -> TradeSummary:
        """获取订单的成交汇总

        Args:
            symbol: 交易对
            order_id: Binance 订单 ID

        Returns:
            成交汇总
        """
        trades = self.fetch_trades_by_order_id(symbol, order_id)
        return self.calculate_summary(trades)

    def get_entry_info(self, symbol: str, order_id: int) -> EntryInfo:
        """获取开仓信息

        Args:
            symbol: 交易对
            order_id: 开仓订单 ID

        Returns:
            开仓信息（价格、手续费）
        """
        summary = self.get_trade_summary(symbol, order_id)
        return EntryInfo(
            avg_price=summary.avg_price,
            commission=summary.total_commission
        )

    def get_exit_info(self, symbol: str, order_id: int) -> ExitInfo:
        """获取平仓信息

        Args:
            symbol: 交易对
            order_id: 平仓订单 ID

        Returns:
            平仓信息（价格、手续费、已实现盈亏）
        """
        summary = self.get_trade_summary(symbol, order_id)
        return ExitInfo(
            close_price=summary.avg_price,
            exit_commission=summary.total_commission,
            realized_pnl=summary.realized_pnl
        )
