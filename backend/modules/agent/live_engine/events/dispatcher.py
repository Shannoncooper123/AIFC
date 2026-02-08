"""事件分发器：分发 WebSocket 用户数据流事件"""
from typing import Any, Dict

from modules.monitor.utils.logger import get_logger

logger = get_logger('live_engine.event_dispatcher')


class EventDispatcher:
    """事件分发器

    职责：
    - 接收 WebSocket 用户数据流事件
    - 分发到对应的处理器

    事件类型：
    - ACCOUNT_UPDATE: 账户余额和持仓变化
    - ORDER_TRADE_UPDATE: 普通订单状态变化
    - ALGO_UPDATE: 条件单（策略单）状态变化
    """

    def __init__(self, account_handler, order_handler, algo_order_handler=None):
        """初始化

        Args:
            account_handler: ACCOUNT_UPDATE 处理器
            order_handler: ORDER_TRADE_UPDATE 处理器
            algo_order_handler: ALGO_UPDATE 处理器（可选）
        """
        self.account_handler = account_handler
        self.order_handler = order_handler
        self.algo_order_handler = algo_order_handler

    def handle_event(self, event_type: str, data: Dict[str, Any]):
        """处理用户数据流事件

        Args:
            event_type: 事件类型
            data: 事件数据
        """
        if event_type == 'ORDER_TRADE_UPDATE':
            order_info = data.get('o', {})
            symbol = order_info.get('s', '')
            status = order_info.get('X', '')
            logger.debug(f"[EventDispatcher] 收到 ORDER_TRADE_UPDATE: {symbol} status={status}")
        elif event_type == 'ALGO_UPDATE':
            order_info = data.get('o', {})
            symbol = order_info.get('s', '')
            status = order_info.get('X', '')
            algo_id = order_info.get('aid', '')
            logger.debug(f"[EventDispatcher] 收到 ALGO_UPDATE: {symbol} status={status} algoId={algo_id}")

        if event_type == 'ACCOUNT_UPDATE':
            self.account_handler.handle(data)
        elif event_type == 'ORDER_TRADE_UPDATE':
            self.order_handler.handle(data)
        elif event_type == 'ALGO_UPDATE':
            if self.algo_order_handler:
                self.algo_order_handler.handle(data)
        else:
            logger.debug(f"未处理的事件类型: {event_type}")
