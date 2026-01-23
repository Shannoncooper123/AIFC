"""WebSocket 处理器"""
import asyncio
import logging
from typing import Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.events import Event, event_bus


logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    """WebSocket 连接管理器"""
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
    
    async def connect(self, websocket: WebSocket):
        """接受新连接"""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket 连接已建立，当前连接数: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        """断开连接"""
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket 连接已断开，当前连接数: {len(self.active_connections)}")
    
    async def broadcast(self, message: str):
        """广播消息到所有连接"""
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.add(connection)
        
        for conn in disconnected:
            self.active_connections.discard(conn)


manager = ConnectionManager()


@router.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    """WebSocket 事件流端点"""
    await manager.connect(websocket)
    
    queue: asyncio.Queue = asyncio.Queue()
    await event_bus.register_websocket_queue(queue)
    
    try:
        send_task = asyncio.create_task(_send_events(websocket, queue))
        receive_task = asyncio.create_task(_receive_messages(websocket))
        
        done, pending = await asyncio.wait(
            [send_task, receive_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
                
    except WebSocketDisconnect:
        logger.info("WebSocket 客户端主动断开")
    except Exception as e:
        logger.error(f"WebSocket 错误: {e}")
    finally:
        await event_bus.unregister_websocket_queue(queue)
        manager.disconnect(websocket)


async def _send_events(websocket: WebSocket, queue: asyncio.Queue):
    """发送事件到 WebSocket"""
    while True:
        event: Event = await queue.get()
        try:
            await websocket.send_text(event.to_json())
        except Exception as e:
            logger.error(f"发送 WebSocket 消息失败: {e}")
            break


async def _receive_messages(websocket: WebSocket):
    """接收 WebSocket 消息（用于保持连接和处理 ping）"""
    while True:
        try:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text('{"type": "pong"}')
        except WebSocketDisconnect:
            break
        except Exception:
            break
