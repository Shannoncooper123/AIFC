"""构建 LangGraph 工作流"""
from typing import Dict, Any, Union

from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnableConfig

from modules.agent.state import AgentState, SymbolAnalysisState
from modules.agent.nodes.context_injection_node import context_injection_node
from modules.agent.nodes.reporting_node import reporting_node
from modules.agent.nodes.single_symbol_analysis_node import single_symbol_analysis_node
from modules.agent.nodes.opening_decision_node import opening_decision_node
from modules.agent.nodes.position_management_node import position_management_node
from modules.agent.conditional_edges import after_opportunity_screening
from modules.agent.utils.workflow_trace_storage import (
    get_current_run_id,
    get_current_span_id,
    set_current_symbol,
    start_span,
    end_span,
)


def _barrier_node(state: Union[AgentState, SymbolAnalysisState], config: RunnableConfig) -> Dict[str, Any]:
    """占位节点，用于 super step 对齐"""
    return {}


def _create_symbol_analysis_subgraph() -> StateGraph:
    """创建单币种分析子图（使用精简的 SymbolAnalysisState）"""
    subgraph = StateGraph(SymbolAnalysisState)
    subgraph.add_node("analysis", single_symbol_analysis_node)
    subgraph.add_node("decision", opening_decision_node)
    subgraph.set_entry_point("analysis")
    subgraph.add_edge("analysis", "decision")
    subgraph.add_edge("decision", END)
    return subgraph.compile()


_compiled_subgraph = _create_symbol_analysis_subgraph()


def _symbol_analysis_node(state: SymbolAnalysisState, config: RunnableConfig) -> Dict[str, Any]:
    """
    子图包装节点：执行单币种分析 + 开仓决策。
    创建父 span 以实现层级化 trace 结构。
    """
    run_id = get_current_run_id()
    parent_span_id = get_current_span_id()
    symbol = state.current_symbol
    
    if symbol:
        set_current_symbol(symbol)
    
    span_id = None
    if run_id:
        span_id = start_span(
            run_id=run_id,
            node="analyze_symbol",
            parent_span_id=parent_span_id,
            symbol=symbol,
        )
    
    try:
        result = _compiled_subgraph.invoke(state, config)
        
        output_summary = {
            "analyzed_symbol": symbol,
            "has_analysis": bool(result.get("analysis_results")),
            "has_decision": bool(result.get("opening_decision_results")),
        }
        
        if run_id and span_id:
            end_span(run_id, span_id, status="success", output_summary=output_summary)
        
        return {
            "analysis_results": result.get("analysis_results", {}),
            "opening_decision_results": result.get("opening_decision_results", {}),
        }
    except Exception as e:
        if run_id and span_id:
            end_span(run_id, span_id, status="error", error=str(e))
        raise


def create_workflow(config: Dict[str, Any]) -> StateGraph:
    """
    创建并配置 LangGraph 工作流。
    
    架构（整体一层 super step）：
    - context_injection: 注入上下文，筛选机会
    - position_management: 持仓管理（与分析并行）
    - analyze_symbol: 子图（analysis + decision），通过 Send 分发
    - barrier: 无机会时的占位节点
    - join_node: 汇聚节点
    - reporting: 生成最终报告
    """
    workflow = StateGraph(AgentState)

    workflow.add_node("context_injection", context_injection_node)
    workflow.add_node("position_management", position_management_node)
    workflow.add_node("analyze_symbol", _symbol_analysis_node)
    workflow.add_node("barrier", _barrier_node)
    workflow.add_node("join_node", _barrier_node)
    workflow.add_node("reporting", reporting_node)

    workflow.set_entry_point("context_injection")
    
    workflow.add_edge("context_injection", "position_management")

    workflow.add_conditional_edges(
        "context_injection",
        after_opportunity_screening,
        {
            "analyze_symbol": "analyze_symbol",
            "analysis_barrier": "barrier",
        }
    )

    workflow.add_edge("analyze_symbol", "join_node")
    workflow.add_edge("barrier", "join_node")
    workflow.add_edge("position_management", "join_node")

    workflow.add_edge("join_node", "reporting")
    workflow.add_edge("reporting", END)

    return workflow
