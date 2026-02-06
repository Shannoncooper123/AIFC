"""
测试深度思考内容（reasoning_content）在 Agent Tool 调用循环中的保留与传递

测试目标：
1. 验证使用火山引擎 Responses API 时，reasoning 内容是否被正确解析到 AIMessage
2. 验证在多轮 tool 调用中，之前的 reasoning 内容是否被传递给下一轮请求
3. 验证 LangChain 的 _construct_responses_api_input 是否正确处理 reasoning blocks

运行方式：
    cd /Users/bytedance/Desktop/crypto_agentx/backend
    source .venv/bin/activate
    python tests/test_reasoning_content_preservation.py

环境变量要求（.env）：
    AGENT_MODEL=doubao-seed-1-8-251228  # 或其他支持深度思考的模型
    AGENT_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
    AGENT_API_KEY=your_ark_api_key
"""

import os
import sys
from typing import Any
from unittest.mock import patch

from dotenv import load_dotenv

load_dotenv()

from langchain.agents import create_agent
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI


class ReasoningInspectorCallback(BaseCallbackHandler):
    """回调处理器：检查每次 LLM 调用的输入输出中的 reasoning 内容"""
    
    def __init__(self):
        self.call_count = 0
        self.reasoning_found_in_responses: list[dict] = []
        self.reasoning_found_in_requests: list[dict] = []
        self.all_ai_messages: list[AIMessage] = []
    
    def on_llm_start(self, serialized: dict, prompts: list[str], **kwargs):
        self.call_count += 1
        messages = kwargs.get("invocation_params", {}).get("messages", [])
        
        print(f"\n{'='*60}")
        print(f"🔍 LLM 调用 #{self.call_count} - 检查输入消息中的 reasoning")
        print(f"{'='*60}")
        
        reasoning_in_request = []
        for i, msg in enumerate(messages):
            if isinstance(msg, dict):
                role = msg.get("role", "")
                if role == "assistant":
                    content = msg.get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") in ("reasoning", "output_text", "text"):
                                block_type = block.get("type")
                                if block_type == "reasoning":
                                    reasoning_in_request.append({
                                        "message_index": i,
                                        "reasoning_block": block
                                    })
                                    print(f"  ✅ 发现 reasoning block 在消息 #{i}:")
                                    summary = block.get("summary", [])
                                    if summary:
                                        for s in summary[:2]:
                                            text = s.get("text", "")[:100]
                                            print(f"     - {text}...")
            elif isinstance(msg, dict) and msg.get("type") == "reasoning":
                reasoning_in_request.append({
                    "message_index": i,
                    "reasoning_block": msg
                })
                print(f"  ✅ 发现独立 reasoning item 在位置 #{i}")
        
        if not reasoning_in_request:
            print("  ⚠️  输入消息中未发现 reasoning blocks（注意：这里检查的是 LangChain 内部格式）")
        
        self.reasoning_found_in_requests.append({
            "call_number": self.call_count,
            "reasoning_blocks": reasoning_in_request
        })
    
    def on_llm_end(self, response, **kwargs):
        print(f"\n📤 LLM 调用 #{self.call_count} - 检查输出响应中的 reasoning")
        
        generations = response.generations if hasattr(response, "generations") else []
        for gen_list in generations:
            for gen in gen_list:
                if hasattr(gen, "message") and isinstance(gen.message, AIMessage):
                    ai_msg = gen.message
                    self.all_ai_messages.append(ai_msg)
                    
                    reasoning_found = self._extract_reasoning_from_message(ai_msg)
                    if reasoning_found:
                        self.reasoning_found_in_responses.append({
                            "call_number": self.call_count,
                            "reasoning": reasoning_found
                        })
                        print(f"  ✅ 响应中包含 reasoning 内容:")
                        for r in reasoning_found[:2]:
                            print(f"     - {r[:100]}...")
                    else:
                        print("  ⚠️  响应中未发现 reasoning 内容")
    
    def _extract_reasoning_from_message(self, msg: AIMessage) -> list[str]:
        """从 AIMessage 中提取 reasoning 内容"""
        reasoning_texts = []
        
        if "reasoning" in msg.additional_kwargs:
            reasoning = msg.additional_kwargs["reasoning"]
            if isinstance(reasoning, dict):
                summary = reasoning.get("summary", [])
                for s in summary:
                    if isinstance(s, dict) and "text" in s:
                        reasoning_texts.append(s["text"])
                    elif isinstance(s, str):
                        reasoning_texts.append(s)
        
        if isinstance(msg.content, list):
            for block in msg.content:
                if isinstance(block, dict) and block.get("type") == "reasoning":
                    summary = block.get("summary", [])
                    for s in summary:
                        if isinstance(s, dict) and "text" in s:
                            reasoning_texts.append(s["text"])
                        elif isinstance(s, str):
                            reasoning_texts.append(s)
        
        return reasoning_texts


call_counter = {"count": 0}


@tool("calculate_fibonacci")
def calculate_fibonacci(n: int) -> str:
    """计算第 n 个斐波那契数
    
    Args:
        n: 要计算的斐波那契数的位置（从 1 开始）
    
    Returns:
        计算结果的描述
    """
    call_counter["count"] += 1
    print(f"\n🔧 Tool 被调用: calculate_fibonacci(n={n}) - 第 {call_counter['count']} 次调用")
    
    if n <= 0:
        return "错误：n 必须是正整数"
    if n == 1 or n == 2:
        return f"第 {n} 个斐波那契数是 1"
    
    a, b = 1, 1
    for _ in range(n - 2):
        a, b = b, a + b
    
    return f"第 {n} 个斐波那契数是 {b}"


@tool("get_current_time")
def get_current_time() -> str:
    """获取当前时间
    
    Returns:
        当前时间的字符串表示
    """
    call_counter["count"] += 1
    from datetime import datetime
    print(f"\n🔧 Tool 被调用: get_current_time() - 第 {call_counter['count']} 次调用")
    return f"当前时间是: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"


def get_deep_thinking_model() -> ChatOpenAI:
    """获取配置为深度思考模式的 ChatOpenAI 模型"""
    model_name = os.getenv("AGENT_MODEL", "doubao-seed-1-8-251228")
    base_url = os.getenv("AGENT_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    api_key = os.getenv("AGENT_API_KEY")
    
    if not api_key:
        print("❌ 错误：未设置 AGENT_API_KEY 环境变量")
        sys.exit(1)
    
    print(f"📋 模型配置:")
    print(f"   - model: {model_name}")
    print(f"   - base_url: {base_url}")
    print(f"   - reasoning: enabled (effort=medium)")
    
    return ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=0.7,
        timeout=120,
        max_tokens=2000,
        reasoning={"effort": "medium"},
    )


def test_1_single_tool_call_reasoning():
    """
    测试1：单次 tool 调用时，响应中是否包含 reasoning 内容
    """
    print("\n" + "=" * 70)
    print("测试1：单次 Tool 调用 - 检查响应中的 reasoning 内容")
    print("=" * 70)
    
    call_counter["count"] = 0
    callback = ReasoningInspectorCallback()
    model = get_deep_thinking_model()
    
    agent = create_agent(
        model=model,
        tools=[calculate_fibonacci],
        system_prompt="你是一个数学助手。请使用提供的工具来帮助用户计算。",
    )
    
    try:
        result = agent.invoke(
            {"messages": [HumanMessage(content="请计算第 10 个斐波那契数是多少？")]},
            config={"callbacks": [callback]}
        )
        
        print("\n" + "-" * 50)
        print("📊 测试结果汇总:")
        print("-" * 50)
        print(f"   - LLM 调用次数: {callback.call_count}")
        print(f"   - 响应中发现 reasoning 的次数: {len(callback.reasoning_found_in_responses)}")
        print(f"   - Tool 调用次数: {call_counter['count']}")
        
        final_response = result["messages"][-1].content
        print(f"\n最终响应: {final_response[:200]}...")
        
        if callback.reasoning_found_in_responses:
            print("\n✅ 测试通过：响应中包含 reasoning 内容")
            return True
        else:
            print("\n⚠️  测试警告：响应中未发现 reasoning 内容（可能模型不支持或未启用深度思考）")
            return False
            
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_2_multi_tool_calls_reasoning_preservation():
    """
    测试2：多次 tool 调用时，前一轮的 reasoning 是否被传递到下一轮请求
    
    这是验证核心猜想的关键测试
    """
    print("\n" + "=" * 70)
    print("测试2：多轮 Tool 调用 - 检查 reasoning 是否在请求间传递")
    print("=" * 70)
    
    call_counter["count"] = 0
    callback = ReasoningInspectorCallback()
    model = get_deep_thinking_model()
    
    agent = create_agent(
        model=model,
        tools=[calculate_fibonacci, get_current_time],
        system_prompt="你是一个多功能助手。请按顺序完成用户的所有请求。",
    )
    
    try:
        result = agent.invoke(
            {"messages": [HumanMessage(
                content="请依次完成以下任务：\n"
                        "1. 首先计算第 5 个斐波那契数\n"
                        "2. 然后获取当前时间\n"
                        "3. 最后计算第 8 个斐波那契数\n"
                        "请一步一步来，每个任务都要调用工具。"
            )]},
            config={"callbacks": [callback]}
        )
        
        print("\n" + "-" * 50)
        print("📊 测试结果汇总:")
        print("-" * 50)
        print(f"   - LLM 调用次数: {callback.call_count}")
        print(f"   - 响应中发现 reasoning 的次数: {len(callback.reasoning_found_in_responses)}")
        print(f"   - 请求中发现 reasoning 的次数: {len([r for r in callback.reasoning_found_in_requests if r['reasoning_blocks']])}")
        print(f"   - Tool 调用次数: {call_counter['count']}")
        
        reasoning_preserved = False
        for req_info in callback.reasoning_found_in_requests[1:]:
            if req_info["reasoning_blocks"]:
                reasoning_preserved = True
                print(f"\n✅ 在第 {req_info['call_number']} 次 LLM 调用的请求中发现了之前的 reasoning blocks!")
                break
        
        if reasoning_preserved:
            print("\n✅ 测试通过：reasoning 内容在多轮调用间被正确保留和传递")
            return True
        else:
            print("\n⚠️  测试警告：未检测到 reasoning 在请求间传递")
            print("   可能原因:")
            print("   1. 模型未启用深度思考或不支持")
            print("   2. LangChain 版本不支持 reasoning 传递")
            print("   3. 火山引擎 API 响应格式与 OpenAI 不兼容")
            return False
            
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_3_inspect_message_structure():
    """
    测试3：详细检查消息结构，打印完整的 AIMessage 内容
    """
    print("\n" + "=" * 70)
    print("测试3：详细检查 AIMessage 结构")
    print("=" * 70)
    
    call_counter["count"] = 0
    model = get_deep_thinking_model()
    
    agent = create_agent(
        model=model,
        tools=[calculate_fibonacci],
        system_prompt="你是一个数学助手。",
    )
    
    try:
        result = agent.invoke(
            {"messages": [HumanMessage(content="计算第 3 个斐波那契数")]}
        )
        
        print("\n📋 完整消息历史:")
        for i, msg in enumerate(result["messages"]):
            print(f"\n--- 消息 #{i} ({type(msg).__name__}) ---")
            
            if isinstance(msg, AIMessage):
                print(f"  content type: {type(msg.content)}")
                if isinstance(msg.content, str):
                    print(f"  content: {msg.content[:200]}...")
                elif isinstance(msg.content, list):
                    print(f"  content blocks ({len(msg.content)}):")
                    for j, block in enumerate(msg.content):
                        if isinstance(block, dict):
                            block_type = block.get("type", "unknown")
                            print(f"    [{j}] type={block_type}")
                            if block_type == "reasoning":
                                summary = block.get("summary", [])
                                print(f"        summary items: {len(summary)}")
                                for s in summary[:2]:
                                    if isinstance(s, dict):
                                        text = s.get("text", "")[:80]
                                        print(f"        - {text}...")
                            elif block_type == "text":
                                text = block.get("text", "")[:80]
                                print(f"        text: {text}...")
                        else:
                            print(f"    [{j}] {str(block)[:80]}...")
                
                print(f"  additional_kwargs keys: {list(msg.additional_kwargs.keys())}")
                if "reasoning" in msg.additional_kwargs:
                    print(f"  ✅ additional_kwargs 中包含 'reasoning'")
                    reasoning = msg.additional_kwargs["reasoning"]
                    if isinstance(reasoning, dict):
                        print(f"     reasoning keys: {list(reasoning.keys())}")
                
                print(f"  tool_calls: {len(msg.tool_calls)} 个")
                for tc in msg.tool_calls:
                    print(f"    - {tc['name']}({tc['args']})")
                
                print(f"  response_metadata keys: {list(msg.response_metadata.keys()) if msg.response_metadata else 'None'}")
            
            elif isinstance(msg, ToolMessage):
                print(f"  tool_call_id: {msg.tool_call_id}")
                print(f"  content: {str(msg.content)[:100]}...")
            
            elif isinstance(msg, HumanMessage):
                print(f"  content: {str(msg.content)[:100]}...")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_4_direct_model_invocation():
    """
    测试4：直接调用模型（不通过 agent），检查原始响应中的 reasoning
    """
    print("\n" + "=" * 70)
    print("测试4：直接调用模型 - 检查原始响应中的 reasoning")
    print("=" * 70)
    
    model = get_deep_thinking_model()
    
    try:
        response = model.invoke([
            HumanMessage(content="简单解释一下什么是斐波那契数列，用一句话回答。")
        ])
        
        print(f"\n📋 模型响应详情:")
        print(f"  - 响应类型: {type(response).__name__}")
        print(f"  - content type: {type(response.content)}")
        
        if isinstance(response.content, str):
            print(f"  - content: {response.content[:200]}...")
        elif isinstance(response.content, list):
            print(f"  - content blocks: {len(response.content)}")
            for i, block in enumerate(response.content):
                if isinstance(block, dict):
                    print(f"    [{i}] type={block.get('type', 'unknown')}")
        
        print(f"\n  - additional_kwargs: {list(response.additional_kwargs.keys())}")
        
        if "reasoning" in response.additional_kwargs:
            print("  ✅ 发现 reasoning 在 additional_kwargs 中")
            reasoning = response.additional_kwargs["reasoning"]
            print(f"     reasoning type: {type(reasoning)}")
            if isinstance(reasoning, dict):
                print(f"     reasoning keys: {list(reasoning.keys())}")
                summary = reasoning.get("summary", [])
                print(f"     summary items: {len(summary)}")
                for s in summary[:3]:
                    if isinstance(s, dict):
                        text = s.get("text", "")[:100]
                        print(f"       - {text}...")
            return True
        else:
            print("  ⚠️  additional_kwargs 中没有 reasoning")
            
            has_reasoning_in_content = False
            if isinstance(response.content, list):
                for block in response.content:
                    if isinstance(block, dict) and block.get("type") == "reasoning":
                        has_reasoning_in_content = True
                        print("  ✅ 发现 reasoning 在 content blocks 中")
                        break
            
            return has_reasoning_in_content
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_5_inspect_actual_api_payload():
    """
    测试5：检查实际发送给 API 的 payload 中是否包含 reasoning
    
    通过 monkey patch _get_request_payload 来捕获实际发送的请求
    """
    print("\n" + "=" * 70)
    print("测试5：检查实际发送给 API 的 payload（关键测试）")
    print("=" * 70)
    
    call_counter["count"] = 0
    model = get_deep_thinking_model()
    
    captured_payloads = []
    original_get_request_payload = model._get_request_payload
    
    def patched_get_request_payload(messages, **kwargs):
        payload = original_get_request_payload(messages, **kwargs)
        captured_payloads.append({
            "call_number": len(captured_payloads) + 1,
            "input": payload.get("input", []),
            "messages_count": len(messages)
        })
        return payload
    
    model._get_request_payload = patched_get_request_payload
    
    agent = create_agent(
        model=model,
        tools=[calculate_fibonacci, get_current_time],
        system_prompt="你是一个助手。",
    )
    
    try:
        result = agent.invoke(
            {"messages": [HumanMessage(content="先计算第 3 个斐波那契数，再获取当前时间")]}
        )
        
        print(f"\n📋 捕获到 {len(captured_payloads)} 次 API 调用的 payload:")
        
        reasoning_in_payload = False
        for payload_info in captured_payloads:
            call_num = payload_info["call_number"]
            input_items = payload_info["input"]
            
            print(f"\n--- 第 {call_num} 次调用 ---")
            print(f"  input items 数量: {len(input_items)}")
            
            for i, item in enumerate(input_items):
                item_type = item.get("type", "unknown")
                print(f"  [{i}] type={item_type}")
                
                if item_type == "reasoning":
                    reasoning_in_payload = True
                    print(f"      ✅ 发现 reasoning item!")
                    summary = item.get("summary", [])
                    if summary:
                        for s in summary[:2]:
                            if isinstance(s, dict):
                                text = s.get("text", "")[:80]
                                print(f"         - {text}...")
                elif item_type == "message":
                    role = item.get("role", "")
                    content = item.get("content", [])
                    print(f"      role={role}, content blocks={len(content) if isinstance(content, list) else 'str'}")
                    if isinstance(content, list):
                        for j, block in enumerate(content):
                            if isinstance(block, dict):
                                block_type = block.get("type", "unknown")
                                print(f"        [{j}] type={block_type}")
                elif item_type == "function_call":
                    name = item.get("name", "")
                    print(f"      name={name}")
                elif item_type == "function_call_output":
                    output = str(item.get("output", ""))[:50]
                    print(f"      output={output}...")
        
        if reasoning_in_payload:
            print("\n✅ 测试通过：reasoning 在后续请求的 payload 中被正确传递!")
            return True
        else:
            print("\n❌ 测试失败：reasoning 没有在后续请求的 payload 中出现")
            print("   这意味着深度思考内容在 tool 调用循环中丢失了！")
            return False
            
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        model._get_request_payload = original_get_request_payload


def main():
    """运行所有测试"""
    print("\n" + "🚀" * 30)
    print("深度思考内容（Reasoning Content）保留测试")
    print("🚀" * 30)
    
    results = {}
    
    results["test_4_direct_model"] = test_4_direct_model_invocation()
    
    results["test_3_message_structure"] = test_3_inspect_message_structure()
    
    results["test_1_single_call"] = test_1_single_tool_call_reasoning()
    
    results["test_2_multi_calls"] = test_2_multi_tool_calls_reasoning_preservation()
    
    results["test_5_actual_payload"] = test_5_inspect_actual_api_payload()
    
    print("\n" + "=" * 70)
    print("📊 最终测试结果汇总")
    print("=" * 70)
    for test_name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败/警告"
        print(f"  {test_name}: {status}")
    
    all_passed = all(results.values())
    print("\n" + ("🎉 所有测试通过！" if all_passed else "⚠️  部分测试未通过，请查看详细输出"))
    
    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
