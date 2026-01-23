"""
Vision Middleware - 处理图像工具返回值并转换为多模态消息

这个middleware继承AgentMiddleware，在工具调用后提取图像数据，
在模型调用前将图像注入到消息中。
"""
import json
from typing import Any, Dict, List
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage
from langchain.agents.middleware.types import AgentMiddleware



class VisionMiddleware(AgentMiddleware):
    """处理图像工具返回并转换为视觉理解消息的middleware"""
    
    def __init__(self):
        super().__init__()
        self.pending_images: List[Dict[str, Any]] = []
        self.tools = []
    
    def wrap_tool_call(self, request, handler):
        """
        工具调用后的钩子 - 检测并提取图像数据
        
        拦截工具返回值，如果包含图像数据则提取并保存
        """
        # 执行原始工具调用
        result = handler(request)
        
        # 检查返回值是否为ToolMessage
        if isinstance(result, ToolMessage):
            try:
                # 尝试解析JSON内容
                content = json.loads(result.content)
                
                # 检查是否包含图像数据
                if content.get('success') and 'image_data' in content:
                    # 保存图像信息
                    image_info = {
                        'image_data': content['image_data'],
                        'symbol': content.get('symbol', 'unknown'),
                        'intervals': content.get('intervals', []),
                        'kline_count': content.get('kline_count', 0)
                    }
                    self.pending_images.append(image_info)
                    
                    # 返回简化的ToolMessage（不包含大量base64数据）
                    # 添加特殊标记 [KLINE_IMAGE] 以便后续识别
                    from langchain_core.messages import ToolMessage as TM
                    simplified_content = f"""[KLINE_IMAGE]K线图已生成

**交易对**: {content.get('symbol')}
**时间周期**: {', '.join(content.get('intervals', []))}
**K线数量**: 每个周期 {content.get('kline_count')} 根
"""
                    return TM(
                        content=simplified_content,
                        tool_call_id=result.tool_call_id
                    )
            except (json.JSONDecodeError, KeyError, TypeError):
                pass
        
        return result
    
    def before_model(self, state, runtime):
        """
        模型调用前的钩子 - 将图像数据注入消息
        
        如果有待处理的图像，删除所有对应的 ToolMessage，并将图片合并到一个 HumanMessage 中
        """
        if not self.pending_images:
            return None
        
        messages = state.get('messages', [])
        if not messages:
            return None
        
        # 记录待处理图片的数量
        num_pending_images = len(self.pending_images)
        
        # 从后往前查找带 [KLINE_IMAGE] 标记的 ToolMessage
        # 只删除对应数量的 K线图工具返回，不影响其他工具
        tool_message_indices = []
        for i in range(len(messages) - 1, -1, -1):
            if isinstance(messages[i], ToolMessage):
                # 检查是否是 K线图工具的返回（带特殊标记）
                if messages[i].content.startswith('[KLINE_IMAGE]'):
                    tool_message_indices.append(i)
                    if len(tool_message_indices) >= num_pending_images:
                        break
        
        if not tool_message_indices:
            return None
        
        # 构造包含所有待处理图片的content数组
        content_items = []
        while self.pending_images:
            image_info = self.pending_images.pop(0)
            image_url = f"data:image/png;base64,{image_info['image_data']}"
            
            content_items.append({
                "type": "image_url",
                "image_url": {
                    "url": image_url,
                    "detail": "high"
                }
            })
        
        if not content_items:
            return None
        
        # 创建包含所有图片的 HumanMessage
        vision_message = HumanMessage(content=content_items)
        
        # 删除所有找到的 ToolMessage，并在最后一个位置插入 HumanMessage
        # tool_message_indices 是倒序的，最后一个索引是最小的（最早的 ToolMessage）
        first_tool_index = tool_message_indices[-1]  # 最早的 ToolMessage 位置
        last_tool_index = tool_message_indices[0]    # 最后的 ToolMessage 位置
        
        # 构建新的消息列表：保留 first_tool_index 之前的，插入 vision_message，保留 last_tool_index 之后的
        new_messages = (
            messages[:first_tool_index] +
            [vision_message] +
            messages[last_tool_index + 1:]
        )
        
        return {"messages": new_messages}
