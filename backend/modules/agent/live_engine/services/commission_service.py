"""统一手续费服务

负责从 Binance API 获取成交记录（Trades），聚合手续费到 Order，再聚合到 TradeRecord。

数据流:
1. WebSocket 收到订单成交事件
2. 调用 fetch_trades_for_order() 获取该订单的成交记录
3. 创建 Trade 对象并存储到 LinkedOrderRepository
4. Trade 自动聚合到 Order 的 commission 字段
5. 调用 aggregate_to_record() 将 Order 的手续费聚合到 TradeRecord
"""

from typing import TYPE_CHECKING, Dict, List, Optional

from modules.agent.live_engine.core.models import (
    Order,
    Trade,
)
from modules.monitor.utils.logger import get_logger

if TYPE_CHECKING:
    from modules.agent.live_engine.core.repositories import LinkedOrderRepository
    from modules.monitor.clients.binance_rest import BinanceRestClient

logger = get_logger('live_engine.commission_service')


class CommissionService:
    """统一手续费服务

    职责:
    - 从 Binance API 获取订单的成交记录
    - 创建 Trade 对象并存储
    - 聚合手续费到 Order
    - 聚合 Order 手续费到 TradeRecord
    """

    def __init__(
        self,
        rest_client: 'BinanceRestClient',
        linked_order_repo: 'LinkedOrderRepository',
    ):
        """初始化

        Args:
            rest_client: Binance REST 客户端
            linked_order_repo: 关联订单仓库
        """
        self.rest_client = rest_client
        self.linked_order_repo = linked_order_repo

    def fetch_trades_for_order(self, order: Order) -> List[Trade]:
        """获取订单的所有成交记录并存储

        从 Binance API 获取成交记录，创建 Trade 对象，
        存储到 LinkedOrderRepository，并自动聚合到 Order。

        Args:
            order: 订单对象（需要有 binance_order_id）

        Returns:
            成交记录列表
        """
        if not order.binance_order_id:
            logger.warning(f"[CommissionService] 订单无 binance_order_id，无法获取成交: order_id={order.id}")
            return []

        try:
            raw_trades = self.rest_client.get_user_trades(
                symbol=order.symbol,
                order_id=order.binance_order_id
            )
        except Exception as e:
            logger.error(f"[CommissionService] 获取成交记录失败: {order.symbol} "
                        f"orderId={order.binance_order_id} error={e}")
            return []

        if not raw_trades:
            logger.debug(f"[CommissionService] 订单无成交记录: {order.symbol} orderId={order.binance_order_id}")
            return []

        trades = []
        for raw_trade in raw_trades:
            binance_trade_id = int(raw_trade.get('id', 0))

            if self.linked_order_repo.trade_exists(binance_trade_id):
                existing_trade = self.linked_order_repo.get_trade_by_binance_id(binance_trade_id)
                if existing_trade:
                    trades.append(existing_trade)
                continue

            trade = Trade.from_binance(raw_trade, order.id)
            self.linked_order_repo.add_trade(trade)
            trades.append(trade)

            logger.debug(f"[CommissionService] 新成交记录: {order.symbol} "
                        f"trade_id={binance_trade_id} commission={trade.commission}")

        if trades:
            order.aggregate_trades()
            self.linked_order_repo.update_order(
                order.id,
                commission=order.commission,
                filled_qty=order.filled_qty,
                avg_filled_price=order.avg_filled_price,
                realized_pnl=order.realized_pnl
            )

            logger.info(f"[CommissionService] 订单成交汇总: {order.symbol} "
                       f"orderId={order.binance_order_id} trades={len(trades)} "
                       f"commission={order.commission:.6f}")

        return trades

    def fetch_trades_by_order_id(
        self,
        symbol: str,
        binance_order_id: int,
        order_id: Optional[str] = None
    ) -> Dict:
        """直接通过订单 ID 获取成交汇总

        不创建 Trade 对象，仅返回汇总信息。
        适用于临时查询手续费的场景。

        Args:
            symbol: 交易对
            binance_order_id: Binance 订单 ID
            order_id: 本地订单 ID（用于去重）

        Returns:
            汇总信息 {avg_price, total_commission, realized_pnl, total_qty}
        """
        try:
            raw_trades = self.rest_client.get_user_trades(
                symbol=symbol,
                order_id=binance_order_id
            )
        except Exception as e:
            logger.warning(f"[CommissionService] 获取成交失败: {symbol} "
                          f"orderId={binance_order_id} error={e}")
            return {'avg_price': None, 'total_commission': 0.0, 'realized_pnl': 0.0, 'total_qty': 0.0}

        return self._calculate_trade_summary(raw_trades)

    def _calculate_trade_summary(self, trades: List[Dict]) -> Dict:
        """计算成交汇总（加权平均价格、总手续费、已实现盈亏）

        Args:
            trades: 原始成交记录列表

        Returns:
            汇总信息 {avg_price, total_commission, realized_pnl, total_qty}
        """
        if not trades:
            return {'avg_price': None, 'total_commission': 0.0, 'realized_pnl': 0.0, 'total_qty': 0.0}

        total_qty = sum(float(t.get('qty', 0)) for t in trades)
        total_value = sum(float(t.get('price', 0)) * float(t.get('qty', 0)) for t in trades)
        total_commission = sum(float(t.get('commission', 0)) for t in trades)
        realized_pnl = sum(float(t.get('realizedPnl', 0)) for t in trades)

        avg_price = total_value / total_qty if total_qty > 0 else None

        return {
            'avg_price': avg_price,
            'total_commission': total_commission,
            'realized_pnl': realized_pnl,
            'total_qty': total_qty
        }

    def fetch_entry_commission(self, symbol: str, order_id: int) -> float:
        """获取开仓手续费

        Args:
            symbol: 交易对
            order_id: 开仓订单 ID

        Returns:
            手续费金额
        """
        summary = self.fetch_trades_by_order_id(symbol, order_id)
        return summary['total_commission']

    def fetch_exit_info(self, symbol: str, order_id: int) -> Dict:
        """获取平仓信息（价格、手续费、已实现盈亏）

        Args:
            symbol: 交易对
            order_id: 平仓订单 ID

        Returns:
            {close_price, exit_commission, realized_pnl}
        """
        summary = self.fetch_trades_by_order_id(symbol, order_id)
        return {
            'close_price': summary['avg_price'],
            'exit_commission': summary['total_commission'],
            'realized_pnl': summary['realized_pnl']
        }

    def aggregate_commission_for_record(self, record_id: str) -> Dict[str, float]:
        """聚合持仓的手续费

        从 LinkedOrderRepository 获取持仓关联的所有订单，
        按用途汇总手续费。

        Args:
            record_id: TradeRecord ID

        Returns:
            {entry_commission, exit_commission, total_commission}
        """
        return self.linked_order_repo.aggregate_commission_for_record(record_id)
