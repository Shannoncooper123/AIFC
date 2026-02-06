"""创建限价单工具"""
from langchain.tools import tool
from typing import Optional, Dict, Any
from modules.agent.engine import get_engine
from modules.monitor.utils.logger import get_logger

logger = get_logger('agent.tool.create_limit_order')


def _format_limit_order_result(res: Dict[str, Any]) -> str:
    """格式化限价单结果"""
    symbol = res.get('symbol', 'UNKNOWN')
    side = res.get('side', 'unknown')
    limit_price = res.get('limit_price', 0)
    tp_price = res.get('tp_price')
    sl_price = res.get('sl_price')
    order_id = res.get('id', 'unknown')
    margin_usdt = res.get('margin_usdt', 0)
    leverage = res.get('leverage', 10)
    
    side_cn = '做多' if side == 'long' else '做空'
    notional = margin_usdt * leverage
    
    tp_str = f"${tp_price:.6g}" if tp_price else "未设置"
    sl_str = f"${sl_price:.6g}" if sl_price else "未设置"
    
    return f"""✅ 限价单创建成功

【{symbol}】{side_cn} (Limit) | {leverage}x杠杆
  订单ID: {order_id}
  挂单价格: ${limit_price:.6g}
  保证金: ${margin_usdt:.2f} | 名义价值: ${notional:.2f}
  止盈: {tp_str}
  止损: {sl_str}
  状态: Pending"""

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

        from modules.agent.engine import get_reverse_engine
        reverse_engine = get_reverse_engine()
        is_reverse_mode = reverse_engine and reverse_engine.is_enabled()
        
        if is_reverse_mode:
            logger.info(f"[反向模式] 创建反向条件单: {symbol} {side_lower} @ {limit_price}")
            
            order = reverse_engine.on_agent_limit_order(
                symbol=symbol,
                side=side_lower,
                limit_price=limit_price,
                tp_price=tp_price,
                sl_price=sl_price,
            )
            
            if not order:
                logger.error(f"[反向模式] 反向条件单创建失败: {symbol}")
                return {"error": "TOOL_RUNTIME_ERROR: 反向条件单创建失败"}
            
            logger.info(f"[反向模式] 反向条件单创建成功: {symbol} algoId={order.algo_id}")
            leverage = reverse_engine.config_manager.fixed_leverage
            reverse_side_cn = '做空' if side_lower == 'long' else '做多'
            
            return f"""✅ 反向条件单创建成功

【{symbol}】反向{reverse_side_cn} (Conditional) | {leverage}x杠杆
  条件单ID: {order.algo_id}
  触发价格: ${limit_price:.6g}
  止盈: ${order.tp_price:.6g} (Agent止损位)
  止损: ${order.sl_price:.6g} (Agent止盈位)
  状态: 等待触发"""
        
        logger.info(f"create_limit_order: {symbol} {side_lower} @ {limit_price}")
        
        res = eng.create_limit_order(
            symbol=symbol,
            side=side_lower,
            limit_price=limit_price,
            tp_price=tp_price,
            sl_price=sl_price
        )
        
        if isinstance(res, dict) and 'error' in res:
            logger.error(f"create_limit_order failed: {res['error']}")
            return res
        
        return _format_limit_order_result(res)
        
    except Exception as e:
        logger.error(f"create_limit_order_tool exception: {e}", exc_info=True)
        return {"error": f"TOOL_RUNTIME_ERROR: {str(e)}"}
