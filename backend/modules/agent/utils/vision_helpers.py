"""图像消息转换辅助函数"""
import json
from typing import List
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage


def convert_image_tool_messages(messages: List[BaseMessage]) -> List[BaseMessage]:
    """
    转换包含图像的ToolMessage为正确的视觉理解消息格式
    
    检测ToolMessage中是否包含type="image"的JSON数据，
    如果有则将其转换为HumanMessage，内容格式为多模态消息（image_url + text）
    
    Args:
        messages: 消息列表
        
    Returns:
        转换后的消息列表
    """
    converted = []
    
    for msg in messages:
        if isinstance(msg, ToolMessage):
            try:
                # 尝试解析JSON内容
                content = json.loads(msg.content)
                
                # 检查是否为图像类型
                if content.get('type') == 'image' and 'image_url' in content:
                    # 构造多模态HumanMessage
                    vision_msg = HumanMessage(
                        content=[
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": content['image_url'],
                                    "detail": content.get('detail', 'high')
                                }
                            },
                            {
                                "type": "text",
                                "text": content.get('description', 
                                    f"K线图已生成 - {content.get('symbol', 'unknown')} "
                                    f"{', '.join(content.get('intervals', []))}")
                            }
                        ]
                    )
                    converted.append(vision_msg)
                    continue
            except (json.JSONDecodeError, KeyError, TypeError):
                # 如果不是JSON或格式不对，保持原样
                pass
        
        converted.append(msg)
    
    return converted
