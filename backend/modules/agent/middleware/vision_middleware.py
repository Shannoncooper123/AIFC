"""
Vision Middleware - 处理图像工具返回值并转换为多模态消息

这个middleware继承AgentMiddleware，在工具调用后提取图像数据，
在模型调用前将图像注入到消息中。
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Callable, Dict, List

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.types import Command

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from langchain.tools.tool_node import ToolCallRequest


class VisionMiddleware(AgentMiddleware):
    """处理图像工具返回并转换为视觉理解消息的middleware
    
    图片元数据通过 image_registry 传递给 WorkflowTraceMiddleware，
    不会污染发送给 LLM 的消息内容。
    """

    def __init__(self):
        super().__init__()
        self.pending_images: List[Dict[str, Any]] = []
        self.image_registry: Dict[int, Dict[str, Any]] = {}
        self._image_counter = 0

    def _process_tool_result(self, result: ToolMessage | Command) -> ToolMessage | Command:
        """处理工具返回结果，提取图像数据"""
        if isinstance(result, ToolMessage):
            try:
                content = json.loads(result.content)
                if isinstance(content, dict) and content.get('success') and 'image_data' in content:
                    image_info = {
                        'image_data': content['image_data'],
                        'symbol': content.get('symbol', 'unknown'),
                        'intervals': content.get('intervals', []),
                        'kline_count': content.get('kline_count', 0)
                    }
                    self.pending_images.append(image_info)
                    simplified_content = f"""[KLINE_IMAGE]K线图已生成

**交易对**: {content.get('symbol')}
**时间周期**: {', '.join(content.get('intervals', []))}
**K线数量**: 每个周期 {content.get('kline_count')} 根
"""
                    return ToolMessage(
                        content=simplified_content,
                        tool_call_id=result.tool_call_id
                    )
            except (json.JSONDecodeError, KeyError, TypeError):
                pass
        return result

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        """工具调用后的钩子 - 检测并提取图像数据（同步版本）"""
        result = handler(request)
        return self._process_tool_result(result)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        """工具调用后的钩子 - 检测并提取图像数据（异步版本）"""
        result = await handler(request)
        return self._process_tool_result(result)

    def _inject_images_to_messages(self, state: dict) -> dict | None:
        """将待处理的图像注入到消息中"""
        if not self.pending_images:
            return None

        messages = state.get('messages', [])
        if not messages:
            return None

        num_pending_images = len(self.pending_images)

        tool_message_indices = []
        for i in range(len(messages) - 1, -1, -1):
            if isinstance(messages[i], ToolMessage):
                if messages[i].content.startswith('[KLINE_IMAGE]'):
                    tool_message_indices.append(i)
                    if len(tool_message_indices) >= num_pending_images:
                        break

        if not tool_message_indices:
            return None

        content_items = []
        while self.pending_images:
            image_info = self.pending_images.pop(0)
            image_url = f"data:image/png;base64,{image_info['image_data']}"
            symbol = image_info.get('symbol', 'unknown')
            interval = image_info.get('intervals', ['unknown'])[0] if image_info.get('intervals') else 'unknown'
            
            self._image_counter += 1
            image_id = self._image_counter
            
            self.image_registry[image_id] = {
                "symbol": symbol,
                "interval": interval,
            }
            
            content_items.append({
                "type": "image_url",
                "image_url": {
                    "url": image_url,
                    "detail": "high"
                }
            })

        if not content_items:
            return None

        vision_message = HumanMessage(content=content_items)

        first_tool_index = tool_message_indices[-1]
        last_tool_index = tool_message_indices[0]

        new_messages = (
            messages[:first_tool_index] +
            [vision_message] +
            messages[last_tool_index + 1:]
        )

        return {
            "messages": new_messages,
        }

    def before_model(self, state: dict, runtime: Any) -> dict | None:
        """模型调用前的钩子 - 将图像数据注入消息（同步版本）"""
        return self._inject_images_to_messages(state)

    async def abefore_model(self, state: dict, runtime: Any) -> dict | None:
        """模型调用前的钩子 - 将图像数据注入消息（异步版本）"""
        return self._inject_images_to_messages(state)
    
    def get_image_meta_for_trace(self, image_index: int) -> Dict[str, Any]:
        """获取指定索引图片的元数据（供 trace 序列化使用）
        
        image_index 从 1 开始
        """
        return self.image_registry.get(image_index, {})
    
    def get_all_image_metas(self) -> List[Dict[str, Any]]:
        """获取所有图片的元数据列表（按注册顺序）"""
        if not self.image_registry:
            return []
        max_id = max(self.image_registry.keys())
        return [self.image_registry.get(i, {}) for i in range(1, max_id + 1)]
