"""
测试 ToolMessage 中直接嵌入图像是否被 Volcengine ARK API 支持

测试目标：
1. 验证 LangChain ToolMessage 是否支持多模态内容（图像）
2. 验证 Volcengine ARK API 是否能正确处理 ToolMessage 中的图像
3. 对比当前 VisionMiddleware 方案与直接嵌入方案的差异

运行方式：
    cd /Users/bytedance/Desktop/crypto_agentx/backend
    source .venv/bin/activate
    python tests/test_toolmessage_image.py
"""
import asyncio
import base64
import json
import os
import sys
from io import BytesIO
from typing import Any, Dict

from dotenv import load_dotenv

load_dotenv()

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI


def create_test_image_base64() -> str:
    """创建一个简单的测试图像（红色方块），返回 base64 编码"""
    try:
        from PIL import Image
    except ImportError:
        print("需要安装 Pillow: pip install Pillow")
        sys.exit(1)
    
    img = Image.new('RGB', (100, 100), color='red')
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode('utf-8')


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


@tool
def get_test_image() -> Dict[str, Any]:
    """获取一个测试图像
    
    Returns:
        包含图像数据的字典
    """
    image_base64 = create_test_image_base64()
    return {
        "success": True,
        "image_data": image_base64,
        "description": "这是一个 100x100 的红色方块测试图像"
    }


def test_1_toolmessage_with_image_content_block():
    """
    测试方案1：使用 LangChain 标准的 content block 格式
    
    ToolMessage.content 设置为 list[dict]，包含 image_url 类型的 content block
    """
    print("\n" + "="*60)
    print("测试1：ToolMessage 使用 content block 格式嵌入图像")
    print("="*60)
    
    model = get_model()
    image_base64 = create_test_image_base64()
    
    messages = [
        HumanMessage(content="请调用 get_test_image 工具获取图像，然后描述你看到的图像内容"),
        AIMessage(
            content="",
            tool_calls=[{
                "id": "call_test_1",
                "name": "get_test_image",
                "args": {}
            }]
        ),
        ToolMessage(
            tool_call_id="call_test_1",
            content=[
                {
                    "type": "text",
                    "text": "工具执行成功，返回了一个测试图像"
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{image_base64}",
                        "detail": "auto"
                    }
                }
            ]
        )
    ]
    
    try:
        response = model.invoke(messages)
        print(f"✅ 成功！模型响应：")
        print(f"   {response.content[:500]}...")
        return True
    except Exception as e:
        print(f"❌ 失败！错误：{e}")
        return False


def test_2_toolmessage_with_string_content_and_separate_human_message():
    """
    测试方案2：当前 VisionMiddleware 的方案
    
    ToolMessage.content 为纯文本，图像通过单独的 HumanMessage 传递
    """
    print("\n" + "="*60)
    print("测试2：ToolMessage 纯文本 + 单独 HumanMessage 携带图像（当前方案）")
    print("="*60)
    
    model = get_model()
    image_base64 = create_test_image_base64()
    
    messages = [
        HumanMessage(content="请调用 get_test_image 工具获取图像，然后描述你看到的图像内容"),
        AIMessage(
            content="",
            tool_calls=[{
                "id": "call_test_2",
                "name": "get_test_image",
                "args": {}
            }]
        ),
        HumanMessage(content=[
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{image_base64}",
                    "detail": "auto"
                }
            }
        ]),
        ToolMessage(
            tool_call_id="call_test_2",
            content="[KLINE_IMAGE]K线图已生成在用户消息内\n\n交易对: TEST\n时间周期: 1h\nK线数量: 100 根"
        )
    ]
    
    try:
        response = model.invoke(messages)
        print(f"✅ 成功！模型响应：")
        print(f"   {response.content[:500]}...")
        return True
    except Exception as e:
        print(f"❌ 失败！错误：{e}")
        return False


def test_3_toolmessage_with_artifact_format():
    """
    测试方案3：使用 artifact 格式
    
    某些模型支持在 ToolMessage 中使用 artifact 字段传递二进制数据
    """
    print("\n" + "="*60)
    print("测试3：ToolMessage 使用 artifact 格式")
    print("="*60)
    
    model = get_model()
    image_base64 = create_test_image_base64()
    
    messages = [
        HumanMessage(content="请调用 get_test_image 工具获取图像，然后描述你看到的图像内容"),
        AIMessage(
            content="",
            tool_calls=[{
                "id": "call_test_3",
                "name": "get_test_image",
                "args": {}
            }]
        ),
        ToolMessage(
            tool_call_id="call_test_3",
            content="工具执行成功，返回了一个测试图像",
            artifact={
                "type": "image",
                "data": image_base64,
                "mime_type": "image/png"
            }
        )
    ]
    
    try:
        response = model.invoke(messages)
        print(f"✅ 成功！模型响应：")
        print(f"   {response.content[:500]}...")
        return True
    except Exception as e:
        print(f"❌ 失败！错误：{e}")
        return False


def test_4_openai_style_multimodal_tool_result():
    """
    测试方案4：OpenAI 风格的多模态工具结果
    
    参考 OpenAI API 文档，tool message content 可以是 array of content parts
    """
    print("\n" + "="*60)
    print("测试4：OpenAI 风格的多模态 tool result")
    print("="*60)
    
    model = get_model()
    image_base64 = create_test_image_base64()
    
    tool_result_content = [
        {
            "type": "text",
            "text": json.dumps({
                "success": True,
                "description": "这是一个 100x100 的红色方块测试图像"
            })
        },
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{image_base64}"
            }
        }
    ]
    
    messages = [
        HumanMessage(content="请调用 get_test_image 工具获取图像，然后描述你看到的图像内容"),
        AIMessage(
            content="",
            tool_calls=[{
                "id": "call_test_4",
                "name": "get_test_image",
                "args": {}
            }]
        ),
        ToolMessage(
            tool_call_id="call_test_4",
            content=tool_result_content
        )
    ]
    
    try:
        response = model.invoke(messages)
        print(f"✅ 成功！模型响应：")
        print(f"   {response.content[:500]}...")
        return True
    except Exception as e:
        print(f"❌ 失败！错误：{e}")
        return False


def test_5_raw_api_with_image_in_tool_message():
    """
    测试方案5：直接使用 requests 调用 ARK API
    
    绕过 LangChain，直接测试 ARK API 是否支持 tool message 中的图像
    """
    print("\n" + "="*60)
    print("测试5：直接调用 ARK API（绕过 LangChain）")
    print("="*60)
    
    import requests
    
    image_base64 = create_test_image_base64()
    
    api_key = os.getenv('AGENT_API_KEY')
    base_url = os.getenv('AGENT_BASE_URL')
    model_name = os.getenv('AGENT_MODEL')
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "user",
                "content": "请调用 get_test_image 工具获取图像，然后描述你看到的图像内容"
            },
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_test_5",
                    "type": "function",
                    "function": {
                        "name": "get_test_image",
                        "arguments": "{}"
                    }
                }]
            },
            {
                "role": "tool",
                "tool_call_id": "call_test_5",
                "content": [
                    {
                        "type": "text",
                        "text": "工具执行成功，返回了一个测试图像"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_base64}"
                        }
                    }
                ]
            }
        ],
        "tools": [{
            "type": "function",
            "function": {
                "name": "get_test_image",
                "description": "获取一个测试图像",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }],
        "max_tokens": 1000
    }
    
    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=120
        )
        
        if response.status_code == 200:
            result = response.json()
            content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
            print(f"✅ 成功！模型响应：")
            print(f"   {content[:500]}...")
            return True
        else:
            print(f"❌ 失败！HTTP {response.status_code}")
            print(f"   响应：{response.text[:500]}")
            return False
    except Exception as e:
        print(f"❌ 失败！错误：{e}")
        return False


def test_6_raw_api_string_content_tool_message():
    """
    测试方案6：直接调用 ARK API，tool message content 为字符串
    
    对照组：验证普通的字符串 content 是否正常工作
    """
    print("\n" + "="*60)
    print("测试6：直接调用 ARK API（tool message 为字符串，对照组）")
    print("="*60)
    
    import requests
    
    api_key = os.getenv('AGENT_API_KEY')
    base_url = os.getenv('AGENT_BASE_URL')
    model_name = os.getenv('AGENT_MODEL')
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "user",
                "content": "请调用 get_weather 工具获取天气，然后告诉我结果"
            },
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_test_6",
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": "{\"city\": \"北京\"}"
                    }
                }]
            },
            {
                "role": "tool",
                "tool_call_id": "call_test_6",
                "content": "北京今天天气晴朗，温度 25°C，湿度 60%"
            }
        ],
        "tools": [{
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "获取指定城市的天气",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": "城市名称"
                        }
                    },
                    "required": ["city"]
                }
            }
        }],
        "max_tokens": 1000
    }
    
    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=120
        )
        
        if response.status_code == 200:
            result = response.json()
            content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
            print(f"✅ 成功！模型响应：")
            print(f"   {content[:500]}...")
            return True
        else:
            print(f"❌ 失败！HTTP {response.status_code}")
            print(f"   响应：{response.text[:500]}")
            return False
    except Exception as e:
        print(f"❌ 失败！错误：{e}")
        return False


def main():
    """运行所有测试"""
    print("="*60)
    print("ToolMessage 图像嵌入测试")
    print("="*60)
    print(f"模型: {os.getenv('AGENT_MODEL')}")
    print(f"API Base URL: {os.getenv('AGENT_BASE_URL')}")
    print("="*60)
    
    results = {}
    
    results['test_6_string_content'] = test_6_raw_api_string_content_tool_message()
    
    results['test_1_content_block'] = test_1_toolmessage_with_image_content_block()
    
    results['test_2_current_approach'] = test_2_toolmessage_with_string_content_and_separate_human_message()
    
    results['test_3_artifact'] = test_3_toolmessage_with_artifact_format()
    
    results['test_4_openai_style'] = test_4_openai_style_multimodal_tool_result()
    
    results['test_5_raw_api'] = test_5_raw_api_with_image_in_tool_message()
    
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    for test_name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {test_name}: {status}")
    
    print("\n" + "="*60)
    print("结论")
    print("="*60)
    
    if results.get('test_1_content_block') or results.get('test_4_openai_style') or results.get('test_5_raw_api'):
        print("🎉 Volcengine ARK API 支持在 ToolMessage 中直接嵌入图像！")
        print("   可以考虑简化 VisionMiddleware 架构")
    else:
        print("⚠️  Volcengine ARK API 不支持在 ToolMessage 中直接嵌入图像")
        print("   需要继续使用当前的 VisionMiddleware 方案")
    
    return all(results.values())


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
