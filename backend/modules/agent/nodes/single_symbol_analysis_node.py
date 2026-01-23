"""工作流节点：单币种深度分析"""
import os
from typing import Dict, Any

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from modules.agent.state import AgentState
from modules.agent.middleware.vision_middleware import VisionMiddleware
from modules.agent.middleware.workflow_trace_middleware import WorkflowTraceMiddleware
from modules.monitor.utils.logger import setup_logger
from modules.agent.utils.trace_decorators import traced_node

from modules.agent.tools.get_kline_tool import get_kline_tool
from modules.agent.tools.get_kline_image_tool import get_kline_image_tool
from modules.agent.tools.calc_metrics_tool import calc_metrics_tool
from modules.agent.tools.open_position_tool import open_position_tool
from modules.agent.tools.trend_comparison_tool import trend_comparison_tool

logger = setup_logger()


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
            temperature=0.8,
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
        
        specific_prompt = f"请基于以上市场信息，重点分析 {symbol} 的开仓机会并自主执行开仓操作。{position_status_hint}"
        
        # 补充账户/持仓/挂单/历史摘要上下文
        supplemental_context = [
            "【账户状态摘要】",
            str(state.account_summary or {}),
            "【当前正在分析币种持仓摘要】",
            str(state.positions_summary) if state.positions_summary else "无当前分析币种持仓",
            "【最近已平仓位摘要】",
            str(state.position_history) if state.position_history else "无历史仓位",
            "【上一轮该币种分析重点】",
            str((state.previous_symbol_focus_map or {}).get(symbol, "无")),
        ]
        
        subagent_messages = [
            HumanMessage(content=market_context),
            HumanMessage(content="\n".join(supplemental_context)),
            HumanMessage(content=specific_prompt),
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
