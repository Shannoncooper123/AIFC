"""创建限价单工具"""
from langchain.tools import tool
from typing import Optional, Dict, Any, List
from modules.agent.engine import get_engine
from modules.constants import DEFAULT_LEVERAGE
from modules.monitor.utils.logger import get_logger
from modules.monitor.alerts.notifier import EmailNotifier
from modules.config.settings import get_config

logger = get_logger('agent.tool.create_limit_order')

def _format_limit_order_result(res: Dict[str, Any], margin_usdt: float, leverage: int) -> str:
    """格式化限价单结果
    
    Args:
        res: 引擎返回的订单字典
        margin_usdt: 保证金
        leverage: 杠杆
    
    Returns:
        格式化的字符串
    """
    symbol = res.get('symbol', 'UNKNOWN')
    side = res.get('side', 'unknown')
    limit_price = res.get('limit_price', 0)
    tp_price = res.get('tp_price')
    sl_price = res.get('sl_price')
    order_id = res.get('id', 'unknown')
    
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

def _send_limit_order_email(symbol: str, side: str, margin_usdt: float, leverage: int,
                           limit_price: float, tp_price: Optional[float], sl_price: Optional[float]):
    """发送限价单通知邮件"""
    try:
        from datetime import datetime, timezone
        
        config = get_config()
        
        if not config['env'].get('email_enabled', False):
            return
        
        notifier = EmailNotifier(config)
        target_email = config.get('agent', {}).get('report_email') or config['env']['alert_email']
        
        if not target_email:
            return
        
        notifier.alert_email = target_email
        side_abbr = "LONG" if side == "long" else "SHORT"
        
        # 构建HTML邮件
        subject = f"Limit Order Created: {symbol} {side_abbr}"
        
        tp_display = f"{tp_price:.8f}" if tp_price else "N/A"
        sl_display = f"{sl_price:.8f}" if sl_price else "N/A"
        
        body_html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background-color: #3498db; color: white; padding: 15px; border-radius: 5px; }}
                .info-table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                .info-table th {{ background-color: #34495e; color: white; padding: 10px; text-align: left; }}
                .info-table td {{ padding: 10px; border-bottom: 1px solid #ddd; }}
                .highlight {{ font-weight: bold; color: #3498db; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>限价单已创建</h2>
                <p>SYMBOL：<strong>{symbol}</strong> | SIDE：<strong>{side_abbr}</strong></p>
                <p>TIME：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC</p>
            </div>
            
            <table class="info-table">
                <tr><th>ITEM</th><th>VALUE</th></tr>
                <tr><td>SYMBOL</td><td class="highlight">{symbol}</td></tr>
                <tr><td>SIDE</td><td class="highlight">{side_abbr}</td></tr>
                <tr><td>LIMIT PRICE</td><td>{limit_price:.8f}</td></tr>
                <tr><td>保证金</td><td>{margin_usdt:.2f} USDT</td></tr>
                <tr><td>杠杆</td><td>{leverage}x</td></tr>
                <tr><td>止盈价</td><td>{tp_display}</td></tr>
                <tr><td>止损价</td><td>{sl_display}</td></tr>
            </table>
        </body>
        </html>
        """
        
        notifier._send_html_email(subject, body_html)
        
    except Exception as e:
        logger.error(f"发送限价单邮件异常: {e}")

@tool("create_limit_order", description="创建限价单（挂单）。当当前价格不理想但想在特定价格入场时使用。注意：必须同时设置止盈和止损。", parse_docstring=True)
def create_limit_order_tool(
    symbol: str,
    side: str,
    limit_price: float,
    margin_usdt: float,
    tp_price: float,
    sl_price: float,
) -> str | Dict[str, Any]:
    """创建限价单。
    
    Args:
        symbol: 交易对 (e.g. "BTCUSDT")
        side: 方向 "BUY" (做多) 或 "SELL" (做空)
        limit_price: 挂单价格（必须大于0）
        margin_usdt: 保证金金额（USDT，必须大于0），但是不能超过当前可用保证金的5%！
        tp_price: 止盈价格（必须大于0，且符合方向逻辑）
        sl_price: 止损价格（必须大于0，且符合方向逻辑）
    """
    from modules.agent.tools.tool_utils import make_input_error
    
    try:
        # 参数校验
        if not symbol or not side or not limit_price or not margin_usdt:
            return make_input_error("symbol, side, limit_price, margin_usdt 均为必填参数")
            
        if limit_price <= 0:
            return make_input_error("limit_price 必须大于 0")
            
        if margin_usdt <= 0:
            return make_input_error("margin_usdt 必须大于 0")

        if not tp_price or tp_price <= 0:
            return make_input_error("tp_price (止盈价) 为必填项且必须大于 0")

        if not sl_price or sl_price <= 0:
            return make_input_error("sl_price (止损价) 为必填项且必须大于 0")
            
        # 转换 side
        side_lower = "long" if side.upper() == "BUY" else "short" if side.upper() == "SELL" else None
        if not side_lower:
             return make_input_error("side 必须为 'BUY' 或 'SELL'")

        # 校验 TP/SL 逻辑
        if side_lower == "long":
            if tp_price <= limit_price:
                return make_input_error(f"做多限价单错误: 止盈价({tp_price}) 必须高于 挂单价({limit_price})")
            if sl_price >= limit_price:
                return make_input_error(f"做多限价单错误: 止损价({sl_price}) 必须低于 挂单价({limit_price})")
        else: # short
            if tp_price >= limit_price:
                return make_input_error(f"做空限价单错误: 止盈价({tp_price}) 必须低于 挂单价({limit_price})")
            if sl_price <= limit_price:
                return make_input_error(f"做空限价单错误: 止损价({sl_price}) 必须高于 挂单价({limit_price})")
            
        config = get_config()
        trading_mode = config.get('trading', {}).get('mode', 'simulator')
        if trading_mode == 'live':
            leverage = int(config.get('trading', {}).get('max_leverage', DEFAULT_LEVERAGE))
        else:
            leverage = int(config.get('agent', {}).get('simulator', {}).get('max_leverage', DEFAULT_LEVERAGE))
        
        eng = get_engine()
        if eng is None:
            logger.error("create_limit_order_tool: 引擎未初始化")
            return {"error": "TOOL_RUNTIME_ERROR: 交易引擎未初始化"}

        try:
            account_summary = eng.get_account_summary()
            account_balance = float(account_summary.get('balance', 0))
            reserved_margin = float(account_summary.get('reserved_margin_sum', 0))
            available_balance = account_balance - reserved_margin
            max_margin_for_new_position = available_balance * 0.05
            if margin_usdt > max_margin_for_new_position:
                logger.error(
                    f"create_limit_order_tool: 保证金超限！请求={margin_usdt:.2f}U，上限={max_margin_for_new_position:.2f}U (可用={available_balance:.2f}U × 5%)"
                )
                return make_input_error(
                    f"保证金超限：当前可用保证金={available_balance:.2f}U，单仓上限={max_margin_for_new_position:.2f}U（5%）"
                )
        except Exception as e:
            logger.warning(f"保证金上限校验时出错（继续执行）: {e}")

        # 调用引擎创建限价单
        logger.info(f"create_limit_order: {symbol} {side_lower} @ {limit_price}, margin={margin_usdt}")
        
        res = eng.create_limit_order(
            symbol=symbol,
            side=side_lower,
            limit_price=limit_price,
            margin_usdt=margin_usdt,
            leverage=leverage,
            tp_price=tp_price,
            sl_price=sl_price
        )
        
        if isinstance(res, dict) and 'error' in res:
            logger.error(f"create_limit_order failed: {res['error']}")
            return res
            
        # 发送邮件
        _send_limit_order_email(symbol, side_lower, margin_usdt, leverage, limit_price, tp_price, sl_price)
        
        # 触发反向交易引擎（如果启用）
        try:
            from modules.agent.engine import get_reverse_engine
            reverse_engine = get_reverse_engine()
            if reverse_engine and reverse_engine.is_enabled():
                order_id = res.get('id') if isinstance(res, dict) else None
                reverse_engine.on_agent_limit_order(
                    symbol=symbol,
                    side=side_lower,
                    limit_price=limit_price,
                    tp_price=tp_price,
                    sl_price=sl_price,
                    agent_order_id=order_id
                )
                logger.info(f"[反向] 已触发反向交易引擎: {symbol} {side_lower}")
        except Exception as e:
            logger.warning(f"反向交易引擎处理失败（不影响主订单）: {e}")
        
        return _format_limit_order_result(res, margin_usdt, leverage)
        
    except Exception as e:
        logger.error(f"create_limit_order_tool exception: {e}", exc_info=True)
        return {"error": f"TOOL_RUNTIME_ERROR: {str(e)}"}
