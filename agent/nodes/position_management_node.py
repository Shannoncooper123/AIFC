"""工作流节点：持仓管理"""
import os
from pathlib import Path
from typing import Dict, Any

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from agent.state import AgentState
from agent.middleware.vision_middleware import VisionMiddleware
from config.settings import get_config
from monitor_module.utils.logger import setup_logger

# 结构化输出支持
from pydantic import BaseModel, Field
from langchain.agents.structured_output import ProviderStrategy

# 导入所需工具
from agent.tools.get_positions_tool import get_positions_tool
from agent.tools.get_kline_tool import get_kline_tool
from agent.tools.get_kline_image_tool import get_kline_image_tool
from agent.tools.close_position_tool import close_position_tool
from agent.tools.update_tp_sl_tool import update_tp_sl_tool
from agent.tools.cancel_limit_order_tool import cancel_limit_order_tool

logger = setup_logger()

def position_management_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    执行持仓管理逻辑，并封装持仓管理子Agent的逻辑。
    
    Args:
        state: 当前工作流状态
        config: 本次运行配置
        
    Returns:
        部分状态更新字典，如 {"position_management_summary": "..."}
    """
    logger.info("=" * 60)
    logger.info("持仓管理节点执行")
    logger.info("=" * 60)

    market_context = state.market_context
    if not market_context:
        logger.error("持仓管理失败: 缺少 market_context")
        return {"position_management_summary": "执行失败: 缺少 market_context"}

    try:
        cfg = get_config()
        
        # 从运行时配置中获取 session_id（RunnableConfig 已在上层统一包装）
        session_id = config.get("configurable", {}).get("session_id", "default_session")

        # 定义工具
        tools = [
            get_positions_tool,
            get_kline_image_tool,
            close_position_tool,
            update_tp_sl_tool,
        ]
        
        # 加载prompt
        prompt_path = os.path.join(os.path.dirname(__file__), 'prompts/position_management_prompt.md')
        with open(prompt_path, 'r', encoding='utf-8') as f:
            prompt = f.read().strip()
        
        # 创建middleware
        middlewares = [
            VisionMiddleware(),
        ]
        
        # 初始化模型
        model = ChatOpenAI(
            model=os.getenv('AGENT_MODEL'),
            api_key=os.getenv('AGENT_API_KEY'),
            base_url=os.getenv('AGENT_BASE_URL') or None,
            temperature=0.8,
            timeout=600,
            max_tokens=16000,
            logprobs=False,
            extra_body={"thinking": {"type": "enabled"}},
        )
        
        subagent = create_agent(
            model=model,
            tools=tools,
            system_prompt=prompt,
            debug=False,
            middleware=middlewares,
        )
        
        # 执行Agent
        logger.info("开始执行持仓管理...")

        # 构造包含下一轮持仓关注重点的上下文
        context_parts = []
        if state.position_next_focus:
            context_parts.append("【上一轮持仓关注重点】")
            context_parts.append(state.position_next_focus)
            context_parts.append("\n")
        context_parts.append(market_context)
        full_context = "\n".join(context_parts)

        subagent_messages = [
            HumanMessage(content=full_context),
            HumanMessage(content="请基于以上市场信息，并参考【上一轮持仓关注重点】，管理所有持仓并执行浮盈保护。")
        ]
        result = subagent.invoke(
            {"messages": subagent_messages},
            config=config,
        )
        
        summary = result["messages"][-1].content if isinstance(result, dict) else str(result)
        
        logger.info("=" * 60)
        logger.info(f"持仓管理完成 (返回长度: {len(summary)})")
        logger.info("=" * 60)
        
        return {"position_management_summary": summary}

    except Exception as e:
        logger.error(f"持仓管理执行失败: {e}", exc_info=True)
        return {"position_management_summary": f"执行失败: {str(e)}"}