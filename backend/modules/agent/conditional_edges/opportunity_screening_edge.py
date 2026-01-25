"""条件边：机会筛选后"""
from modules.agent.state import AgentState, SymbolAnalysisState
from langgraph.types import Send


def after_opportunity_screening(state: AgentState):
    """
    机会筛选后，决定是并发分析还是进入占位节点。
    
    返回值：
    - 当有机会时：返回 Send 对象的列表（用于 map-reduce 模式）
    - 当无机会时：返回字符串 "analysis_barrier"
    """
    if state.opportunities:
        print(f"发现 {len(state.opportunities)} 个机会，分发进行分析: {state.opportunities}")
        sends = []
        for s in state.opportunities:
            specific_position = state.symbol_positions_map.get(s)
            filtered_positions = [specific_position] if specific_position else []
            
            subgraph_state = SymbolAnalysisState(
                current_symbol=s,
                symbol_contexts=state.symbol_contexts,
                market_context=state.market_context,
                account_summary=state.account_summary,
                positions_summary=filtered_positions,
                position_history=state.position_history,
            )
            sends.append(Send("analyze_symbol", subgraph_state))
        return sends
    else:
        print("未发现机会，进入占位节点以对齐 Super Step。")
        return "analysis_barrier"
