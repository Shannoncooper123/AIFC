"""条件边：持仓管理分发"""
from modules.agent.state import AgentState, PositionManagementState
from modules.backtest.context import is_backtest_mode
from langgraph.types import Send


def after_context_injection_for_positions(state: AgentState):
    """
    根据持仓情况分发持仓管理任务。
    
    回测模式下直接跳过持仓管理，因为回测引擎会独立处理止盈止损。
    
    返回值：
    - 回测模式：直接返回 "position_barrier"
    - 当有持仓时：返回 Send 对象的列表（每个持仓一个 Send）
    - 当无持仓时：返回字符串 "position_barrier"
    """
    if is_backtest_mode():
        print("回测模式：跳过持仓管理，直接进入占位节点。")
        return "position_barrier"
    
    positions = state.positions_summary
    
    if not positions:
        print("无持仓需要管理，进入占位节点。")
        return "position_barrier"
    
    print(f"发现 {len(positions)} 个持仓，分发进行管理: {[p.get('symbol') for p in positions]}")
    
    sends = []
    for pos in positions:
        symbol = pos.get('symbol', 'UNKNOWN')
        
        subgraph_state = PositionManagementState(
            current_symbol=symbol,
            position_info=pos,
            market_context=state.market_context,
            position_history=state.position_history,
            position_next_focus=state.position_next_focus,
        )
        sends.append(Send("manage_position", subgraph_state))
    
    return sends
