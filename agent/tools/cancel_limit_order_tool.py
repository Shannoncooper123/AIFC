"""取消限价单工具"""
from langchain.tools import tool
from typing import Optional, Dict, Any, List
from agent.engine import get_engine
from monitor_module.utils.logger import get_logger

logger = get_logger('agent.tool.cancel_limit_order')


@tool("cancel_limit_order", description="取消指定交易对的所有待成交限价单", parse_docstring=True)
def cancel_limit_order_tool(
    symbol: str,
    structure_changed: bool,
    entry_invalid: bool,
    volume_divergence: bool,
    timing_reasonable: bool
) -> Dict[str, Any]:
    """取消指定交易对的所有待成交限价单。
    
    当市场结构变化、入场点失效或其他条件不再满足时，取消该交易对的所有挂单。
    重要：仅在确认挂单逻辑失效时使用，避免频繁撤单重挂。
    
    Args:
        symbol: 交易对（如 "BTCUSDT"），将取消该交易对的所有待成交限价单
        
        structure_changed: 关键结构变化（关键支撑/阻力位被有效突破或形态改变，收盘价连续≥2-3根确认）
        entry_invalid: 入场点失效（挂单价格附近的结构被破坏，或不再是合理的关键位）
        volume_divergence: 成交量背离（出现明显的量能背离，如放量反向突破）
        timing_reasonable: 撤单时机合理（非情绪性撤单，记录结构/量能变化的依据）
    
    Returns:
        成功时返回包含取消订单数量和详情的字典，
        失败时返回包含 "error" 键的字典。
        
    注意：
        这4个检查点参数仅用于决策验证和置信度计算。
        系统会进行加权评分后决定是否放行。
    """
    def _error(msg: str) -> Dict[str, str]:
        return {"error": f"TOOL_INPUT_ERROR: {msg}. 请修正参数后重试。"}
    
    try:
        eng = get_engine()
        if eng is None:
            logger.error("cancel_limit_order_tool: 引擎未初始化")
            return _error("交易引擎未初始化")
        
        if not symbol:
            logger.error("cancel_limit_order_tool: 缺少symbol参数")
            return _error("symbol 为必填参数")
        
        logger.info(
            f"cancel_limit_order_tool: symbol={symbol}, "
            f"checkpoints=[structure_changed:{structure_changed}, entry_invalid:{entry_invalid}, "
            f"volume_divergence:{volume_divergence}, timing:{timing_reasonable}]"
        )
        
        res = eng.cancel_limit_orders_by_symbol(symbol=symbol)
        
        if isinstance(res, dict) and 'error' in res:
            logger.error(f"cancel_limit_order_tool: 失败 -> {res['error']}")
        else:
            cancelled_count = res.get('cancelled_count', 0)
            logger.info(
                f"cancel_limit_order_tool: 成功 -> "
                f"symbol={symbol}, 已取消 {cancelled_count} 个挂单\n"
            )
        
        return res
    
    except Exception as e:
        logger.error(f"cancel_limit_order_tool: 异常 -> {e}")
        return {"error": f"TOOL_RUNTIME_ERROR: 取消限价单失败 - {str(e)}"}

