"""创建限价单工具

支持正常模式和反向模式。反向模式下会自动进行参数转换：
- 方向反转：Agent BUY -> 我们 SELL
- TP/SL 互换：Agent 的 TP 变成我们的 SL，Agent 的 SL 变成我们的 TP
"""
from langchain.tools import tool
from typing import Optional, Dict, Any
from modules.agent.engine import get_engine, is_reverse_enabled
from modules.monitor.utils.logger import get_logger

logger = get_logger('agent.tool.create_limit_order')


def _format_order_result(res: Dict[str, Any], is_reverse: bool = False) -> str:
    """格式化订单结果"""
    symbol = res.get('symbol', 'UNKNOWN')
    side = res.get('side', 'unknown')
    order_kind = res.get('order_kind', 'LIMIT')
    price = res.get('price') or res.get('trigger_price') or res.get('limit_price', 0)
    tp_price = res.get('tp_price')
    sl_price = res.get('sl_price')
    order_id = res.get('order_id') or res.get('algo_id') or res.get('id', 'unknown')
    margin_usdt = res.get('margin_usdt', 0)
    leverage = res.get('leverage', 10)
    
    if is_reverse:
        agent_side = res.get('agent_side') or ('long' if side == 'sell' else 'short')
        mode_label = f"反向{'做空' if agent_side == 'long' else '做多'}"
    else:
        mode_label = '做多' if side in ('buy', 'long') else '做空'
    
    order_type_cn = '条件单' if order_kind == 'CONDITIONAL' else '限价单'
    fee_type = 'Taker' if order_kind == 'CONDITIONAL' else 'Maker'
    
    notional = margin_usdt * leverage if margin_usdt > 0 else 0
    
    tp_str = f"${tp_price:.6g}" if tp_price else "未设置"
    sl_str = f"${sl_price:.6g}" if sl_price else "未设置"
    
    return f"""✅ {order_type_cn}创建成功

【{symbol}】{mode_label} ({order_type_cn}/{fee_type}) | {leverage}x杠杆
  订单ID: {order_id}
  挂单价格: ${price:.6g}
  保证金: ${margin_usdt:.2f} | 名义价值: ${notional:.2f}
  止盈: {tp_str}
  止损: {sl_str}
  状态: 等待触发"""


@tool("create_limit_order", description="创建限价单（挂单）。当当前价格不理想但想在特定价格入场时使用。注意：必须同时设置止盈和止损。", parse_docstring=True)
def create_limit_order_tool(
    symbol: str,
    side: str,
    limit_price: float,
    tp_price: float,
    sl_price: float,
) -> str | Dict[str, Any]:
    """创建限价单（开仓信号）。
    
    Agent 只需要提供开仓信号，实际金额由引擎配置决定。
    如果启用了反向交易模式，会自动创建反向订单。
    
    Args:
        symbol: 交易对 (e.g. "BTCUSDT")
        side: 方向 "BUY" (做多) 或 "SELL" (做空)
        limit_price: 挂单价格（必须大于0）
        tp_price: 止盈价格（必须大于0，且符合方向逻辑）
        sl_price: 止损价格（必须大于0，且符合方向逻辑）
    """
    from modules.agent.tools.tool_utils import make_input_error
    
    try:
        if not symbol or not side or not limit_price:
            return make_input_error("symbol, side, limit_price 均为必填参数")
            
        if limit_price <= 0:
            return make_input_error("limit_price 必须大于 0")

        if not tp_price or tp_price <= 0:
            return make_input_error("tp_price (止盈价) 为必填项且必须大于 0")

        if not sl_price or sl_price <= 0:
            return make_input_error("sl_price (止损价) 为必填项且必须大于 0")
            
        side_lower = "long" if side.upper() == "BUY" else "short" if side.upper() == "SELL" else None
        if not side_lower:
            return make_input_error("side 必须为 'BUY' 或 'SELL'")

        if side_lower == "long":
            if tp_price <= limit_price:
                return make_input_error(f"做多限价单错误: 止盈价({tp_price}) 必须高于 挂单价({limit_price})")
            if sl_price >= limit_price:
                return make_input_error(f"做多限价单错误: 止损价({sl_price}) 必须低于 挂单价({limit_price})")
        else:
            if tp_price >= limit_price:
                return make_input_error(f"做空限价单错误: 止盈价({tp_price}) 必须低于 挂单价({limit_price})")
            if sl_price <= limit_price:
                return make_input_error(f"做空限价单错误: 止损价({sl_price}) 必须高于 挂单价({limit_price})")
        
        eng = get_engine()
        if eng is None:
            logger.error("create_limit_order_tool: 引擎未初始化")
            return {"error": "TOOL_RUNTIME_ERROR: 交易引擎未初始化"}

        is_reverse_mode = is_reverse_enabled()
        
        final_side = side_lower
        final_tp = tp_price
        final_sl = sl_price
        source = 'live'
        agent_side = None
        
        if is_reverse_mode:
            final_side = 'short' if side_lower == 'long' else 'long'
            final_tp = sl_price
            final_sl = tp_price
            source = 'reverse'
            agent_side = side_lower
            
            logger.info(f"[反向模式] Agent 信号: {symbol} {side_lower} @ {limit_price}")
            logger.info(f"[反向模式] 反向订单: {final_side} TP={final_tp} SL={final_sl}")
        else:
            logger.info(f"create_limit_order: {symbol} {side_lower} @ {limit_price}")
        
        current_price = None
        if hasattr(eng, 'get_simulated_price'):
            current_price = eng.get_simulated_price(symbol)
        elif hasattr(eng, 'price_service'):
            current_price = eng.price_service.get_last_price(symbol)
        
        order_kind = 'LIMIT'
        if current_price and current_price > 0:
            if final_side == 'long':
                if current_price > limit_price:
                    order_kind = 'LIMIT'
                    logger.info(f"[智能下单] 当前价 {current_price:.6f} > 触发价 {limit_price:.6f} → 限价单 (Maker)")
                else:
                    order_kind = 'CONDITIONAL'
                    logger.info(f"[智能下单] 当前价 {current_price:.6f} <= 触发价 {limit_price:.6f} → 条件单 (Taker)")
            else:
                if current_price < limit_price:
                    order_kind = 'LIMIT'
                    logger.info(f"[智能下单] 当前价 {current_price:.6f} < 触发价 {limit_price:.6f} → 限价单 (Maker)")
                else:
                    order_kind = 'CONDITIONAL'
                    logger.info(f"[智能下单] 当前价 {current_price:.6f} >= 触发价 {limit_price:.6f} → 条件单 (Taker)")
        
        res = eng.create_limit_order(
            symbol=symbol,
            side=final_side,
            limit_price=limit_price,
            tp_price=final_tp,
            sl_price=final_sl,
            source=source,
            agent_side=agent_side,
            order_kind=order_kind
        )
        
        if isinstance(res, dict) and 'error' in res:
            logger.error(f"create_limit_order failed: {res['error']}")
            return res
        
        return _format_order_result(res, is_reverse=is_reverse_mode)
        
    except Exception as e:
        logger.error(f"create_limit_order_tool exception: {e}", exc_info=True)
        return {"error": f"TOOL_RUNTIME_ERROR: {str(e)}"}
