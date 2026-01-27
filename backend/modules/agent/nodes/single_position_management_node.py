"""工作流节点：单币种持仓管理"""
import os
from typing import Dict, Any

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from modules.agent.state import PositionManagementState
from modules.agent.utils.profit_protection import fmt6, fmt2, calculate_protection
from modules.agent.utils.trace_agent import create_trace_agent
from modules.agent.utils.trace_utils import traced_node
from modules.monitor.utils.logger import get_logger

from modules.agent.tools.get_kline_image_tool import get_kline_image_tool
from modules.agent.tools.close_position_tool import close_position_tool
from modules.agent.tools.update_tp_sl_tool import update_tp_sl_tool

logger = get_logger('agent.nodes.single_position_management')


def _format_single_position(pos: Dict[str, Any]) -> str:
    """格式化单个持仓信息"""
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
        f"【{symbol} 持仓信息】({'多头' if side == 'long' else '空头'})",
        f"  数量: {fmt6(qty)}, 均价: ${fmt6(entry_price)}",
        f"  止盈: ${fmt6(tp_price)}, 止损: ${fmt6(sl_price)}",
        f"  当前价: ${fmt6(mark_price)}",
        f"  未实现盈亏: ${fmt2(unrealized_pnl)}, ROE: {fmt2(roe)}%",
    ]
    
    if protection_info:
        position_block.append(f"  浮盈保护分析: {protection_info}")
    else:
        position_block.append(f"  浮盈保护分析: 无SL或计算失败")
    
    return "\n".join(position_block)


@traced_node("manage_position")
def single_position_management_node(
    state: PositionManagementState,
    *,
    config: RunnableConfig
) -> Dict[str, Any]:
    """
    执行单币种持仓管理逻辑。
    
    Args:
        state: 单币种持仓管理状态（包含该币种的持仓信息）
        config: 本次运行配置
        
    Returns:
        部分状态更新字典，如 {"position_management_results": {symbol: summary}}
    """
    symbol = state.current_symbol
    position = state.position_info
    
    logger.info("=" * 60)
    logger.info(f"单币种持仓管理节点执行: {symbol}")
    logger.info("=" * 60)

    if not position:
        logger.warning(f"{symbol} 无持仓信息，跳过管理")
        return {"position_management_results": {symbol: "无持仓信息"}}

    try:
        tools = [
            get_kline_image_tool,
            close_position_tool,
            update_tp_sl_tool,
        ]
        
        prompt_path = os.path.join(
            os.path.dirname(__file__),
            'prompts/single_position_management_prompt.md'
        )
        with open(prompt_path, 'r', encoding='utf-8') as f:
            prompt = f.read().strip()
        
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
        
        subagent = create_trace_agent(
            model=model,
            tools=tools,
            system_prompt=prompt,
            node_name=f"manage_position_{symbol}",
        )
        
        logger.info(f"开始执行 {symbol} 持仓管理...")

        positions_context = _format_single_position(position)
        
        combined_context = f"{positions_context}\n\n---\n请基于以上 {symbol} 持仓信息，执行持仓管理与浮盈保护。"
        
        subagent_messages = [HumanMessage(content=combined_context)]
        result = subagent.invoke(
            {"messages": subagent_messages},
            config=config,
        )
        
        summary = result["messages"][-1].content if isinstance(result, dict) else str(result)
        
        logger.info("=" * 60)
        logger.info(f"{symbol} 持仓管理完成 (返回长度: {len(summary)})")
        logger.info("=" * 60)
        
        return {"position_management_results": {symbol: summary}}

    except Exception as e:
        logger.error(f"{symbol} 持仓管理执行失败: {e}", exc_info=True)
        return {"position_management_results": {symbol: f"执行失败: {str(e)}"}}
