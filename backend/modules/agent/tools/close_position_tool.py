"""平仓工具（全平）"""
from langchain.tools import tool
from typing import Optional, Dict, Any
from modules.agent.tools.tool_utils import make_input_error, make_runtime_error, require_engine
from modules.agent.utils.workflow_trace_storage import get_current_run_id
from modules.monitor.utils.logger import get_logger

logger = get_logger('agent.tool.close_position')


@tool("close_position", description="平仓（全部平仓）", parse_docstring=True)
def close_position_tool(
    symbol: str,
    trend_reversed: bool,
    structure_broken: bool,
    volume_confirmed: bool,
    timing_reasonable: bool
) -> Dict[str, Any]:
    """平仓。

    根据当前最新价进行持仓的手动全平，并结算手续费与已实现盈亏。
    重要：这是手动平仓，仅在确认持仓逻辑失效时使用，不要恐慌性止损。
    
    Args:
        symbol: 交易对，如 "BTCUSDT"。
        
        trend_reversed: 趋势反转确认（基于方向中性因子：趋势对齐/价格有利/MACD 方向在 1h/4h 反向一致）。
        structure_broken: 关键结构破坏（重要支撑/阻力位被有效突破，收盘价连续≥2-3 根确认）。
        volume_confirmed: 反向成交量确认（1h 至少 1 根且 15m 连续 ≥2 根放量，>1.5×均量）。
        timing_reasonable: 平仓时机合理（非情绪性止损，记录结构/量能/因子变化的依据）。
    
    Returns:
        成功时返回持仓结构化字典（含 close_price/realized_pnl/fees_close 等更新字段），
        失败时返回包含 "error" 键的字典。
        
    注意：
        这4个检查点参数仅用于决策验证和置信度计算。
        系统会进行加权评分后决定是否放行。
    """
    try:
        eng, error = require_engine()
        if error:
            logger.error(f"close_position_tool: {error}")
            return make_input_error(error)
        logger.info(
            f"close_position_tool: symbol={symbol}, "
            f"checkpoints=[trend_reversed:{trend_reversed}, structure_broken:{structure_broken}, "
            f"volume:{volume_confirmed}, timing:{timing_reasonable}]"
        )
        run_id = get_current_run_id()
        res = eng.close_position(symbol=symbol, run_id=run_id)
        if isinstance(res, dict) and 'error' in res:
            logger.error(f"close_position_tool: 失败 -> {res['error']}")
        else:
            logger.info(f"close_position_tool: 成功 -> id={res.get('id')}, symbol={res.get('symbol')}, status={res.get('status')}, close_price={res.get('close_price')}\n")
        return res
    except Exception as e:
        logger.error(f"close_position_tool: 异常 -> {e}", exc_info=True)
        return make_runtime_error(f"平仓失败 - {str(e)}")