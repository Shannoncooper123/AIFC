"""构建 LangGraph 工作流"""
from typing import Dict, Any, Union

from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnableConfig

from modules.agent.state import AgentState, SymbolAnalysisState
from modules.agent.nodes.context_injection_node import context_injection_node
from modules.agent.nodes.single_symbol_analysis_node import single_symbol_analysis_node
from modules.agent.nodes.opening_decision_node import opening_decision_node
from modules.agent.conditional_edges import after_opportunity_screening
from modules.agent.utils.trace_utils import traced_node


def _barrier_node(state: Union[AgentState, SymbolAnalysisState], *, config: RunnableConfig) -> Dict[str, Any]:
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


@traced_node("analyze_symbol")
def _symbol_analysis_node(state: SymbolAnalysisState, *, config: RunnableConfig) -> Dict[str, Any]:
    """
    子图包装节点：执行单币种分析 + 开仓决策。
    装饰器自动创建节点级 trace 以实现层级化 trace 结构。
    """
    result = _compiled_subgraph.invoke(state, config)
    
    return {
        "analysis_results": result.get("analysis_results", {}),
        "opening_decision_results": result.get("opening_decision_results", {}),
    }


def create_workflow(config: Dict[str, Any]) -> StateGraph:
    """
    创建并配置 LangGraph 工作流。
    
    架构：
    - context_injection: 注入上下文，筛选机会
    - analyze_symbol: 子图（analysis + decision），通过 Send 分发
    - analysis_barrier: 无机会时的占位节点
    - join_node: 汇聚节点
    """
    workflow = StateGraph(AgentState)

    workflow.add_node("context_injection", context_injection_node)
    workflow.add_node("analyze_symbol", _symbol_analysis_node)
    workflow.add_node("analysis_barrier", _barrier_node)
    workflow.add_node("join_node", _barrier_node)

    workflow.set_entry_point("context_injection")

    workflow.add_conditional_edges(
        "context_injection",
        after_opportunity_screening,
        {
            "analyze_symbol": "analyze_symbol",
            "analysis_barrier": "analysis_barrier",
        }
    )

    workflow.add_edge("analyze_symbol", "join_node")
    workflow.add_edge("analysis_barrier", "join_node")

    workflow.add_edge("join_node", END)

    return workflow
