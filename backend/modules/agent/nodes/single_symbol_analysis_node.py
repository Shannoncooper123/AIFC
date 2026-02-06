"""工作流节点：单币种深度分析（双向分析：做多+做空）"""
import asyncio
import os
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from modules.agent.state import SymbolAnalysisState
from modules.agent.tools.calc_metrics_tool import calc_metrics_tool
from modules.agent.tools.get_kline_image_tool import get_kline_image_tool
from modules.agent.utils.kline_utils import get_current_price, format_price
from modules.agent.utils.model_factory import get_model_factory, with_async_retry
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
    account_summary: Optional[Dict[str, Any]],
) -> List[str]:
    """构建精简的补充上下文，只包含账户信息"""

    context = [
        "【账户状态】",
        _format_account_summary(account_summary or {}),
    ]

    return context



def _build_multimodal_content(
    symbol: str,
    supplemental_context: str,
    direction: str,
    current_price: Optional[float],
) -> List[Dict[str, Any]]:
    """构建消息内容（不再预生成图像，由 agent 自行调用工具获取）
    
    Args:
        symbol: 交易对
        supplemental_context: 补充上下文（账户信息）
        direction: 分析方向 "long" 或 "short"
        current_price: 当前价格
        
    Returns:
        消息内容列表
    """
    content = []
    
    direction_cn = "做多" if direction == "long" else "做空"
    price_str = f"${format_price(current_price)}" if current_price else "获取失败"
    
    text_part = f"""【待分析币种】{symbol}
【当前价格】{price_str}
【分析方向】{direction_cn}

{supplemental_context}

请利用 get_kline_image 工具，严格按照 1h -> 15m -> 3m 的顺序，逐个获取K线图像并进行分析。"""
    content.append({"type": "text", "text": text_part})
    
    return content


def _create_directional_subagent(direction: str) -> Tuple[Any, str]:
    """
    创建方向性分析 subagent
    
    Args:
        direction: "long" 或 "short"
        
    Returns:
        (subagent, node_name) 元组
    """
    tools = [
        get_kline_image_tool,
        calc_metrics_tool,
    ]
    
    prompt_filename = f"single_symbol_analysis_{direction}_prompt.md"
    prompt_path = os.path.join(os.path.dirname(__file__), f'prompts/{prompt_filename}')
    with open(prompt_path, 'r', encoding='utf-8') as f:
        prompt = f.read().strip()
    
    node_name = f"single_symbol_analysis_{direction}"
    
    model = get_model_factory().get_analysis_model()
    
    subagent = create_trace_agent(
        model=model,
        tools=tools,
        system_prompt=prompt,
        node_name=node_name,
    )
    
    return subagent, node_name


async def _run_directional_analysis_async(
    direction: str,
    symbol: str,
    multimodal_content: List[Dict[str, Any]],
    config: RunnableConfig,
) -> Tuple[str, str, Optional[str]]:
    """
    异步执行单方向分析（带指数退避重试）
    
    Args:
        direction: "long" 或 "short"
        symbol: 交易对
        multimodal_content: 消息内容
        config: RunnableConfig（包含 trace context）
        
    Returns:
        (direction, result, error) 元组
    """
    direction_cn = "做多" if direction == "long" else "做空"
    
    @with_async_retry(max_retries=5, retryable_exceptions=(Exception,))
    async def _invoke_with_retry():
        subagent, _ = _create_directional_subagent(direction)
        subagent_messages = [HumanMessage(
            content=multimodal_content,
        )]
        return await subagent.ainvoke({"messages": subagent_messages}, config=config)
    
    try:
        logger.info(f"开始 {symbol} {direction_cn}分析...")
        
        result = await _invoke_with_retry()
        
        analysis_output = result["messages"][-1].content if isinstance(result, dict) else str(result)
        
        logger.info(f"{symbol} {direction_cn}分析完成 (返回长度: {len(analysis_output)})")
        
        return direction, analysis_output, None
        
    except Exception as e:
        logger.error(f"{symbol} {direction_cn}分析执行失败 (重试耗尽): {e}", exc_info=True)
        return direction, "", str(e)


async def _run_parallel_analysis(
    symbol: str,
    supplemental_context: str,
    current_price: Optional[float],
    config: RunnableConfig,
) -> Tuple[Optional[str], Optional[str], List[str]]:
    """
    并行执行做多和做空分析（使用 asyncio.gather）
    
    contextvars 会自动传播到每个 async task，无需手动 copy context
    
    Args:
        symbol: 交易对
        supplemental_context: 补充上下文
        current_price: 当前价格
        config: RunnableConfig
        
    Returns:
        (long_result, short_result, errors) 元组
    """
    long_content = _build_multimodal_content(
        symbol, supplemental_context, "long", current_price
    )
    short_content = _build_multimodal_content(
        symbol, supplemental_context, "short", current_price
    )
    
    tasks = [
        _run_directional_analysis_async("long", symbol, long_content, config),
        _run_directional_analysis_async("short", symbol, short_content, config),
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    long_result = None
    short_result = None
    errors = []
    
    for result in results:
        if isinstance(result, Exception):
            errors.append(str(result))
            continue
        
        direction, output, error = result
        if error:
            errors.append(f"{direction}: {error}")
        else:
            if direction == "long":
                long_result = output
            else:
                short_result = output
    
    return long_result, short_result, errors


@traced_node("single_symbol_analysis")
def single_symbol_analysis_node(state: SymbolAnalysisState, *, config: RunnableConfig) -> Dict[str, Any]:
    """
    对当前状态中的单个币种进行双向深度技术分析（做多+做空）。
    
    本节点：
    1. 预生成 1h/15m/3m 三个周期的K线图像
    2. 将图像直接传入 HumanMessage，供 LLM 进行视觉分析
    3. 并行执行两个 subagent（使用 asyncio 实现并行，contextvars 自动传播）：
       - Long Subagent: 专注于识别做多机会
       - Short Subagent: 专注于识别做空机会
    
    两个 subagent 的分析结论将合并后传递给下游的开仓决策节点。
    
    返回部分状态更新字典：{"analysis_results": {symbol: combined_result}}
    """
    symbol = state.current_symbol
    if not symbol:
        return {"error": "single_symbol_analysis_node: 缺少 current_symbol，跳过分析。"}

    logger.info("=" * 60)
    logger.info(f"单币种双向分析节点执行: {symbol}")
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

        logger.info(f"开始为 {symbol} 执行双向技术分析（做多+做空并行，asyncio）...")
        
        long_result, short_result, errors = asyncio.run(
            _run_parallel_analysis(
                symbol,
                supplemental_context_str,
                current_price,
                config
            )
        )
        
        combined_analysis_parts = []
        
        if long_result:
            combined_analysis_parts.append("=" * 40)
            combined_analysis_parts.append("【做多方向分析】")
            combined_analysis_parts.append("=" * 40)
            combined_analysis_parts.append(long_result)
        else:
            combined_analysis_parts.append("【做多方向分析】: 分析失败")
        
        combined_analysis_parts.append("")
        
        if short_result:
            combined_analysis_parts.append("=" * 40)
            combined_analysis_parts.append("【做空方向分析】")
            combined_analysis_parts.append("=" * 40)
            combined_analysis_parts.append(short_result)
        else:
            combined_analysis_parts.append("【做空方向分析】: 分析失败")
        
        if errors:
            combined_analysis_parts.append("")
            combined_analysis_parts.append("【分析错误】")
            combined_analysis_parts.extend(errors)
        
        combined_analysis = "\n".join(combined_analysis_parts)

        logger.info("=" * 60)
        logger.info(f"{symbol} 双向技术分析完成 (合并结果长度: {len(combined_analysis)})")
        logger.info("=" * 60)

        return {"analysis_results": {symbol: combined_analysis}, "current_symbol": symbol}

    except Exception as e:
        logger.error(f"{symbol} 双向技术分析执行失败: {e}", exc_info=True)
        return {"analysis_results": {symbol: f"分析执行失败: {str(e)}"}, "current_symbol": symbol}
