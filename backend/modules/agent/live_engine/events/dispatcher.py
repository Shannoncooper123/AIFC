"""事件分发器：分发 WebSocket 用户数据流事件"""
from typing import Dict, Any
from modules.monitor.utils.logger import get_logger

logger = get_logger('live_engine.event_dispatcher')


class EventDispatcher:
    """事件分发器
    
    职责：
    - 接收 WebSocket 用户数据流事件
    - 分发到对应的处理器
    """
    
    def __init__(self, account_handler, order_handler):
        """初始化
        
        Args:
            account_handler: ACCOUNT_UPDATE 处理器
            order_handler: ORDER_TRADE_UPDATE 处理器
        """
        self.account_handler = account_handler
        self.order_handler = order_handler
    
    def handle_event(self, event_type: str, data: Dict[str, Any]):
        """处理用户数据流事件
        
        Args:
            event_type: 事件类型
            data: 事件数据
        """
        if event_type == 'ACCOUNT_UPDATE':
            self.account_handler.handle(data)
        elif event_type == 'ORDER_TRADE_UPDATE':
            self.order_handler.handle(data)
        else:
            logger.debug(f"未处理的事件类型: {event_type}")

