"""订单数据访问层

负责 PendingOrder 的 CRUD 操作和持久化。
"""

import threading
from typing import Dict, List, Optional

from modules.agent.live_engine.core.models import OrderKind, PendingOrder
from modules.agent.live_engine.core.persistence import JsonStateManager
from modules.monitor.utils.logger import get_logger

logger = get_logger('shared.order_repository')


def _get_default_state_file() -> str:
    """从配置文件获取默认状态文件路径"""
    try:
        from modules.config.settings import get_config
        config = get_config()
        persistence = config.get('agent', {}).get('persistence', {})
        return persistence.get('pending_orders_path', 'modules/data/pending_orders.json')
    except Exception as e:
        logger.warning(f"获取配置路径失败，使用默认值: {e}")
        return 'modules/data/pending_orders.json'


class OrderRepository:
    """待触发订单数据仓库

    职责：
    - PendingOrder 的 CRUD 操作
    - 数据持久化（使用 JsonStateManager）
    - 按条件查询和过滤

    不包含业务逻辑（如下单到 Binance），业务逻辑由 OrderManager 处理。
    """

    def __init__(self, state_file: Optional[str] = None):
        """初始化

        Args:
            state_file: 持久化文件路径（可选，默认从配置文件读取）
        """
        self._lock = threading.RLock()
        file_path = state_file or _get_default_state_file()
        self._state_manager = JsonStateManager(file_path)
        self._orders: Dict[str, PendingOrder] = {}

        logger.info(f"[OrderRepository] 使用存储文件: {file_path}")
        self._load_state()

    def _load_state(self):
        """从文件加载状态"""
        data = self._state_manager.load()

        for order_data in data.get('conditional_orders', []):
            try:
                order = PendingOrder.from_dict(order_data)
                self._orders[order.id] = order
            except Exception as e:
                logger.warning(f"[OrderRepository] 加载条件单失败: {e}")

        for order_data in data.get('limit_orders', []):
            try:
                order = PendingOrder.from_dict(order_data)
                self._orders[order.id] = order
            except Exception as e:
                logger.warning(f"[OrderRepository] 加载限价单失败: {e}")

        logger.info(f"[OrderRepository] 已加载 {len(self._orders)} 个订单")

    def _save_state(self):
        """保存状态到文件"""
        conditional_orders = []
        limit_orders = []

        for order in self._orders.values():
            if order.order_kind == OrderKind.CONDITIONAL_ORDER:
                conditional_orders.append(order.to_dict())
            else:
                limit_orders.append(order.to_dict())

        self._state_manager.save({
            'conditional_orders': conditional_orders,
            'limit_orders': limit_orders
        })

    def get(self, order_id: str) -> Optional[PendingOrder]:
        """获取订单"""
        with self._lock:
            return self._orders.get(order_id)

    def get_all(self, source: Optional[str] = None) -> List[PendingOrder]:
        """获取所有订单"""
        with self._lock:
            orders = list(self._orders.values())
            if source:
                orders = [o for o in orders if o.source == source]
            return orders

    def find_by_algo_id(self, algo_id: str) -> Optional[PendingOrder]:
        """按条件单 ID 查找"""
        with self._lock:
            for order in self._orders.values():
                if order.algo_id == algo_id:
                    return order
            return None

    def find_by_order_id(self, order_id: int) -> Optional[PendingOrder]:
        """按限价单 ID 查找"""
        with self._lock:
            for order in self._orders.values():
                if order.order_id == order_id:
                    return order
            return None

    def save(self, order: PendingOrder) -> None:
        """保存或更新订单"""
        with self._lock:
            self._orders[order.id] = order
            self._save_state()
            logger.info(f"[OrderRepository] 保存订单: {order.id} ({order.order_kind.value})")

    def get_by_source(self, source: str) -> List[PendingOrder]:
        """按来源获取订单"""
        with self._lock:
            return [o for o in self._orders.values() if o.source == source]

    def delete(self, order_id: str) -> bool:
        """删除订单"""
        with self._lock:
            if order_id in self._orders:
                del self._orders[order_id]
                self._save_state()
                logger.info(f"[OrderRepository] 删除订单: {order_id}")
                return True
            return False
