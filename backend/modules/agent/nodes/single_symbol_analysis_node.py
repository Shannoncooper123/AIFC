"""工作流节点：单币种深度分析"""
import os
from typing import Any, Dict, List, Optional

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from modules.agent.middleware.vision_middleware import VisionMiddleware
from modules.agent.middleware.workflow_trace_middleware import WorkflowTraceMiddleware
from modules.agent.state import AgentState
from modules.agent.tools.calc_metrics_tool import calc_metrics_tool
from modules.agent.tools.get_kline_image_tool import get_kline_image_tool
from modules.agent.tools.open_position_tool import open_position_tool
from modules.agent.tools.trend_comparison_tool import trend_comparison_tool
from modules.agent.utils.trace_decorators import traced_node
from modules.monitor.utils.logger import setup_logger

logger = setup_logger()


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
    """构建精简的补充上下文
    """

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


@traced_node("single_symbol_analysis")
def single_symbol_analysis_node(state: AgentState, *, config: RunnableConfig) -> Dict[str, Any]:
    """
    对当前状态中的单个币种进行深度分析，并封装开仓子Agent的逻辑。
    
    返回部分状态更新字典：{"analysis_results": {symbol: result}}
    """
    symbol = state.current_symbol
    if not symbol:
        return {"error": "single_symbol_analysis_node: 缺少 current_symbol，跳过分析。"}

    logger.info("=" * 60)
    logger.info(f"单币种分析节点执行: {symbol}")
    logger.info("=" * 60)

    # 使用更聚焦的上下文：优先符号级上下文；回退至总览
    market_context = state.symbol_contexts.get(symbol) or state.market_context
    if not market_context:
        logger.error(f"{symbol} 分析失败: 缺少上下文")
        return {"analysis_results": {symbol: "分析失败: 缺少上下文"}}

    try:
        # 定义工具
        tools = [
            get_kline_image_tool,
            trend_comparison_tool,
            calc_metrics_tool,
            open_position_tool,
        ]

        # 加载prompt
        prompt_path = os.path.join(os.path.dirname(__file__), 'prompts/single_symbol_analysis_prompt.md')
        with open(prompt_path, 'r', encoding='utf-8') as f:
            prompt = f.read().strip()

        # 创建middleware
        middlewares = [
            VisionMiddleware(),
            WorkflowTraceMiddleware("single_symbol_analysis"),
        ]

        # 初始化模型
        model = ChatOpenAI(
            model=os.getenv('AGENT_MODEL'),
            api_key=os.getenv('AGENT_API_KEY'),
            base_url=os.getenv('AGENT_BASE_URL') or None,
            temperature=0.2,
            timeout=600,
            max_tokens=16000,
            logprobs=False,
            extra_body={"thinking": {"type": "enabled"}},
        )

        # 创建Agent（使用 ProviderStrategy 约束原生结构化输出）
        subagent = create_agent(
            model=model,
            tools=tools,
            system_prompt=prompt,
            debug=False,
            middleware=middlewares,
        )

        # 执行Agent
        logger.info(f"开始为 {symbol} 执行开仓分析...")

        # 检测该币种是否已有持仓
        # 注意：在单币种分析场景下，positions_summary 已被过滤为只包含该币种的持仓（0或1个元素）
        has_existing_position = bool(state.positions_summary)  # positions_summary 非空表示该币种已有持仓
        position_status_hint = ""
        if has_existing_position:
            position_status_hint = f"\n重要提示：{symbol} 已有持仓，本次分析仅评估是否需要加仓（需极强信号+严格条件）或直接拒绝分析。"
            logger.warning(f"检测到 {symbol} 已有持仓: {state.positions_summary}")

        supplemental_context = _build_supplemental_context(
            symbol=symbol,
            account_summary=state.account_summary,
            positions_summary=state.positions_summary,
            position_history=state.position_history,
        )

        task_prompt = f"请基于以上市场信息，重点分析 {symbol} 的开仓机会并自主执行开仓操作。{position_status_hint}"

        combined_message = "\n\n".join([
            market_context,
            "\n".join(supplemental_context),
            task_prompt,
        ])

        subagent_messages = [
            HumanMessage(content=combined_message),
        ]
        result = subagent.invoke(
            {"messages": subagent_messages},
            config=config,
        )

        analysis_output = result["messages"][-1].content if isinstance(result, dict) else str(result)

        logger.info("=" * 60)
        logger.info(f"{symbol} 开仓分析完成 (返回长度: {len(analysis_output)})")
        logger.info("=" * 60)

        return {"analysis_results": {symbol: analysis_output}}

    except Exception as e:
        logger.error(f"{symbol} 开仓分析执行失败: {e}", exc_info=True)
        return {"analysis_results": {symbol: f"分析执行失败: {str(e)}"}}
