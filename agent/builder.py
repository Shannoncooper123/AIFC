"""构建 LangGraph 工作流"""
from typing import Dict, Any

from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnableConfig

from agent.state import AgentState
from agent.nodes.context_injection_node import context_injection_node
from agent.nodes.reporting_node import reporting_node
from agent.nodes.single_symbol_analysis_node import single_symbol_analysis_node
from agent.nodes.position_management_node import position_management_node
from agent.conditional_edges import after_opportunity_screening


def create_workflow(config: Dict[str, Any]) -> StateGraph:
    """
    创建并配置 LangGraph 工作流。
    """
    workflow = StateGraph(AgentState)

    # 1. 添加节点
    workflow.add_node("context_injection", context_injection_node)
    workflow.add_node("analyze_symbol", single_symbol_analysis_node) # worker for concurrent analysis
    workflow.add_node("reporting", reporting_node)
    workflow.add_node("position_management", position_management_node)

    # 2. 添加占位节点（用于不需要执行实际操作时的对齐）
    def _barrier_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
        # 不改变状态，仅作为同步点
        return {}
    
    workflow.add_node("analysis_barrier", _barrier_node)
    workflow.add_node("join_node", _barrier_node)

    # 3. 设置工作流的入口
    workflow.set_entry_point("context_injection")
    
    # 4. 定义并行分支的条件路由
    workflow.add_edge("context_injection","position_management")

    # 分支 2: 机会分析（条件路由到 analyze_symbol 或 analysis_barrier）
    workflow.add_conditional_edges(
        "context_injection",
        after_opportunity_screening,
        {
            "analyze_symbol": "analyze_symbol",
            "analysis_barrier": "analysis_barrier",
        }
    )

    # 5. 所有节点汇聚到 join_node
    workflow.add_edge("position_management", "join_node")
    workflow.add_edge("analyze_symbol", "join_node")
    workflow.add_edge("analysis_barrier", "join_node")

    # 6. join_node 汇聚后进入报告
    workflow.add_edge("join_node", "reporting")
    workflow.add_edge("reporting", END)

    return workflow