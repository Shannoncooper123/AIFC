"""关联订单数据访问层

负责 Order 和 Trade 的 CRUD 操作和持久化。
Order 关联到 TradeRecord，Trade 关联到 Order。

数据层次结构:
- TradeRecord (持仓) → 关联多个 Order (订单)
- Order (订单) → 关联多个 Trade (成交)
"""

import threading
import uuid
from datetime import datetime
from typing import Callable, Dict, List, Optional, Set

from modules.agent.live_engine.core.models import (
    Order,
    OrderPurpose,
    OrderStatus,
    Trade,
)
from modules.agent.live_engine.core.persistence import JsonStateManager
from modules.monitor.utils.logger import get_logger

logger = get_logger('live_engine.linked_order_repository')


def _get_default_state_file() -> str:
    """从配置文件获取默认状态文件路径"""
    try:
        from modules.config.settings import get_config
        config = get_config()
        persistence = config.get('agent', {}).get('persistence', {})
        return persistence.get('linked_orders_path', 'modules/data/linked_orders.json')
    except Exception as e:
        logger.warning(f"获取配置路径失败，使用默认值: {e}")
        return 'modules/data/linked_orders.json'


class LinkedOrderRepository:
    """关联订单数据仓库

    职责：
    - Order 和 Trade 的 CRUD 操作
    - 数据持久化（使用 JsonStateManager）
    - 按条件查询和过滤
    - 维护 Order-Trade 和 Record-Order 的关系

    与 OrderRepository 的区别：
    - OrderRepository: 管理 PendingOrder（待触发的入场订单）
    - LinkedOrderRepository: 管理 Order（已关联到 TradeRecord 的订单）和 Trade（成交记录）
    """

    def __init__(self, state_file: Optional[str] = None):
        """初始化

        Args:
            state_file: 持久化文件路径（可选，默认从配置文件读取）
        """
        self._lock = threading.RLock()
        file_path = state_file or _get_default_state_file()
        self._state_manager = JsonStateManager(file_path)

        self._orders: Dict[str, Order] = {}
        self._trades: Dict[str, Trade] = {}

        self._binance_order_id_index: Dict[int, str] = {}
        self._binance_algo_id_index: Dict[str, str] = {}
        self._binance_trade_id_index: Dict[int, str] = {}
        self._record_id_index: Dict[str, Set[str]] = {}

        self._on_change_callbacks: List[Callable[[], None]] = []

        logger.info(f"[LinkedOrderRepository] 使用存储文件: {file_path}")
        self._load_state()

    def _load_state(self):
        """从文件加载状态"""
        data = self._state_manager.load()

        for order_data in data.get('orders', []):
            try:
                order = Order.from_dict(order_data)
                self._orders[order.id] = order
                self._build_order_indexes(order)
            except Exception as e:
                logger.warning(f"[LinkedOrderRepository] 加载订单失败: {e}")

        for trade_data in data.get('trades', []):
            try:
                trade = Trade.from_dict(trade_data)
                self._trades[trade.id] = trade
                if trade.binance_trade_id:
                    self._binance_trade_id_index[trade.binance_trade_id] = trade.id
            except Exception as e:
                logger.warning(f"[LinkedOrderRepository] 加载成交记录失败: {e}")

        logger.info(f"[LinkedOrderRepository] 已加载 {len(self._orders)} 个订单, {len(self._trades)} 条成交记录")

    def _build_order_indexes(self, order: Order):
        """构建订单索引"""
        if order.binance_order_id:
            self._binance_order_id_index[order.binance_order_id] = order.id
        if order.binance_algo_id:
            self._binance_algo_id_index[order.binance_algo_id] = order.id
        if order.record_id:
            if order.record_id not in self._record_id_index:
                self._record_id_index[order.record_id] = set()
            self._record_id_index[order.record_id].add(order.id)

    def _remove_order_indexes(self, order: Order):
        """移除订单索引"""
        if order.binance_order_id and order.binance_order_id in self._binance_order_id_index:
            del self._binance_order_id_index[order.binance_order_id]
        if order.binance_algo_id and order.binance_algo_id in self._binance_algo_id_index:
            del self._binance_algo_id_index[order.binance_algo_id]
        if order.record_id and order.record_id in self._record_id_index:
            self._record_id_index[order.record_id].discard(order.id)
            if not self._record_id_index[order.record_id]:
                del self._record_id_index[order.record_id]

    def _save_state(self):
        """保存状态到文件"""
        data = {
            'orders': [order.to_dict() for order in self._orders.values()],
            'trades': [trade.to_dict() for trade in self._trades.values()],
            'updated_at': datetime.now().isoformat()
        }

        self._state_manager.save(data)

    def add_order(self, order: Order) -> Order:
        """添加订单

        Args:
            order: 订单对象

        Returns:
            添加的订单
        """
        with self._lock:
            self._orders[order.id] = order
            self._build_order_indexes(order)
            self._save_state()
            logger.debug(f"[LinkedOrderRepository] 添加订单: {order.id} symbol={order.symbol}")
            return order

    def get_orders_by_record_id(self, record_id: str) -> List[Order]:
        """获取持仓关联的所有订单

        Args:
            record_id: TradeRecord ID

        Returns:
            订单列表
        """
        order_ids = self._record_id_index.get(record_id, set())
        return [self._orders[oid] for oid in order_ids if oid in self._orders]

    def get_order_by_binance_id(self, binance_order_id: int) -> Optional[Order]:
        """根据 Binance 普通订单 ID 获取订单

        通过 _binance_order_id_index 索引快速查找订单。

        Args:
            binance_order_id: Binance 返回的普通订单 ID

        Returns:
            订单对象，不存在返回 None
        """
        local_id = self._binance_order_id_index.get(binance_order_id)
        if local_id:
            return self._orders.get(local_id)
        return None

    def get_order_by_binance_algo_id(self, binance_algo_id: str) -> Optional[Order]:
        """根据 Binance 条件单 ID 获取订单

        通过 _binance_algo_id_index 索引快速查找订单。

        Args:
            binance_algo_id: Binance 返回的条件单 ID（algoId）

        Returns:
            订单对象，不存在返回 None
        """
        local_id = self._binance_algo_id_index.get(binance_algo_id)
        if local_id:
            return self._orders.get(local_id)
        return None

    def get_open_orders(self) -> List[Order]:
        """获取所有挂单状态的订单

        Returns:
            挂单列表
        """
        return [o for o in self._orders.values() if o.is_open]

    def get_open_limit_orders(self) -> List[Order]:
        """获取所有挂单状态的限价单

        Returns:
            限价单列表
        """
        return [o for o in self._orders.values() if o.is_open and o.is_limit_order]

    def get_open_algo_orders(self) -> List[Order]:
        """获取所有挂单状态的条件单

        Returns:
            条件单列表
        """
        return [o for o in self._orders.values() if o.is_open and o.is_algo_order]

    def update_order(self, order_id: str, **kwargs) -> Optional[Order]:
        """更新订单

        Args:
            order_id: 本地订单 ID
            **kwargs: 要更新的字段

        Returns:
            更新后的订单，不存在返回 None
        """
        with self._lock:
            order = self._orders.get(order_id)
            if not order:
                return None

            old_binance_id = order.binance_order_id
            old_algo_id = order.binance_algo_id
            old_record_id = order.record_id

            for key, value in kwargs.items():
                if hasattr(order, key):
                    setattr(order, key, value)

            order.updated_at = datetime.now().isoformat()

            if old_binance_id != order.binance_order_id:
                if old_binance_id and old_binance_id in self._binance_order_id_index:
                    del self._binance_order_id_index[old_binance_id]
                if order.binance_order_id:
                    self._binance_order_id_index[order.binance_order_id] = order.id

            if old_algo_id != order.binance_algo_id:
                if old_algo_id and old_algo_id in self._binance_algo_id_index:
                    del self._binance_algo_id_index[old_algo_id]
                if order.binance_algo_id:
                    self._binance_algo_id_index[order.binance_algo_id] = order.id

            if old_record_id != order.record_id:
                if old_record_id and old_record_id in self._record_id_index:
                    self._record_id_index[old_record_id].discard(order.id)
                if order.record_id:
                    if order.record_id not in self._record_id_index:
                        self._record_id_index[order.record_id] = set()
                    self._record_id_index[order.record_id].add(order.id)

            self._save_state()
            return order

    def add_trade(self, trade: Trade) -> Trade:
        """添加成交记录

        Args:
            trade: 成交记录对象

        Returns:
            添加的成交记录
        """
        with self._lock:
            self._trades[trade.id] = trade
            if trade.binance_trade_id:
                self._binance_trade_id_index[trade.binance_trade_id] = trade.id

            if trade.order_id and trade.order_id in self._orders:
                order = self._orders[trade.order_id]
                if trade not in order.trades:
                    order.trades.append(trade)
                    order.aggregate_trades()

            self._save_state()
            logger.debug(f"[LinkedOrderRepository] 添加成交: {trade.id} trade_id={trade.binance_trade_id}")
            return trade

    def get_trade_by_binance_id(self, binance_trade_id: int) -> Optional[Trade]:
        """根据 Binance 成交 ID 获取成交记录

        Args:
            binance_trade_id: Binance 成交 ID

        Returns:
            成交记录，不存在返回 None
        """
        local_id = self._binance_trade_id_index.get(binance_trade_id)
        if local_id:
            return self._trades.get(local_id)
        return None

    def trade_exists(self, binance_trade_id: int) -> bool:
        """检查成交记录是否已存在

        Args:
            binance_trade_id: Binance 成交 ID

        Returns:
            是否存在
        """
        return binance_trade_id in self._binance_trade_id_index

    def create_order(
        self,
        record_id: Optional[str],
        symbol: str,
        purpose: OrderPurpose,
        side: str,
        position_side: str,
        quantity: float,
        price: float = 0.0,
        stop_price: float = 0.0,
        binance_order_id: Optional[int] = None,
        binance_algo_id: Optional[str] = None,
        order_type=None,
        reduce_only: bool = False,
    ) -> Order:
        """创建并添加新订单

        Args:
            record_id: 关联的 TradeRecord ID
            symbol: 交易对
            purpose: 订单用途
            side: 方向 (BUY/SELL)
            position_side: 持仓方向 (LONG/SHORT)
            quantity: 数量
            price: 委托价格
            stop_price: 触发价格
            binance_order_id: Binance 普通订单 ID
            binance_algo_id: Binance 条件单 ID
            order_type: 订单类型
            reduce_only: 是否只减仓

        Returns:
            创建的订单
        """
        from modules.agent.live_engine.core.models import OrderType

        if order_type is None:
            if binance_algo_id:
                order_type = OrderType.STOP_MARKET
            else:
                order_type = OrderType.LIMIT if price > 0 else OrderType.MARKET

        order = Order(
            id=str(uuid.uuid4()),
            record_id=record_id,
            symbol=symbol,
            binance_order_id=binance_order_id,
            binance_algo_id=binance_algo_id,
            order_type=order_type,
            purpose=purpose,
            status=OrderStatus.NEW,
            side=side,
            position_side=position_side,
            price=price,
            stop_price=stop_price,
            quantity=quantity,
            reduce_only=reduce_only,
        )

        return self.add_order(order)

    def aggregate_commission_for_record(self, record_id: str) -> Dict[str, float]:
        """聚合持仓的手续费

        Args:
            record_id: TradeRecord ID

        Returns:
            {entry_commission, exit_commission, total_commission}
        """
        orders = self.get_orders_by_record_id(record_id)

        entry_commission = 0.0
        exit_commission = 0.0

        for order in orders:
            if order.purpose == OrderPurpose.ENTRY:
                entry_commission += order.commission
            else:
                exit_commission += order.commission

        return {
            'entry_commission': entry_commission,
            'exit_commission': exit_commission,
            'total_commission': entry_commission + exit_commission,
        }
