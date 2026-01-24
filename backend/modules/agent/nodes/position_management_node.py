"""工作流节点：持仓管理"""
import os
from pathlib import Path
from typing import Dict, Any, List

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from modules.agent.state import AgentState
from modules.agent.middleware.vision_middleware import VisionMiddleware
from modules.agent.middleware.workflow_trace_middleware import WorkflowTraceMiddleware
from modules.agent.utils.profit_protection import fmt6, fmt2, calculate_protection
from modules.config.settings import get_config
from modules.monitor.utils.logger import get_logger
from modules.agent.utils.trace_decorators import traced_node
from modules.agent.engine import get_engine

from modules.agent.tools.get_kline_image_tool import get_kline_image_tool
from modules.agent.tools.close_position_tool import close_position_tool
from modules.agent.tools.update_tp_sl_tool import update_tp_sl_tool

logger = get_logger('agent.nodes.position_management')


def _format_positions_context() -> str:
    """获取并格式化持仓信息"""
    try:
        eng = get_engine()
        if eng is None:
            return "【当前持仓】交易引擎未初始化，无法获取持仓信息"
        
        positions = eng.get_positions_summary()
        
        if not positions:
            return "【当前持仓】无持仓"
        
        result_parts = []
        result_parts.append(f"【当前持仓】共 {len(positions)} 个持仓\n")
        
        for idx, pos in enumerate(positions, 1):
            symbol = pos.get('symbol', 'UNKNOWN')
            side = pos.get('side', 'UNKNOWN')
            qty = pos.get('qty', 0.0)
            entry_price = pos.get('entry_price', 0.0)
            tp_price = pos.get('tp_price', 0.0)
            sl_price = pos.get('sl_price', 0.0)
            mark_price = pos.get('mark_price', 0.0)
            unrealized_pnl = pos.get('unrealized_pnl', 0.0)
            roe = pos.get('roe', 0.0)
            
            protection_info = calculate_protection(pos)
            
            position_block = [
                f"[持仓 #{idx}] {symbol} ({'多头' if side == 'long' else '空头'}持仓)",
                f"  持仓信息:",
                f"    数量: {fmt6(qty)}, 均价: ${fmt6(entry_price)}",
                f"    止盈: ${fmt6(tp_price)}, 止损: ${fmt6(sl_price)}",
                f"    当前价: ${fmt6(mark_price)}",
                f"    未实现盈亏: ${fmt2(unrealized_pnl)}, ROE: {fmt2(roe)}%",
            ]
            
            if protection_info:
                position_block.append(f"  浮盈保护分析:")
                position_block.append(f"    {protection_info}")
            else:
                position_block.append(f"  浮盈保护分析: 无SL或计算失败")
            
            position_block.append("")
            result_parts.append("\n".join(position_block))
        
        return "\n".join(result_parts)
    
    except Exception as e:
        logger.error(f"获取持仓信息失败: {e}")
        return f"【当前持仓】获取失败: {str(e)}"


@traced_node("position_management")
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

        tools = [
            get_kline_image_tool,
            close_position_tool,
            update_tp_sl_tool,
        ]
        
        prompt_path = os.path.join(os.path.dirname(__file__), 'prompts/position_management_prompt.md')
        with open(prompt_path, 'r', encoding='utf-8') as f:
            prompt = f.read().strip()
        
        middlewares = [
            VisionMiddleware(),
            WorkflowTraceMiddleware("position_management"),
        ]
        
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
        
        logger.info("开始执行持仓管理...")

        positions_context = _format_positions_context()
        
        if positions_context == "【当前持仓】无持仓":
            logger.info("无持仓需要管理，跳过持仓管理节点")
            return {"position_management_summary": "无持仓需要管理"}
        
        context_parts = []
        
        context_parts.append(positions_context)
        
        if state.position_next_focus:
            context_parts.append(f"\n【上一轮持仓关注重点】\n{state.position_next_focus}")
        
        context_parts.append(f"\n【市场环境】\n{market_context}")
        
        context_parts.append("\n---\n请基于以上持仓信息和市场环境，执行持仓管理与浮盈保护。")
        
        combined_context = "\n".join(context_parts)
        
        subagent_messages = [HumanMessage(content=combined_context)]
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
