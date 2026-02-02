"""事件分发器：分发 WebSocket 用户数据流事件"""
from typing import Dict, Any, Optional, Callable, List
from modules.monitor.utils.logger import get_logger

logger = get_logger('live_engine.event_dispatcher')


class EventDispatcher:
    """事件分发器
    
    职责：
    - 接收 WebSocket 用户数据流事件
    - 分发到对应的处理器
    - 支持注册额外的事件监听器（如 reverse_engine）
    """
    
    def __init__(self, account_handler, order_handler):
        """初始化
        
        Args:
            account_handler: ACCOUNT_UPDATE 处理器
            order_handler: ORDER_TRADE_UPDATE 处理器
        """
        self.account_handler = account_handler
        self.order_handler = order_handler
        self._extra_listeners: List[Callable[[str, Dict[str, Any]], None]] = []
    
    def register_listener(self, listener: Callable[[str, Dict[str, Any]], None]):
        """注册额外的事件监听器
        
        Args:
            listener: 监听器函数，接收 (event_type, data) 参数
        """
        if listener not in self._extra_listeners:
            self._extra_listeners.append(listener)
            logger.info(f"已注册额外事件监听器: {listener}")
    
    def unregister_listener(self, listener: Callable[[str, Dict[str, Any]], None]):
        """取消注册事件监听器
        
        Args:
            listener: 监听器函数
        """
        if listener in self._extra_listeners:
            self._extra_listeners.remove(listener)
            logger.info(f"已取消注册事件监听器: {listener}")
    
    def handle_event(self, event_type: str, data: Dict[str, Any]):
        """处理用户数据流事件
        
        Args:
            event_type: 事件类型
            data: 事件数据
        """
        # 记录收到的事件（便于调试）
        if event_type == 'ORDER_TRADE_UPDATE':
            order_info = data.get('o', {})
            symbol = order_info.get('s', '')
            status = order_info.get('X', '')
            logger.debug(f"[EventDispatcher] 收到 ORDER_TRADE_UPDATE: {symbol} status={status}")
        
        if event_type == 'ACCOUNT_UPDATE':
            self.account_handler.handle(data)
        elif event_type == 'ORDER_TRADE_UPDATE':
            self.order_handler.handle(data)
        else:
            logger.debug(f"未处理的事件类型: {event_type}")
        
        # 分发给额外监听器（如 reverse_engine）
        if self._extra_listeners:
            logger.debug(f"[EventDispatcher] 分发事件到 {len(self._extra_listeners)} 个额外监听器")
        
        for listener in self._extra_listeners:
            try:
                listener(event_type, data)
            except Exception as e:
                logger.error(f"额外监听器处理事件失败: {e}")
