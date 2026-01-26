"""
测试工具直接返回多模态内容（不经过 VisionMiddleware）

测试目标：
1. 验证 @tool 装饰器是否支持直接返回 list[dict] 格式的多模态内容
2. 验证 langchain.agents.create_agent 是否能正确处理这种返回格式
3. 验证 Volcengine ARK API 是否能正确接收并理解工具返回的图像

运行方式：
    cd /Users/bytedance/Desktop/crypto_agentx/backend
    source .venv/bin/activate
    python tests/test_tool_direct_image_return.py
"""
import base64
import os
import sys
from io import BytesIO
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI


def create_test_image_base64() -> str:
    """创建一个简单的测试图像（红色方块），返回 base64 编码"""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("需要安装 Pillow: pip install Pillow")
        sys.exit(1)
    
    img = Image.new('RGB', (200, 200), color='white')
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, 180, 180], fill='red', outline='black', width=2)
    draw.text((60, 90), "TEST", fill='white')
    
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode('utf-8')


@tool("get_chart_image_v1")
def get_chart_image_v1() -> list[dict]:
    """获取图表图像 - 方案1：直接返回 list[dict] 多模态格式
    
    Returns:
        包含文本和图像的多模态内容列表
    """
    image_base64 = create_test_image_base64()
    
    return [
        {
            "type": "text",
            "text": "图表生成成功！这是一个 200x200 的测试图像，中间有一个红色方块和 'TEST' 文字。"
        },
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{image_base64}",
                "detail": "auto"
            }
        }
    ]


@tool("get_chart_image_v2")
def get_chart_image_v2() -> str:
    """获取图表图像 - 方案2：返回 JSON 字符串（当前方案）
    
    Returns:
        JSON 字符串，包含 image_data 字段
    """
    import json
    image_base64 = create_test_image_base64()
    
    return json.dumps({
        "success": True,
        "symbol": "TEST",
        "intervals": ["1h"],
        "kline_count": 100,
        "image_data": image_base64,
    }, ensure_ascii=False)


def get_model() -> ChatOpenAI:
    """获取配置好的 ChatOpenAI 模型"""
    return ChatOpenAI(
        model=os.getenv('AGENT_MODEL'),
        api_key=os.getenv('AGENT_API_KEY'),
        base_url=os.getenv('AGENT_BASE_URL') or None,
        temperature=0.1,
        timeout=120,
        max_tokens=1000,
    )


def test_1_direct_multimodal_return():
    """
    测试方案1：工具直接返回 list[dict] 多模态格式
    
    这是最简洁的方案，如果可行，可以完全移除 VisionMiddleware
    """
    print("\n" + "="*60)
    print("测试1：工具直接返回 list[dict] 多模态格式")
    print("="*60)
    
    model = get_model()
    
    agent = create_agent(
        model=model,
        tools=[get_chart_image_v1],
        system_prompt="你是一个图像分析助手。当用户要求获取图表时，调用相应工具并描述图像内容。",
    )
    
    try:
        result = agent.invoke({
            "messages": [
                HumanMessage(content="请调用 get_chart_image_v1 工具获取图表，然后描述你看到的图像内容。")
            ]
        })
        
        final_message = result["messages"][-1]
        print(f"✅ 成功！模型响应：")
        print(f"   {final_message.content[:500]}...")
        
        print("\n--- 消息历史 ---")
        for i, msg in enumerate(result["messages"]):
            msg_type = type(msg).__name__
            content_preview = str(msg.content)[:100] if hasattr(msg, 'content') else "N/A"
            print(f"  [{i}] {msg_type}: {content_preview}...")
        
        return True
    except Exception as e:
        print(f"❌ 失败！错误：{e}")
        import traceback
        traceback.print_exc()
        return False


def test_2_json_string_return_without_middleware():
    """
    测试方案2：工具返回 JSON 字符串（不使用 VisionMiddleware）
    
    这是当前的方案，但不使用 VisionMiddleware，看模型能否理解
    """
    print("\n" + "="*60)
    print("测试2：工具返回 JSON 字符串（不使用 VisionMiddleware）")
    print("="*60)
    
    model = get_model()
    
    agent = create_agent(
        model=model,
        tools=[get_chart_image_v2],
        system_prompt="你是一个图像分析助手。当用户要求获取图表时，调用相应工具并描述图像内容。",
    )
    
    try:
        result = agent.invoke({
            "messages": [
                HumanMessage(content="请调用 get_chart_image_v2 工具获取图表，然后描述你看到的图像内容。")
            ]
        })
        
        final_message = result["messages"][-1]
        print(f"✅ Agent 执行完成！模型响应：")
        print(f"   {final_message.content[:500]}...")
        
        if "无法" in final_message.content or "看不到" in final_message.content or "cannot" in final_message.content.lower():
            print("\n⚠️  模型表示无法看到图像（符合预期，因为 JSON 中的 base64 不会被解析为图像）")
            return False
        
        return True
    except Exception as e:
        print(f"❌ 失败！错误：{e}")
        import traceback
        traceback.print_exc()
        return False


def test_3_inspect_tool_message_format():
    """
    测试方案3：检查工具返回值如何被转换为 ToolMessage
    
    直接调用工具并检查 LangChain 如何处理返回值
    """
    print("\n" + "="*60)
    print("测试3：检查 ToolMessage 格式转换")
    print("="*60)
    
    from langchain_core.messages import ToolMessage
    
    print("\n--- 直接调用 get_chart_image_v1 ---")
    result_v1 = get_chart_image_v1.invoke({})
    print(f"  返回类型: {type(result_v1).__name__}")
    if isinstance(result_v1, list):
        print(f"  返回长度: {len(result_v1)}")
        for i, block in enumerate(result_v1):
            if isinstance(block, dict):
                block_type = block.get('type', 'unknown')
                print(f"    [{i}] type={block_type}")
                if block_type == 'image_url':
                    url = block.get('image_url', {}).get('url', '')
                    print(f"        image_url 长度: {len(url)} 字符")
    else:
        print(f"  返回预览: {str(result_v1)[:200]}...")
    
    print("\n--- 直接调用 get_chart_image_v2 ---")
    result_v2 = get_chart_image_v2.invoke({})
    print(f"  返回类型: {type(result_v2).__name__}")
    print(f"  返回预览: {str(result_v2)[:200]}...")
    
    print("\n--- 模拟 ToolMessage 构造 ---")
    tool_msg_v1 = ToolMessage(
        content=result_v1,
        tool_call_id="test_call_v1"
    )
    print(f"  ToolMessage v1 content 类型: {type(tool_msg_v1.content).__name__}")
    
    tool_msg_v2 = ToolMessage(
        content=result_v2,
        tool_call_id="test_call_v2"
    )
    print(f"  ToolMessage v2 content 类型: {type(tool_msg_v2.content).__name__}")
    
    print("\n✅ 格式检查完成")
    return True


def main():
    """运行所有测试"""
    print("="*60)
    print("工具直接返回多模态内容测试")
    print("="*60)
    print(f"模型: {os.getenv('AGENT_MODEL')}")
    print(f"API Base URL: {os.getenv('AGENT_BASE_URL')}")
    print("="*60)
    
    results = {}
    
    results['test_3_format_check'] = test_3_inspect_tool_message_format()
    
    results['test_1_direct_multimodal'] = test_1_direct_multimodal_return()
    
    results['test_2_json_without_middleware'] = test_2_json_string_return_without_middleware()
    
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    for test_name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {test_name}: {status}")
    
    print("\n" + "="*60)
    print("结论")
    print("="*60)
    
    if results.get('test_1_direct_multimodal'):
        print("🎉 工具可以直接返回 list[dict] 多模态格式！")
        print("   可以完全移除 VisionMiddleware，直接在工具中返回图像")
        print("\n   推荐的工具返回格式：")
        print("""
    @tool
    def get_kline_image_tool(...) -> list[dict]:
        image_base64 = generate_chart(...)
        return [
            {"type": "text", "text": f"K线图: {symbol} {interval}"},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{image_base64}",
                    "detail": "high"
                }
            }
        ]
        """)
    else:
        print("⚠️  工具直接返回多模态格式可能存在问题")
        print("   建议继续使用 VisionMiddleware 方案")
    
    return all(results.values())


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
