"""订单数据访问层

负责 PendingOrder 的 CRUD 操作和持久化。
"""

import threading
from datetime import datetime
from typing import Dict, List, Optional, Callable
from modules.monitor.utils.logger import get_logger
from modules.agent.live_engine.core.persistence import JsonStateManager
from modules.agent.live_engine.core.models import PendingOrder, AlgoOrderStatus, OrderKind

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
        self._on_change_callbacks: List[Callable[[], None]] = []
        
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
        
        for callback in self._on_change_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"[OrderRepository] 回调失败: {e}")
    
    def on_change(self, callback: Callable[[], None]):
        """注册数据变更回调"""
        self._on_change_callbacks.append(callback)
    
    def create(
        self,
        id: str,
        symbol: str,
        side: str,
        trigger_price: float,
        quantity: float,
        order_kind: OrderKind = OrderKind.CONDITIONAL_ORDER,
        tp_price: Optional[float] = None,
        sl_price: Optional[float] = None,
        leverage: int = 10,
        margin_usdt: float = 50.0,
        order_id: Optional[int] = None,
        algo_id: Optional[str] = None,
        source: str = 'live',
        agent_order_id: Optional[str] = None,
        agent_limit_price: Optional[float] = None,
        agent_side: Optional[str] = None,
        extra_data: Optional[Dict] = None
    ) -> PendingOrder:
        """创建待触发订单
        
        Args:
            id: 唯一标识
            symbol: 交易对
            side: 方向
            trigger_price: 触发价格
            quantity: 数量
            order_kind: 订单类型
            tp_price: 止盈价
            sl_price: 止损价
            leverage: 杠杆
            margin_usdt: 保证金
            order_id: Binance 限价单 ID
            algo_id: Binance 条件单 ID
            source: 来源
            agent_order_id: Agent 订单 ID
            agent_limit_price: Agent 限价
            agent_side: Agent 方向
            extra_data: 额外数据
            
        Returns:
            创建的订单
        """
        order = PendingOrder(
            id=id,
            symbol=symbol,
            side=side,
            trigger_price=trigger_price,
            quantity=quantity,
            status=AlgoOrderStatus.NEW,
            order_kind=order_kind,
            tp_price=tp_price,
            sl_price=sl_price,
            leverage=leverage,
            margin_usdt=margin_usdt,
            order_id=order_id,
            algo_id=algo_id or (id if order_kind == OrderKind.CONDITIONAL_ORDER else None),
            source=source,
            agent_order_id=agent_order_id,
            agent_limit_price=agent_limit_price,
            agent_side=agent_side,
            extra_data=extra_data or {},
        )
        
        with self._lock:
            self._orders[order.id] = order
            self._save_state()
        
        logger.info(f"[OrderRepository] 创建订单: {id} {symbol} {side} @ {trigger_price} ({order_kind.value})")
        return order
    
    def get(self, order_id: str) -> Optional[PendingOrder]:
        """获取订单"""
        with self._lock:
            return self._orders.get(order_id)
    
    def get_by_binance_order_id(self, binance_order_id: int) -> Optional[PendingOrder]:
        """按 Binance 订单 ID 查找"""
        with self._lock:
            for order in self._orders.values():
                if order.order_id == binance_order_id:
                    return order
            return None
    
    def get_by_algo_id(self, algo_id: str) -> Optional[PendingOrder]:
        """按条件单 ID 查找"""
        with self._lock:
            for order in self._orders.values():
                if order.algo_id == algo_id:
                    return order
            return None
    
    def get_all(self, source: Optional[str] = None) -> List[PendingOrder]:
        """获取所有订单"""
        with self._lock:
            orders = list(self._orders.values())
            if source:
                orders = [o for o in orders if o.source == source]
            return orders
    
    def get_conditional_orders(self, source: Optional[str] = None) -> List[PendingOrder]:
        """获取所有条件单"""
        with self._lock:
            orders = [o for o in self._orders.values() if o.order_kind == OrderKind.CONDITIONAL_ORDER]
            if source:
                orders = [o for o in orders if o.source == source]
            return orders
    
    def get_limit_orders(self, source: Optional[str] = None) -> List[PendingOrder]:
        """获取所有限价单"""
        with self._lock:
            orders = [o for o in self._orders.values() if o.order_kind == OrderKind.LIMIT_ORDER]
            if source:
                orders = [o for o in orders if o.source == source]
            return orders
    
    def get_by_symbol(self, symbol: str, source: Optional[str] = None) -> List[PendingOrder]:
        """按交易对查找"""
        with self._lock:
            orders = [o for o in self._orders.values() if o.symbol == symbol]
            if source:
                orders = [o for o in orders if o.source == source]
            return orders
    
    def get_by_source(self, source: str) -> List[PendingOrder]:
        """按来源查找"""
        return self.get_all(source=source)
    
    def find_by_algo_id(self, algo_id: str) -> Optional[PendingOrder]:
        """按条件单 ID 查找（get_by_algo_id 的别名）"""
        return self.get_by_algo_id(algo_id)
    
    def find_by_order_id(self, order_id: int) -> Optional[PendingOrder]:
        """按限价单 ID 查找（get_by_binance_order_id 的别名）"""
        return self.get_by_binance_order_id(order_id)
    
    def update(self, order_id: str, **kwargs) -> Optional[PendingOrder]:
        """更新订单"""
        with self._lock:
            order = self._orders.get(order_id)
            if not order:
                return None
            
            for key, value in kwargs.items():
                if hasattr(order, key):
                    setattr(order, key, value)
            
            self._save_state()
            return order
    
    def mark_triggered(self, order_id: str, filled_price: float) -> Optional[PendingOrder]:
        """标记订单已触发"""
        with self._lock:
            order = self._orders.get(order_id)
            if not order:
                return None
            
            order.status = AlgoOrderStatus.TRIGGERED
            order.triggered_at = datetime.now().isoformat()
            order.filled_price = filled_price
            
            self._save_state()
            logger.info(f"[OrderRepository] 订单触发: {order_id} @ {filled_price}")
            return order
    
    def mark_filled(self, order_id: str, filled_price: float) -> Optional[PendingOrder]:
        """标记订单已成交"""
        with self._lock:
            order = self._orders.get(order_id)
            if not order:
                return None
            
            order.status = AlgoOrderStatus.FILLED
            order.filled_at = datetime.now().isoformat()
            order.filled_price = filled_price
            
            self._save_state()
            logger.info(f"[OrderRepository] 订单成交: {order_id} @ {filled_price}")
            return order
    
    def delete(self, order_id: str) -> bool:
        """删除订单"""
        with self._lock:
            if order_id in self._orders:
                del self._orders[order_id]
                self._save_state()
                logger.info(f"[OrderRepository] 删除订单: {order_id}")
                return True
            return False
    
    def delete_by_binance_order_id(self, binance_order_id: int) -> bool:
        """按 Binance 订单 ID 删除"""
        with self._lock:
            for order_id, order in list(self._orders.items()):
                if order.order_id == binance_order_id:
                    del self._orders[order_id]
                    self._save_state()
                    return True
            return False
    
    def count(self, source: Optional[str] = None, order_kind: Optional[OrderKind] = None) -> int:
        """统计订单数量"""
        with self._lock:
            orders = list(self._orders.values())
            if source:
                orders = [o for o in orders if o.source == source]
            if order_kind:
                orders = [o for o in orders if o.order_kind == order_kind]
            return len(orders)
