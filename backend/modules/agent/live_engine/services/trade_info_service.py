"""成交信息服务

统一管理从 Binance API 获取订单成交信息的逻辑。

职责：
- 通过 GET /fapi/v1/order 获取订单的平均成交价
- 通过 GET /fapi/v1/userTrades 获取手续费和已实现盈亏（仅平仓时需要）
- 提供开仓/平仓信息查询接口

接口选择说明：
- 平均成交价：使用 GET /fapi/v1/order (权重=1)，直接返回 avgPrice
- 手续费/盈亏：使用 GET /fapi/v1/userTrades (权重=5)，仅在需要时调用
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

    统一管理所有成交信息的获取。
    """

    def __init__(self, rest_client: 'BinanceRestClient'):
        """初始化

        Args:
            rest_client: Binance REST 客户端
        """
        self.rest_client = rest_client

    def get_order_avg_price(self, symbol: str, order_id: int) -> Optional[float]:
        """获取订单的平均成交价

        使用 GET /fapi/v1/order 接口，权重=1，直接返回 avgPrice。

        Args:
            symbol: 交易对
            order_id: Binance 订单 ID

        Returns:
            平均成交价，获取失败返回 None
        """
        try:
            order_info = self.rest_client.get_order(symbol, order_id=order_id)
            if order_info:
                avg_price = float(order_info.get('avgPrice', 0) or 0)
                if avg_price > 0:
                    logger.debug(f"[TradeInfoService] 订单 {order_id} avgPrice={avg_price}")
                    return avg_price
            return None
        except Exception as e:
            logger.warning(f"[TradeInfoService] 获取订单失败: {symbol} orderId={order_id} error={e}")
            return None

    def fetch_trades_by_order_id(self, symbol: str, order_id: int) -> List[Dict]:
        """获取订单的原始成交记录

        使用 GET /fapi/v1/userTrades 接口，权重=5。
        仅在需要手续费和已实现盈亏时调用。

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
            logger.warning(f"[TradeInfoService] 获取成交记录失败: {symbol} orderId={order_id} error={e}")
            return []

    def calculate_commission_and_pnl(self, trades: List[Dict]) -> Dict[str, float]:
        """从成交记录计算手续费和已实现盈亏

        Args:
            trades: 原始成交记录列表

        Returns:
            {'commission': float, 'realized_pnl': float}
        """
        if not trades:
            return {'commission': 0.0, 'realized_pnl': 0.0}

        total_commission = sum(float(t.get('commission', 0)) for t in trades)
        realized_pnl = sum(float(t.get('realizedPnl', 0)) for t in trades)

        return {
            'commission': total_commission,
            'realized_pnl': realized_pnl
        }

    def get_entry_info(self, symbol: str, order_id: int) -> EntryInfo:
        """获取开仓信息

        开仓时只需要平均成交价，手续费可选。
        使用 GET /fapi/v1/order 获取 avgPrice (权重=1)。

        Args:
            symbol: 交易对
            order_id: 开仓订单 ID

        Returns:
            开仓信息（价格、手续费）
        """
        avg_price = self.get_order_avg_price(symbol, order_id)

        commission = 0.0
        trades = self.fetch_trades_by_order_id(symbol, order_id)
        if trades:
            fee_info = self.calculate_commission_and_pnl(trades)
            commission = fee_info['commission']

        return EntryInfo(
            avg_price=avg_price,
            commission=commission
        )

    def get_exit_info(self, symbol: str, order_id: int) -> ExitInfo:
        """获取平仓信息

        平仓时需要平均成交价、手续费和已实现盈亏。
        使用 GET /fapi/v1/order 获取 avgPrice (权重=1)，
        使用 GET /fapi/v1/userTrades 获取手续费和盈亏 (权重=5)。

        Args:
            symbol: 交易对
            order_id: 平仓订单 ID

        Returns:
            平仓信息（价格、手续费、已实现盈亏）
        """
        close_price = self.get_order_avg_price(symbol, order_id)

        exit_commission = 0.0
        realized_pnl = 0.0

        trades = self.fetch_trades_by_order_id(symbol, order_id)
        if trades:
            fee_info = self.calculate_commission_and_pnl(trades)
            exit_commission = fee_info['commission']
            realized_pnl = fee_info['realized_pnl']

        return ExitInfo(
            close_price=close_price,
            exit_commission=exit_commission,
            realized_pnl=realized_pnl
        )

    def get_trade_summary(self, symbol: str, order_id: int) -> TradeSummary:
        """获取订单的完整成交汇总

        同时获取平均成交价、成交量、手续费和已实现盈亏。

        Args:
            symbol: 交易对
            order_id: Binance 订单 ID

        Returns:
            成交汇总
        """
        avg_price = self.get_order_avg_price(symbol, order_id)

        trades = self.fetch_trades_by_order_id(symbol, order_id)
        if not trades:
            return TradeSummary(
                avg_price=avg_price,
                total_qty=0.0,
                total_commission=0.0,
                realized_pnl=0.0
            )

        total_qty = sum(float(t.get('qty', 0)) for t in trades)
        fee_info = self.calculate_commission_and_pnl(trades)

        return TradeSummary(
            avg_price=avg_price,
            total_qty=total_qty,
            total_commission=fee_info['commission'],
            realized_pnl=fee_info['realized_pnl']
        )
