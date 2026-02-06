"""
测试 LangChain 根据 reasoning 参数自动选择 API 端点

目的：验证 LangChain 是否真的会根据 reasoning 参数自动选择 Responses API
"""
import os
from unittest.mock import patch, MagicMock

from dotenv import load_dotenv
load_dotenv()

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage


def test_api_endpoint_selection():
    """测试 API 端点自动选择"""
    
    print("\n" + "=" * 70)
    print("测试：LangChain API 端点自动选择")
    print("=" * 70)
    
    base_url = os.getenv('AGENT_BASE_URL', 'https://ark-cn-beijing.bytedance.net/api/v3')
    api_key = os.getenv('AGENT_API_KEY')
    model_name = os.getenv('AGENT_MODEL')
    
    print(f"\n配置：")
    print(f"  base_url: {base_url}")
    print(f"  model: {model_name}")
    
    print("\n--- 测试1：不启用 reasoning ---")
    model_no_reasoning = ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=0.0,
        reasoning=None,
    )
    
    result1 = model_no_reasoning._use_responses_api({})
    print(f"  _use_responses_api() = {result1}")
    print(f"  预期使用: {'Responses API' if result1 else 'Chat Completions API'}")
    
    print("\n--- 测试2：启用 reasoning ---")
    model_with_reasoning = ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=0.0,
        reasoning={"effort": "medium"},
    )
    
    result2 = model_with_reasoning._use_responses_api({})
    print(f"  _use_responses_api() = {result2}")
    print(f"  预期使用: {'Responses API' if result2 else 'Chat Completions API'}")
    
    print("\n--- 测试3：实际 API 调用验证 ---")
    
    captured_calls = {"chat_completions": 0, "responses": 0}
    
    original_chat_create = model_no_reasoning.root_client.chat.completions.create
    original_responses_create = model_no_reasoning.root_client.responses.create
    
    def mock_chat_create(*args, **kwargs):
        captured_calls["chat_completions"] += 1
        print(f"  📡 调用了 Chat Completions API!")
        return original_chat_create(*args, **kwargs)
    
    def mock_responses_create(*args, **kwargs):
        captured_calls["responses"] += 1
        print(f"  📡 调用了 Responses API!")
        return original_responses_create(*args, **kwargs)
    
    print("\n  3a. 测试无 reasoning 的模型:")
    try:
        model_no_reasoning.root_client.chat.completions.create = mock_chat_create
        model_no_reasoning.root_client.responses.create = mock_responses_create
        
        response = model_no_reasoning.invoke([HumanMessage(content="说'测试'")])
        print(f"     响应: {response.content[:50]}...")
    except Exception as e:
        print(f"     错误: {e}")
    
    captured_calls = {"chat_completions": 0, "responses": 0}
    
    print("\n  3b. 测试有 reasoning 的模型:")
    try:
        model_with_reasoning.root_client.chat.completions.create = mock_chat_create
        model_with_reasoning.root_client.responses.create = mock_responses_create
        
        response = model_with_reasoning.invoke([HumanMessage(content="说'测试'")])
        print(f"     响应: {response.content[:50] if isinstance(response.content, str) else str(response.content)[:50]}...")
    except Exception as e:
        print(f"     错误: {e}")
    
    print("\n" + "=" * 70)
    print("结论：")
    print("=" * 70)
    print(f"  - 无 reasoning 时 _use_responses_api(): {result1}")
    print(f"  - 有 reasoning 时 _use_responses_api(): {result2}")
    
    if not result1 and result2:
        print("\n✅ 验证成功：LangChain 会根据 reasoning 参数自动选择 API 端点")
        print("   - reasoning=None → Chat Completions API")
        print("   - reasoning={'effort': '...'} → Responses API")
        return True
    else:
        print("\n❌ 验证失败：行为与预期不符")
        return False


if __name__ == "__main__":
    test_api_endpoint_selection()
