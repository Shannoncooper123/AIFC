"""工作流节点：单币种深度分析（双向分析：做多+做空）"""
import asyncio
import os
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from modules.agent.state import SymbolAnalysisState
from modules.agent.tools.trend_comparison_tool import trend_comparison_tool
from modules.agent.tools.calc_metrics_tool import calc_metrics_tool
from modules.agent.utils.kline_utils import fetch_klines, get_current_price, format_price
from modules.agent.utils.model_factory import get_model_factory, with_async_retry
from modules.agent.utils.trace_utils import create_trace_agent, traced_node
from modules.monitor.utils.logger import get_logger

logger = get_logger('agent.nodes.single_symbol_analysis')

ANALYSIS_INTERVALS = ["4h", "1h", "15m"]


def _format_account_summary(account: Dict[str, Any]) -> str:
    """格式化账户摘要，只保留关键信息"""
    if not account:
        return "账户信息不可用"

    balance = account.get('balance', 0)
    equity = account.get('equity', 0)
    margin_usage = account.get('margin_usage_rate', 0)
    positions_count = account.get('positions_count', 0)
    realized_pnl = account.get('realized_pnl', 0)

    return (
        f"余额: ${balance:.2f} | 净值: ${equity:.2f} | "
        f"保证金利用率: {margin_usage:.1f}% | "
        f"持仓数: {positions_count} | 已实现盈亏: ${realized_pnl:.2f}"
    )


def _format_current_position(positions: List[Dict[str, Any]]) -> str:
    """格式化当前币种持仓，精简显示"""
    if not positions:
        return "无"

    pos = positions[0]
    side = pos.get('side', '?')
    entry = pos.get('entry_price', 0)
    mark = pos.get('mark_price', 0)
    pnl = pos.get('unrealized_pnl', 0)
    roe = pos.get('roe', 0) * 100
    tp = pos.get('tp_price', 0)
    sl = pos.get('sl_price', 0)
    leverage = pos.get('leverage', 1)

    return (
        f"方向: {side.upper()} {leverage}x | "
        f"入场: ${entry:.6f} | 当前: ${mark:.6f} | "
        f"浮盈: ${pnl:.2f} ({roe:+.1f}%) | "
        f"止盈: ${tp:.6f} | 止损: ${sl:.6f}"
    )


def _format_position_history(
    history: List[Dict[str, Any]],
    current_symbol: str,
    max_items: int = 3
) -> str:
    """格式化历史仓位，只显示当前分析币种的历史记录"""
    if not history:
        return "无"

    symbol_history = [h for h in history if h.get('symbol') == current_symbol]
    if not symbol_history:
        return "无"

    lines = [_format_single_history(h) for h in symbol_history[:max_items]]
    return "\n".join(lines)


def _format_single_history(h: Dict[str, Any]) -> str:
    """格式化单条历史记录"""
    symbol = h.get('symbol', '?')
    side = h.get('side', '?')
    entry = h.get('entry_price', 0)
    close = h.get('close_price', 0)
    pnl = h.get('realized_pnl', 0)
    reason = h.get('close_reason', '?')

    pnl_sign = "+" if pnl >= 0 else ""
    return f"  • {symbol} {side.upper()}: ${entry:.6f}→${close:.6f}, 盈亏: {pnl_sign}${pnl:.2f}, 原因: {reason}"


def _build_supplemental_context(
    symbol: str,
    account_summary: Optional[Dict[str, Any]],
    positions_summary: Optional[List[Dict[str, Any]]],
    position_history: Optional[List[Dict[str, Any]]],
) -> List[str]:
    """构建精简的补充上下文"""

    context = [
        "【账户状态】",
        _format_account_summary(account_summary or {}),
        "",
        f"【{symbol} 当前持仓】",
        _format_current_position(positions_summary or []),
        "",
        "【近期平仓记录】",
        _format_position_history(position_history or [], symbol),
    ]

    return context


def _generate_kline_images(symbol: str, intervals: List[str]) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """预生成多周期K线图像
    
    Args:
        symbol: 交易对
        intervals: 时间周期列表
        
    Returns:
        (images, image_metas): images 用于构建消息，image_metas 用于 trace 匹配
    """
    from modules.agent.tools.chart_renderer_pillow import render_kline_chart_pillow
    
    images = []
    image_metas = []
    
    logger.info(f"为 {symbol} 预生成 {len(intervals)} 个周期的K线图像: {intervals}")
    
    for interval in intervals:
        try:
            fetch_limit = 200
            display_limit = 100
            
            logger.info(f"{symbol} {interval} 获取K线用于分析图像")
            
            klines, error = fetch_klines(symbol, interval, fetch_limit)
            
            if error or not klines:
                logger.warning(f"未获取到 {symbol} {interval} K线数据: {error}")
                continue
            
            image_base64 = render_kline_chart_pillow(klines, symbol, interval, display_limit)
            
            images.append({
                "interval": interval,
                "image_base64": image_base64,
            })
            image_metas.append({"symbol": symbol, "interval": interval})
            
            logger.info(f"生成 {symbol} {interval} 分析图像成功")
            
        except Exception as e:
            logger.error(f"生成 {symbol} {interval} 图像失败: {e}")
            continue
    
    return images, image_metas


def _build_multimodal_content(
    symbol: str,
    market_context: str,
    supplemental_context: str,
    images: List[Dict[str, Any]],
    position_status_hint: str,
    direction: str,
    current_price: Optional[float],
) -> List[Dict[str, Any]]:
    """构建多模态消息内容（含K线图像）
    
    Args:
        symbol: 交易对
        market_context: 市场上下文
        supplemental_context: 补充上下文（账户、持仓等）
        images: K线图像列表
        position_status_hint: 持仓状态提示
        direction: 分析方向 "long" 或 "short"
        current_price: 当前价格
        
    Returns:
        多模态内容列表
    """
    content = []
    
    direction_cn = "做多" if direction == "long" else "做空"
    price_str = f"${format_price(current_price)}" if current_price else "获取失败"
    
    text_part = f"""【待分析币种】{symbol}
【当前价格】{price_str}
【分析方向】{direction_cn}

{market_context}

{supplemental_context}

【多周期K线图像】
以下是 {symbol} 的 4h/1h/15m 三个周期的K线图（含技术指标：EMA、MACD、RSI、Bollinger Bands），请直接基于图像进行{direction_cn}方向的技术分析：
"""
    content.append({"type": "text", "text": text_part})
    
    for img_data in images:
        interval = img_data["interval"]
        content.append({"type": "text", "text": f"\n--- {interval} 周期 ---"})
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{img_data['image_base64']}",
                "detail": "high"
            }
        })
    
    task_prompt = f"\n请基于以上K线图像，对 {symbol} 进行{direction_cn}方向的多周期技术分析，输出结构化的分析结论。{position_status_hint}"
    content.append({"type": "text", "text": task_prompt})
    
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
        trend_comparison_tool,
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
    image_metas: List[Dict[str, str]],
    config: RunnableConfig,
) -> Tuple[str, str, Optional[str]]:
    """
    异步执行单方向分析（带指数退避重试）
    
    Args:
        direction: "long" 或 "short"
        symbol: 交易对
        multimodal_content: 多模态消息内容（含图像）
        image_metas: 图像元数据
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
            additional_kwargs={"_image_metas": image_metas}
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
    market_context: str,
    supplemental_context: str,
    images: List[Dict[str, Any]],
    image_metas: List[Dict[str, str]],
    position_status_hint: str,
    current_price: Optional[float],
    config: RunnableConfig,
) -> Tuple[Optional[str], Optional[str], List[str]]:
    """
    并行执行做多和做空分析（使用 asyncio.gather）
    
    contextvars 会自动传播到每个 async task，无需手动 copy context
    
    Args:
        symbol: 交易对
        market_context: 市场上下文
        supplemental_context: 补充上下文
        images: K线图像列表
        image_metas: 图像元数据
        position_status_hint: 持仓状态提示
        current_price: 当前价格
        config: RunnableConfig
        
    Returns:
        (long_result, short_result, errors) 元组
    """
    long_content = _build_multimodal_content(
        symbol, market_context, supplemental_context, images, position_status_hint, "long", current_price
    )
    short_content = _build_multimodal_content(
        symbol, market_context, supplemental_context, images, position_status_hint, "short", current_price
    )
    
    tasks = [
        _run_directional_analysis_async("long", symbol, long_content, image_metas, config),
        _run_directional_analysis_async("short", symbol, short_content, image_metas, config),
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
    1. 预生成 4h/1h/15m 三个周期的K线图像
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

    market_context = state.symbol_contexts.get(symbol) or state.market_context
    if not market_context:
        logger.error(f"{symbol} 分析失败: 缺少上下文")
        return {"analysis_results": {symbol: "分析失败: 缺少上下文"}}

    try:
        logger.info(f"开始为 {symbol} 预生成K线图像...")
        images, image_metas = _generate_kline_images(symbol, ANALYSIS_INTERVALS)
        
        if not images:
            logger.error(f"{symbol} 无法生成K线图像，分析中止")
            return {"analysis_results": {symbol: "分析失败: 无法生成K线图像"}}
        
        logger.info(f"{symbol} 成功生成 {len(images)} 个周期的K线图像")
        
        current_price = get_current_price(symbol)
        if current_price:
            logger.info(f"{symbol} 当前价格: ${format_price(current_price)}")
        else:
            logger.warning(f"{symbol} 无法获取当前价格")
        
        has_existing_position = bool(state.positions_summary)
        position_status_hint = ""
        if has_existing_position:
            position_status_hint = f"\n重要提示：{symbol} 已有持仓，分析时需考虑加仓可能性（需极强信号）。"
            logger.warning(f"检测到 {symbol} 已有持仓: {state.positions_summary}")

        supplemental_context = _build_supplemental_context(
            symbol=symbol,
            account_summary=state.account_summary,
            positions_summary=state.positions_summary,
            position_history=state.position_history,
        )
        supplemental_context_str = "\n".join(supplemental_context)

        logger.info(f"开始为 {symbol} 执行双向技术分析（做多+做空并行，asyncio）...")
        
        long_result, short_result, errors = asyncio.run(
            _run_parallel_analysis(
                symbol,
                market_context,
                supplemental_context_str,
                images,
                image_metas,
                position_status_hint,
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
