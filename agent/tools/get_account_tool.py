"""查询账户工具"""
from langchain.tools import tool
from typing import Dict, Any
from agent.engine import get_engine
from monitor_module.utils.logger import get_logger
logger = get_logger('agent.tool.get_account')


@tool("get_account", description="查询账户资金摘要（balance/equity/realized/unrealized/reserved_margin/positions_count）", parse_docstring=True)
def get_account_tool() -> Dict[str, Any]:
    """查询账户资金摘要。
    
    获取全仓账户关键指标，支持权益评估与风险控制。在做开仓、加仓或设定唤醒时间前，
    建议先查询账户以合理分配保证金与风险。
    
    Returns:
        成功时返回账户摘要字典（balance/equity/realized_pnl/unrealized_pnl/
        reserved_margin_sum/positions_count），失败时返回包含 "error" 键的字典。
    """
    try:
        eng = get_engine()
        if eng is None:
            return {"error": "TOOL_RUNTIME_ERROR: 交易引擎未初始化"}
        res = eng.get_account_summary()
        logger.info(f"get_account: balance={res.get('balance')}, equity={res.get('equity')}, realized={res.get('realized_pnl')}, unrealized={res.get('unrealized_pnl')}, reserved_margin={res.get('reserved_margin_sum')}, positions={res.get('positions_count')} ")
        return res
    except Exception as e:
        return {"error": f"TOOL_RUNTIME_ERROR: 查询账户失败 - {str(e)}"}