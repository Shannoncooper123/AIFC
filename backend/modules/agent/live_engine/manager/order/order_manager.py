"""挂单管理器

职责：
- 创建入场挂单（限价单/条件单）
- 取消挂单
- 挂单状态查询

管理待触发的入场订单生命周期。
"""
from typing import TYPE_CHECKING, Any, Dict, Optional

from modules.agent.live_engine.config import get_trading_config_manager
from modules.agent.live_engine.core import ExchangeInfoCache
from modules.agent.live_engine.core.models import AlgoOrderStatus, OrderKind, PendingOrder
from modules.monitor.utils.logger import get_logger

if TYPE_CHECKING:
    from modules.agent.live_engine.core.repositories import OrderRepository
    from modules.agent.live_engine.manager.order.order_executor import OrderExecutor

logger = get_logger('live_engine.order_manager')


class OrderManager:
    """挂单管理器

    管理待触发的入场订单（限价单、条件单）。
    """

    def __init__(
        self,
        order_executor: 'OrderExecutor',
        order_repository: 'OrderRepository'
    ):
        """初始化

        Args:
            order_executor: 订单执行器
            order_repository: 订单仓库
        """
        self.order_executor = order_executor
        self.order_repository = order_repository

    def create_limit_order(
        self,
        symbol: str,
        side: str,
        limit_price: float,
        tp_price: Optional[float] = None,
        sl_price: Optional[float] = None,
        source: str = 'live',
        agent_side: Optional[str] = None
    ) -> Dict[str, Any]:
        """创建限价入场单

        根据配置计算数量，使用智能限价单下单。
        会根据当前价格自动选择使用限价单（Maker）或条件单（Taker）。

        Args:
            symbol: 交易对
            side: 方向（long/short 或 BUY/SELL）
            limit_price: 限价价格
            tp_price: 止盈价格（可选）
            sl_price: 止损价格（可选）
            source: 来源（live/reverse）
            agent_side: Agent 方向（可选）

        Returns:
            下单结果字典
        """
        try:
            config = get_trading_config_manager()
            margin = config.fixed_margin_usdt
            leverage = config.fixed_leverage

            quantity = (margin * leverage) / limit_price
            quantity = ExchangeInfoCache.format_quantity(symbol, quantity)

            self.order_executor.ensure_dual_position_mode()
            self.order_executor.ensure_leverage(symbol, leverage)

            result = self.order_executor.create_smart_limit_order(
                symbol=symbol,
                side=side,
                limit_price=limit_price,
                quantity=quantity,
                tp_price=tp_price,
                sl_price=sl_price,
                source=source,
                expiration_days=config.expiration_days
            )

            if result.get('error'):
                return {'success': False, 'error': result.get('error')}

            order_id = result.get('order_id')
            algo_id = result.get('algo_id')
            order_kind = OrderKind.LIMIT_ORDER if order_id else OrderKind.CONDITIONAL_ORDER

            pending_order = PendingOrder(
                id=f"LIMIT_{order_id}" if order_id else algo_id,
                symbol=symbol,
                side=side.lower(),
                trigger_price=limit_price,
                quantity=quantity,
                status=AlgoOrderStatus.NEW,
                order_kind=order_kind,
                tp_price=tp_price,
                sl_price=sl_price,
                leverage=leverage,
                margin_usdt=margin,
                order_id=order_id,
                algo_id=algo_id,
                source=source,
                agent_side=agent_side
            )

            if self.order_repository:
                self.order_repository.save(pending_order)

            logger.info(f"[OrderManager] ✅ 限价单创建成功: {symbol} {side} @ {limit_price} "
                       f"qty={quantity} kind={order_kind.value}")

            return {
                'success': True,
                'pending_order_id': pending_order.id,
                'order_id': order_id,
                'algo_id': algo_id,
                'symbol': symbol,
                'side': side,
                'limit_price': limit_price,
                'quantity': quantity,
                'tp_price': tp_price,
                'sl_price': sl_price,
                'order_kind': order_kind.value,
                'margin_usdt': margin,
                'leverage': leverage
            }

        except Exception as e:
            logger.error(f"[OrderManager] 创建限价单失败: {symbol} error={e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def cancel_pending_order(
        self,
        order_id: str,
        source: Optional[str] = None
    ) -> bool:
        """取消待触发的入场订单

        Args:
            order_id: 订单 ID（pending order id）
            source: 来源（可选，用于日志）

        Returns:
            是否成功取消
        """
        try:
            if not self.order_repository:
                logger.warning("[OrderManager] order_repository 未设置")
                return False

            order = self.order_repository.get(order_id)
            if not order:
                logger.warning(f"[OrderManager] 未找到待触发订单: {order_id}")
                return False

            if order.is_conditional_order and order.algo_id:
                self.order_executor.cancel_algo_order(order.symbol, order.algo_id)
            elif order.is_limit_order and order.order_id:
                self.order_executor.cancel_order(order.symbol, order.order_id)

            self.order_repository.remove(order_id)

            logger.info(f"[OrderManager] ✅ 取消待触发订单成功: {order_id} symbol={order.symbol}")
            return True

        except Exception as e:
            logger.error(f"[OrderManager] 取消待触发订单失败: {order_id} error={e}", exc_info=True)
            return False

    def get_pending_order(self, order_id: str) -> Optional[PendingOrder]:
        """获取待触发订单

        Args:
            order_id: 订单 ID

        Returns:
            PendingOrder 或 None
        """
        if not self.order_repository:
            return None
        return self.order_repository.get(order_id)

    def get_all_pending_orders(self, source: Optional[str] = None) -> list:
        """获取所有待触发订单

        Args:
            source: 来源过滤（可选）

        Returns:
            订单列表
        """
        if not self.order_repository:
            return []
        if source:
            return self.order_repository.get_by_source(source)
        return self.order_repository.get_all()

    def remove_pending_order(self, order_id: str) -> bool:
        """移除待触发订单（不撤单，仅从本地删除）

        Args:
            order_id: 订单 ID

        Returns:
            是否成功移除
        """
        if not self.order_repository:
            return False
        return self.order_repository.remove(order_id)
