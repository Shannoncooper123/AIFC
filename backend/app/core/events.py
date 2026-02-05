"""事件总线：用于服务间实时通信"""
import asyncio
import json
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from pydantic import BaseModel


logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """事件类型枚举"""
    SYSTEM_STATUS = "system_status"
    MONITOR_STATUS = "monitor_status"
    AGENT_STATUS = "agent_status"
    WORKFLOW_STATUS = "workflow_status"
    
    NEW_ALERT = "new_alert"
    POSITION_UPDATE = "position_update"
    TRADE_EXECUTED = "trade_executed"
    MARK_PRICE_UPDATE = "mark_price_update"
    
    CONFIG_UPDATED = "config_updated"
    
    LOG_MESSAGE = "log_message"
    ERROR = "error"


class Event(BaseModel):
    """事件模型"""
    type: EventType
    data: Dict[str, Any]
    timestamp: str = ""
    
    def __init__(self, **data):
        if "timestamp" not in data or not data["timestamp"]:
            data["timestamp"] = datetime.utcnow().isoformat() + "Z"
        super().__init__(**data)
    
    def to_json(self) -> str:
        """转换为JSON字符串"""
        return self.model_dump_json()


class EventBus:
    """事件总线单例"""
    _instance: Optional["EventBus"] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._subscribers: Dict[EventType, List[Callable]] = {}
        self._async_subscribers: Dict[EventType, List[Callable]] = {}
        self._websocket_queues: Set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
    
    def set_loop(self, loop: asyncio.AbstractEventLoop):
        """设置事件循环（用于跨线程发布）"""
        self._loop = loop
    
    def subscribe(self, event_type: EventType, callback: Callable) -> None:
        """订阅事件（同步回调）"""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)
    
    def subscribe_async(self, event_type: EventType, callback: Callable) -> None:
        """订阅事件（异步回调）"""
        if event_type not in self._async_subscribers:
            self._async_subscribers[event_type] = []
        self._async_subscribers[event_type].append(callback)
    
    def unsubscribe(self, event_type: EventType, callback: Callable) -> None:
        """取消订阅"""
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                cb for cb in self._subscribers[event_type] if cb != callback
            ]
        if event_type in self._async_subscribers:
            self._async_subscribers[event_type] = [
                cb for cb in self._async_subscribers[event_type] if cb != callback
            ]
    
    async def publish(self, event: Event) -> None:
        """发布事件"""
        logger.debug(f"发布事件: {event.type} - {event.data}")
        
        if event.type in self._subscribers:
            for callback in self._subscribers[event.type]:
                try:
                    callback(event)
                except Exception as e:
                    logger.error(f"同步事件回调错误: {e}")
        
        if event.type in self._async_subscribers:
            for callback in self._async_subscribers[event.type]:
                try:
                    await callback(event)
                except Exception as e:
                    logger.error(f"异步事件回调错误: {e}")
        
        async with self._lock:
            for queue in self._websocket_queues:
                try:
                    await queue.put(event)
                except Exception as e:
                    logger.error(f"WebSocket队列推送错误: {e}")
    
    def publish_sync(self, event: Event) -> None:
        """同步发布事件（用于非异步上下文）"""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.publish(event))
        except RuntimeError:
            # 如果在非异步线程中（如 ReverseEngine 线程），尝试使用主循环
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(self.publish(event), self._loop)
            
            # 执行同步回调
            if event.type in self._subscribers:
                for callback in self._subscribers[event.type]:
                    try:
                        callback(event)
                    except Exception as e:
                        logger.error(f"同步事件回调错误: {e}")
    
    async def register_websocket_queue(self, queue: asyncio.Queue) -> None:
        """注册WebSocket队列"""
        async with self._lock:
            self._websocket_queues.add(queue)
    
    async def unregister_websocket_queue(self, queue: asyncio.Queue) -> None:
        """注销WebSocket队列"""
        async with self._lock:
            self._websocket_queues.discard(queue)


event_bus = EventBus()


def emit_system_status(status: str, details: Optional[Dict[str, Any]] = None) -> None:
    """发送系统状态事件"""
    event = Event(
        type=EventType.SYSTEM_STATUS,
        data={"status": status, "details": details or {}}
    )
    event_bus.publish_sync(event)


def emit_monitor_status(status: str, details: Optional[Dict[str, Any]] = None) -> None:
    """发送监控状态事件"""
    event = Event(
        type=EventType.MONITOR_STATUS,
        data={"status": status, "details": details or {}}
    )
    event_bus.publish_sync(event)


def emit_agent_status(status: str, details: Optional[Dict[str, Any]] = None) -> None:
    """发送Agent状态事件"""
    event = Event(
        type=EventType.AGENT_STATUS,
        data={"status": status, "details": details or {}}
    )
    event_bus.publish_sync(event)


def emit_new_alert(alert_data: Dict[str, Any]) -> None:
    """发送新告警事件"""
    event = Event(
        type=EventType.NEW_ALERT,
        data=alert_data
    )
    event_bus.publish_sync(event)


def emit_position_update(position_data: Dict[str, Any]) -> None:
    """发送持仓更新事件"""
    event = Event(
        type=EventType.POSITION_UPDATE,
        data=position_data
    )
    event_bus.publish_sync(event)


def emit_trade_executed(trade_data: Dict[str, Any]) -> None:
    """发送交易执行事件"""
    event = Event(
        type=EventType.TRADE_EXECUTED,
        data=trade_data
    )
    event_bus.publish_sync(event)


def emit_log(level: str, message: str, source: str = "system") -> None:
    """发送日志消息事件"""
    event = Event(
        type=EventType.LOG_MESSAGE,
        data={"level": level, "message": message, "source": source}
    )
    event_bus.publish_sync(event)


def emit_error(error: str, details: Optional[Dict[str, Any]] = None) -> None:
    """发送错误事件"""
    event = Event(
        type=EventType.ERROR,
        data={"error": error, "details": details or {}}
    )
    event_bus.publish_sync(event)


def emit_mark_price_update(prices: Dict[str, float]) -> None:
    """发送标记价格更新事件
    
    Args:
        prices: {symbol: mark_price} 字典
    """
    event = Event(
        type=EventType.MARK_PRICE_UPDATE,
        data={"prices": prices}
    )
    event_bus.publish_sync(event)
