"""工作流节点：市场上下文注入"""
from typing import Any, Dict, List

from langchain_core.runnables import RunnableConfig

from modules.agent.engine import get_engine
from modules.agent.utils.trace_utils import traced_node
from modules.agent.state import AgentState
from modules.monitor.utils.logger import get_logger

logger = get_logger('agent.nodes.context_injection')


@traced_node("context_injection")
def context_injection_node(state: AgentState, *, config: RunnableConfig) -> Dict[str, Any]:
    """
    注入账户状态和待分析币种列表。
    
    简化版本：
    - 只注入账户信息
    - 提取告警中的币种列表
    - 不再注入持仓、历史等冗余信息
    """
    configurable: Dict[str, Any] = config.get("configurable", {}) if config else {}
    latest_alert = configurable.get("latest_alert")
    if not latest_alert:
        return {"error": "context_injection_node: 未能从配置中获取 latest_alert。"}

    run_id = configurable.get("run_id")

    eng = get_engine()
    account_summary = eng.get_account_summary() if eng else {}

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
