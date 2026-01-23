"""条件边：机会筛选后"""
from modules.agent.state import AgentState
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
        # 为每个机会创建一个 Send 对象，分发到 analyze_symbol 节点并发执行
        sends = []
        for s in state.opportunities:
            # 获取该币种的持仓信息（如果存在）
            specific_position = state.symbol_positions_map.get(s)
            filtered_positions = [specific_position] if specific_position else []
            
            subgraph_state = AgentState(
                current_symbol=s,
                symbol_contexts=state.symbol_contexts,
                market_context=state.market_context,
                account_summary=state.account_summary,
                positions_summary=filtered_positions,  # 只传该币种的持仓
                position_history=state.position_history,
                long_short_ratio=state.long_short_ratio,  # 传递整体多空比
                symbol_positions_map=state.symbol_positions_map,  # 传递完整映射以备需要
                previous_symbol_focus_map=state.previous_symbol_focus_map,
                position_next_focus=state.position_next_focus,
            )
            sends.append(Send("analyze_symbol", subgraph_state))
        return sends
    else:
        print("未发现机会，进入占位节点以对齐 Super Step。")
        return "analysis_barrier"