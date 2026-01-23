"""更新止盈/止损工具"""
from langchain.tools import tool
from typing import Optional, Dict, Any
from agent.engine import get_engine
from monitor_module.utils.logger import get_logger
logger = get_logger('agent.tool.update_tp_sl')


@tool("update_tp_sl", description="更新持仓的TP/SL（仅支持绝对价格）", parse_docstring=True)
def update_tp_sl_tool(symbol: str,
                      tp_price: float, sl_price: float) -> Dict[str, Any]:
    """更新持仓的止盈/止损设置。
    
    在持仓维持期间，动态调整TP/SL以适应波动与风险控制。止盈止损必须使用绝对价格，
    不支持百分比。止盈止损为必填参数，每次更新必须同时设置两个值。
    建议：
      - 浮盈≥1R 将 SL 上提/下移至入场价附近（BE）
      - 浮盈≥2R 启用追踪止盈，参考结构位/ATR/布林带，避免情绪化提早离场
    
    Args:
        symbol: 交易对，如 "BTCUSDT"。
        tp_price: 止盈价格，必须为正数的绝对价格。
        sl_price: 止损价格，必须为正数的绝对价格。
    
    Returns:
        成功时返回更新后的持仓结构化字典，失败时返回包含 "error" 键的字典。
    """
    def _error(msg: str) -> Dict[str, str]:
        return {"error": f"TOOL_INPUT_ERROR: {msg}. 请修正参数后重试。"}
    logger = get_logger('agent.tool.update_tp_sl')

    try:
        eng = get_engine()
        if eng is None:
            logger.error("update_tp_sl_tool: 引擎未初始化")
            return _error("交易引擎未初始化")
        
        # 绝对价格校验
        if not isinstance(tp_price, (int, float)) or tp_price <= 0:
            logger.error(f"update_tp_sl_tool: tp_price非法 {tp_price}")
            return _error("tp_price必须为正数价格")
        if not isinstance(sl_price, (int, float)) or sl_price <= 0:
            logger.error(f"update_tp_sl_tool: sl_price非法 {sl_price}")
            return _error("sl_price必须为正数价格")
        
        # 获取持仓信息以校验 TP/SL 价格关系
        positions = eng.get_positions_summary()
        pos = next((p for p in positions if p.get('symbol') == symbol), None)
        
        if pos:
            side = pos.get('side')
            entry_price = pos.get('entry_price')
            current_tp = pos.get('tp_price')
            current_sl = pos.get('sl_price')
            
            # 检查是否有实际变化
            if current_tp == tp_price and current_sl == sl_price:
                logger.warning(f"update_tp_sl_tool: TP/SL无变化 symbol={symbol}, tp={tp_price}, sl={sl_price}")
                return _error(f"当前仓位的止盈止损价格与您要设置的值完全相同（TP={tp_price}, SL={sl_price}），无需更新。如果需要调整风控策略，请设置不同的价格。")
            
            # 合理性验证：防止小数点错误（如 0.43 误写成 43.0）
            # 对于加密货币，TP/SL 距离入场价超过 50 倍通常是异常的
            max_reasonable_multiplier = 50
            min_reasonable_multiplier = 1.0 / max_reasonable_multiplier
            
            if side == 'long':
                # 做多仓位：SL 应该在入场价下方，不应该远高于入场价
                if sl_price > entry_price * max_reasonable_multiplier:
                    logger.error(f"update_tp_sl_tool: LONG仓位SL异常 sl_price={sl_price} 远高于 entry_price={entry_price}")
                    return _error(f"做多仓位的止损价格 {sl_price} 异常：远高于入场价 {entry_price:.6f}（超过{max_reasonable_multiplier}倍）。这可能是小数点错误，例如将 0.{str(sl_price).replace('.', '')} 误写成了 {sl_price}。请检查并修正。")
                # 做多仓位：TP 应该在入场价上方，不应该远低于入场价
                if tp_price < entry_price * min_reasonable_multiplier:
                    logger.error(f"update_tp_sl_tool: LONG仓位TP异常 tp_price={tp_price} 远低于 entry_price={entry_price}")
                    return _error(f"做多仓位的止盈价格 {tp_price} 异常：远低于入场价 {entry_price:.6f}（低于1/{max_reasonable_multiplier}）。这可能是小数点错误。请检查并修正。")
            elif side == 'short':
                # 做空仓位：SL 应该在入场价上方，不应该远低于入场价
                if sl_price < entry_price * min_reasonable_multiplier:
                    logger.error(f"update_tp_sl_tool: SHORT仓位SL异常 sl_price={sl_price} 远低于 entry_price={entry_price}")
                    return _error(f"做空仓位的止损价格 {sl_price} 异常：远低于入场价 {entry_price:.6f}（低于1/{max_reasonable_multiplier}）。这可能是小数点错误。请检查并修正。")
                # 做空仓位：TP 应该在入场价下方，不应该远高于入场价
                if tp_price > entry_price * max_reasonable_multiplier:
                    logger.error(f"update_tp_sl_tool: SHORT仓位TP异常 tp_price={tp_price} 远高于 entry_price={entry_price}")
                    return _error(f"做空仓位的止盈价格 {tp_price} 异常：远高于入场价 {entry_price:.6f}（超过{max_reasonable_multiplier}倍）。这可能是小数点错误。请检查并修正。")
            
            # 关键校验：TP/SL 价格关系必须符合仓位方向
            # 这个规则在任何情况下都成立，包括追踪止盈
            if side == 'long':
                # 做多：止盈价格必须大于止损价格（止盈在上，止损在下）
                if tp_price <= sl_price:
                    logger.error(f"update_tp_sl_tool: LONG仓位TP/SL关系错误 tp_price={tp_price} <= sl_price={sl_price}")
                    return _error(f"做多仓位的止盈价格必须高于止损价格。当前 tp_price={tp_price} <= sl_price={sl_price}。请检查是否把止盈止损价格传反了。")
            elif side == 'short':
                # 做空：止损价格必须大于止盈价格（止损在上，止盈在下）
                if sl_price <= tp_price:
                    logger.error(f"update_tp_sl_tool: SHORT仓位TP/SL关系错误 sl_price={sl_price} <= tp_price={tp_price}")
                    return _error(f"做空仓位的止损价格必须高于止盈价格。当前 sl_price={sl_price} <= tp_price={tp_price}。请检查是否把止盈止损价格传反了。")
            
            logger.info(f"update_tp_sl_tool: TP/SL价格关系校验通过 symbol={symbol}, side={side}, entry={entry_price}, tp={tp_price}, sl={sl_price}")
        
        logger.info(f"update_tp_sl_tool: symbol={symbol}, tp_price={tp_price}, sl_price={sl_price}")
        res = eng.update_tp_sl(symbol, tp_price, sl_price)
        if isinstance(res, dict) and 'error' in res:
            logger.error(f"update_tp_sl_tool: 失败 -> {res['error']}")
        else:
            logger.info(f"update_tp_sl_tool: 成功 -> id={res.get('id')}, symbol={res.get('symbol')}, tp={res.get('tp_price')}, sl={res.get('sl_price')}\n")
        return res
    except Exception as e:
        logger.error(f"update_tp_sl_tool: 异常 -> {e}")
        return {"error": f"TOOL_RUNTIME_ERROR: 更新TP/SL失败 - {str(e)}"}