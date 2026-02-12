"""工作流节点：单币种深度分析（统一分析：先判断市场状态，再决定方向）"""
import os
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from modules.agent.state import SymbolAnalysisState
from modules.agent.tools.calc_metrics_tool import calc_metrics_tool
from modules.agent.tools.get_kline_image_tool import get_kline_image_tool
from modules.agent.utils.kline_utils import get_current_price, format_price
from modules.agent.utils.model_factory import get_model_factory, with_retry
from modules.agent.utils.trace_utils import create_trace_agent, traced_node
from modules.monitor.utils.logger import get_logger

logger = get_logger('agent.nodes.single_symbol_analysis')

ANALYSIS_INTERVALS = ["1h", "15m", "3m"]

HARDCODED_ACCOUNT_SUMMARY_STR = (
    "余额: $10000.00 | 净值: $10000.00 | "
    "保证金利用率: 0.0% | "
    "持仓数: 0 | 已实现盈亏: $0.00"
)


def _format_account_summary(account: Dict[str, Any]) -> str:
    """格式化账户摘要，始终返回硬编码的账户状态"""
    return HARDCODED_ACCOUNT_SUMMARY_STR


def _build_supplemental_context(
    account_summary: Dict[str, Any] | None,
) -> List[str]:
    """构建精简的补充上下文，只包含账户信息"""
    context = [
        "【账户状态】",
        _format_account_summary(account_summary or {}),
    ]
    return context


def _build_message_content(
    symbol: str,
    supplemental_context: str,
    current_price: float | None,
    analysis_attention_points: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """构建消息内容
    
    Args:
        symbol: 交易对
        supplemental_context: 补充上下文（账户信息）
        current_price: 当前价格
        analysis_attention_points: 强化学习注入的分析节点注意事项（可选）
        
    Returns:
        消息内容列表
    """
    content = []
    
    price_str = f"${format_price(current_price)}" if current_price else "获取失败"
    
    text_part = f"""【待分析币种】{symbol}
【当前价格】{price_str}

{supplemental_context}
"""
    
    if analysis_attention_points and len(analysis_attention_points) > 0:
        text_part += """
【⚠️ 注意事项（基于上轮复盘）】
请在分析时务必关注以下要点：
"""
        for i, point in enumerate(analysis_attention_points, 1):
            text_part += f"{i}. {point}\n"
        text_part += "\n"
    
    text_part += """请利用 get_kline_image 工具，严格按照 1h -> 15m -> 3m 的顺序，逐个获取K线图像并进行分析。
分析完成后，基于市场状态判断最优方向（做多 / 做空 / 观望），并给出具体的交易计划或观望理由。"""
    content.append({"type": "text", "text": text_part})
    
    return content


def _create_analysis_agent():
    """
    创建统一的市场分析 agent
    
    Returns:
        (agent, node_name) 元组
    """
    tools = [
        get_kline_image_tool,
        calc_metrics_tool,
    ]
    
    prompt_path = os.path.join(os.path.dirname(__file__), 'prompts/single_symbol_analysis_prompt.md')
    with open(prompt_path, 'r', encoding='utf-8') as f:
        prompt = f.read().strip()
    
    node_name = "single_symbol_analysis"
    
    model = get_model_factory().get_analysis_model()
    
    agent = create_trace_agent(
        model=model,
        tools=tools,
        system_prompt=prompt,
        node_name=node_name,
    )
    
    return agent, node_name


def _extract_analysis_attention_points(config: RunnableConfig) -> Optional[List[str]]:
    """从config中提取分析节点的注意事项
    
    Args:
        config: workflow 配置
        
    Returns:
        注意事项列表，如果没有则返回 None
    """
    configurable = config.get("configurable", {})
    reinforcement_feedback = configurable.get("reinforcement_feedback")
    
    if not reinforcement_feedback:
        return None
    
    analysis_fb = getattr(reinforcement_feedback, "analysis_node_feedback", None)
    if analysis_fb is None:
        if isinstance(reinforcement_feedback, dict):
            analysis_fb = reinforcement_feedback.get("analysis_node_feedback")
    
    if analysis_fb:
        if hasattr(analysis_fb, "attention_points"):
            return analysis_fb.attention_points
        elif isinstance(analysis_fb, dict):
            return analysis_fb.get("attention_points", [])
    
    return None


@traced_node("single_symbol_analysis")
def single_symbol_analysis_node(state: SymbolAnalysisState, *, config: RunnableConfig) -> Dict[str, Any]:
    """
    对当前状态中的单个币种进行统一的深度技术分析。
    
    本节点：
    1. 使用单一 Agent 分析市场状态
    2. Agent 自行获取 1h/15m/3m 三个周期的K线图像
    3. 基于市场状态判断最优方向（做多/做空/观望）
    4. 输出分析结论传递给下游的开仓决策节点
    
    核心改进：先判断市场状态，再决定方向，避免双向分析的冲突问题。
    支持强化学习反馈注入：如果 config 中包含 reinforcement_feedback，会提取分析节点的注意事项并注入到消息中。
    
    返回部分状态更新字典：{"analysis_results": {symbol: analysis_result}}
    """
    symbol = state.current_symbol
    if not symbol:
        return {"error": "single_symbol_analysis_node: 缺少 current_symbol，跳过分析。"}

    analysis_attention_points = _extract_analysis_attention_points(config)
    has_feedback = analysis_attention_points and len(analysis_attention_points) > 0

    logger.info("=" * 60)
    feedback_info = " (带强化学习反馈)" if has_feedback else ""
    logger.info(f"单币种统一分析节点执行{feedback_info}: {symbol}")
    if has_feedback:
        logger.info(f"注入注意事项: {analysis_attention_points}")
    logger.info("=" * 60)

    try:
        current_price = get_current_price(symbol)
        if current_price:
            logger.info(f"{symbol} 当前价格: ${format_price(current_price)}")
        else:
            logger.warning(f"{symbol} 无法获取当前价格")

        supplemental_context = _build_supplemental_context(
            account_summary=state.account_summary,
        )
        supplemental_context_str = "\n".join(supplemental_context)

        message_content = _build_message_content(
            symbol=symbol,
            supplemental_context=supplemental_context_str,
            current_price=current_price,
            analysis_attention_points=analysis_attention_points,
        )

        agent, _ = _create_analysis_agent()
        
        agent_messages = [HumanMessage(content=message_content)]

        @with_retry(max_retries=5, retryable_exceptions=(Exception,))
        def _invoke_with_retry():
            return agent.invoke({"messages": agent_messages}, config=config)

        logger.info(f"开始为 {symbol} 执行统一技术分析...")
        result = _invoke_with_retry()

        analysis_output = result["messages"][-1].content if isinstance(result, dict) else str(result)

        logger.info("=" * 60)
        logger.info(f"{symbol} 统一技术分析完成 (返回长度: {len(analysis_output)})")
        logger.info("=" * 60)

        return {"analysis_results": {symbol: analysis_output}, "current_symbol": symbol}

    except Exception as e:
        logger.error(f"{symbol} 统一技术分析执行失败: {e}", exc_info=True)
        return {"analysis_results": {symbol: f"分析执行失败: {str(e)}"}, "current_symbol": symbol}
