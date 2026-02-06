"""工作流节点：市场上下文注入"""
from typing import Any, Dict, List

from langchain_core.runnables import RunnableConfig

from modules.agent.utils.trace_utils import traced_node
from modules.agent.state import AgentState
from modules.monitor.utils.logger import get_logger

logger = get_logger('agent.nodes.context_injection')

HARDCODED_ACCOUNT_SUMMARY: Dict[str, Any] = {
    'balance': 10000.0,
    'equity': 10000.0,
    'margin_usage_rate': 0.0,
    'positions_count': 0,
    'realized_pnl': 0.0,
    'reserved_margin_sum': 0.0,
}


@traced_node("context_injection")
def context_injection_node(state: AgentState, *, config: RunnableConfig) -> Dict[str, Any]:
    """
    注入账户状态和待分析币种列表。
    
    简化版本：
    - 使用硬编码的账户信息（不再获取真实账户状态）
    - 提取告警中的币种列表
    - 不再注入持仓、历史等冗余信息
    """
    configurable: Dict[str, Any] = config.get("configurable", {}) if config else {}
    latest_alert = configurable.get("latest_alert")
    if not latest_alert:
        return {"error": "context_injection_node: 未能从配置中获取 latest_alert。"}

    run_id = configurable.get("run_id")

    account_summary = HARDCODED_ACCOUNT_SUMMARY.copy()

    entries = latest_alert.get('entries', [])

    # 提取币种列表
    all_symbols: List[str] = []
    symbol_contexts: Dict[str, str] = {}
    seen = set()
    
    for entry in entries:
        sym = entry.get('symbol')
        if sym and sym.upper() not in seen:
            all_symbols.append(sym.upper())
            symbol_contexts[sym.upper()] = ""
            seen.add(sym.upper())

    result = {
        "market_context": "",
        "symbol_contexts": symbol_contexts,
        "account_summary": account_summary,
        "opportunities": all_symbols,
    }
    if run_id:
        result["run_id"] = run_id
    
    return result
