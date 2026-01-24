"""开仓/加仓工具"""
from langchain.tools import tool
from typing import Optional, Dict, Any, List
from modules.agent.engine import get_engine
from modules.agent.utils.workflow_trace_storage import get_current_run_id
from modules.constants import DEFAULT_LEVERAGE
from modules.monitor.utils.logger import get_logger
from modules.monitor.alerts.notifier import EmailNotifier
from modules.config.settings import get_config
from modules.monitor.clients.binance_rest import BinanceRestClient
from modules.monitor.data.models import Kline
from modules.monitor.indicators.atr import calculate_atr

logger = get_logger('agent.tool.open_position')





def _send_position_open_email(symbol: str, side: str, margin_usdt: float, leverage: int,
                               entry_price: float, tp_price: float, sl_price: float, notional: float):
    """发送开仓通知邮件
    
    Args:
        symbol: 交易对
        side: 方向（long/short）
        margin_usdt: 保证金（USDT）
        leverage: 杠杆
        entry_price: 入场价格
        tp_price: 止盈价
        sl_price: 止损价
        notional: 名义价值
    """
    try:
        from datetime import datetime, timezone
        
        config = get_config()
        notifier = EmailNotifier(config)
        
        # 获取收件邮箱
        target_email = config.get('agent', {}).get('report_email') or config['env']['alert_email']
        if not target_email:
            logger.warning("未配置报告收件邮箱，跳过开仓邮件发送")
            return
        
        notifier.alert_email = target_email
        
        # 计算止盈止损比例
        side_abbr = "LONG" if side == "long" else "SHORT"
        if side == "long":
            tp_rate = ((tp_price - entry_price) / entry_price) * 100 if entry_price else 0
            sl_rate = ((entry_price - sl_price) / entry_price) * 100 if entry_price else 0
        else:
            tp_rate = ((entry_price - tp_price) / entry_price) * 100 if entry_price else 0
            sl_rate = ((sl_price - entry_price) / entry_price) * 100 if entry_price else 0
        
        # 计算风险回报比
        risk_reward_ratio = tp_rate / sl_rate if sl_rate > 0 else 0
        
        # 构建HTML邮件
        subject = f"{symbol} {side_abbr}"
        
        body_html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background-color: #{'2ecc71' if side == 'long' else '#e74c3c'}; color: white; padding: 15px; border-radius: 5px; }}
                .info-table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                .info-table th {{ background-color: #34495e; color: white; padding: 10px; text-align: left; }}
                .info-table td {{ padding: 10px; border-bottom: 1px solid #ddd; }}
                .info-table tr:nth-child(even) {{ background-color: #f2f2f2; }}
                .highlight {{ font-weight: bold; color: #{'2ecc71' if side == 'long' else '#e74c3c'}; }}
                .footer {{ margin-top: 30px; padding: 15px; background-color: #ecf0f1; border-radius: 5px; font-size: 12px; color: #7f8c8d; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>通知</h2>
                <p>SYMBOL：<strong>{symbol}</strong> | SIDE：<strong>{side_abbr}</strong></p>
                <p>TIME：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC</p>
            </div>
            
            <table class="info-table">
                <tr>
                    <th>ITEM</th>
                    <th>VALUE</th>
                </tr>
                <tr>
                    <td>SYMBOL</td>
                    <td class="highlight">{symbol}</td>
                </tr>
                <tr>
                    <td>SIDE</td>
                    <td class="highlight">{side_abbr}</td>
                </tr>
                <tr>
                    <td>ENTRY_PRICE</td>
                    <td>{entry_price:.8f}</td>
                </tr>
                <tr>
                    <td>保证金</td>
                    <td>{margin_usdt:.2f} USDT</td>
                </tr>
                <tr>
                    <td>杠杆</td>
                    <td>{leverage}x</td>
                </tr>
                <tr>
                    <td>名义价值</td>
                    <td>{notional:.2f} USDT</td>
                </tr>
                <tr>
                    <td>止盈价</td>
                    <td>{tp_price:.8f} <span style="color: green;">(+{tp_rate:.2f}%)</span></td>
                </tr>
                <tr>
                    <td>止损价</td>
                    <td>{sl_price:.8f} <span style="color: red;">(-{sl_rate:.2f}%)</span></td>
                </tr>
                <tr>
                    <td>风险回报比</td>
                    <td>{risk_reward_ratio:.2f}:1</td>
                </tr>
            </table>
            
            <div class="footer">
                <p><strong>提示：</strong></p>
                <ul>
                    <li>此邮件由交易系统自动发送，无需回复</li>
                    <li>请登录交易平台查看实时持仓状态</li>
                    <li>如有疑问，请检查系统日志或联系管理员</li>
                </ul>
            </div>
        </body>
        </html>
        """
        
        # 发送邮件
        success = notifier._send_html_email(subject, body_html)
        if success:
            logger.info(f"✓ 开仓邮件已发送至 {target_email}")
        else:
            logger.warning(f"✗ 开仓邮件发送失败")
        
    except Exception as e:
        logger.error(f"发送开仓邮件异常: {e}", exc_info=True)

@tool("open_position", description="开仓/加仓或标记开仓阶段完成（仅支持市价单；必须先调用4h/1h/3m的K线和指标；order_type 固定为 market）", parse_docstring=True)
def open_position_tool(
    side: str,
    order_type: str,
    symbol: Optional[str] = None,
    margin_usdt: Optional[float] = None,
    tp_price: Optional[float] = None,
    sl_price: Optional[float] = None,
    runtime = None
) -> Dict[str, Any]:
    """开仓/加仓或标记开仓阶段完成。仅支持市价单（order_type 固定为 "market"）。
    
    当 side="NULL" 时：
      - 用于标记"不执行任何开仓"，系统将自动切换到持仓管理阶段
      - 此时其他所有参数可省略
      - 适用场景：分析后决定不开仓，需要明确告知系统进入下一阶段
    
    当 side="BUY"/"SELL" 时：
      - 执行实际开仓或加仓操作
      - 在全仓保证金模式下，根据最新行情以当根K线最新价开仓或在同向持仓上加仓
      - 仅支持保证金金额（USDT），工具会按配置杠杆计算名义价值；止盈止损必须使用绝对价格，不支持百分比
      - 同一交易对仅允许一边仓位；如已有同向持仓则执行加仓并重算均价
      - 使用配置杠杆；开/平均收 taker 0.05% 手续费；不考虑滑点
    
    订单类型（order_type）：仅支持 "market"，立即以当前市场价格成交。
    
    Args:
        side: 仓位方向或阶段标记。"BUY"=做多，"SELL"=做空，"NULL"=标记开仓阶段完成
        order_type: 订单类型，必须为 "market"
        symbol: 交易对（side 不为 NULL 时必填）
        margin_usdt: 保证金金额（side 不为 NULL 时必填）
        tp_price: 止盈价格（side 不为 NULL 时必填）
        sl_price: 止损价格（side 不为 NULL 时必填）
    
    Returns:
        side="BUY"/"SELL" 时返回持仓结构化字典或错误字典。
        
    注意：
        - 开仓金额不建议超过可用保证金的5%（参考值）
        - 建议先调用 get_kline_image 分析 4h/1h/15m/3m 多周期 K 线图像，确保信息充分
    """
    from modules.agent.tools.tool_utils import make_input_error, make_runtime_error

    try:
        # 处理 NULL 选项（标记开仓阶段完成，不实际开仓）
        if side == "NULL":
            logger.info("open_position_tool: 收到 NULL 信号，标记开仓决策阶段已完成")
            return {
                "status": "opening_stage_completed",
                "message": "开仓决策阶段已完成，未执行实际开仓操作。系统将进入持仓管理阶段。"
            }
        
        config = get_config()
        trading_mode = config.get('trading', {}).get('mode', 'simulator')
        if trading_mode == 'live':
            leverage = int(config.get('trading', {}).get('max_leverage', DEFAULT_LEVERAGE))
        else:
            leverage = int(config.get('agent', {}).get('simulator', {}).get('max_leverage', DEFAULT_LEVERAGE))
        
        if not symbol or margin_usdt is None:
            logger.error("open_position_tool: side 不为 NULL 时缺少必填参数")
            return make_input_error("side 不为 NULL 时，symbol、margin_usdt 为必填参数（margin_usdt 为开仓保证金金额，单位USDT）")
        
        if order_type != "market":
            logger.error(f"open_position_tool: 订单类型无效 {order_type}")
            return make_input_error("order_type 必须为 'market'")
        
        eng = get_engine()
        if eng is None:
            logger.error("open_position_tool: 引擎未初始化")
            return make_input_error("交易引擎未初始化")
        
        if not isinstance(margin_usdt, (int, float)) or margin_usdt <= 0:
            logger.error("open_position_tool: 参数 保证金 非法")
            return make_input_error("margin_usdt（保证金金额）必须为正数")
        
        try:
            account_summary = eng.get_account_summary()
            account_balance = float(account_summary.get('balance', 0))
            reserved_margin = float(account_summary.get('reserved_margin_sum', 0))
            available_balance = account_balance - reserved_margin
            max_margin_for_new_position = available_balance * 0.05
            if margin_usdt > max_margin_for_new_position:
                logger.error(
                    f"open_position_tool: 保证金超限！请求={margin_usdt:.2f}U，上限={max_margin_for_new_position:.2f}U (可用={available_balance:.2f}U × 5%)"
                )
                return make_input_error(
                    f"保证金超限：当前可用保证金={available_balance:.2f}U，单仓上限={max_margin_for_new_position:.2f}U（5%）"
                )
        except Exception as e:
            logger.warning(f"保证金上限校验时出错（继续执行）: {e}")
        
        if tp_price is None or sl_price is None:
            logger.error("open_position_tool: 缺少止盈止损价格")
            return make_input_error("side 不为 NULL 时，tp_price 和 sl_price 为必填参数")
        if not isinstance(tp_price, (int, float)) or tp_price <= 0:
            logger.error(f"open_position_tool: tp_price非法 {tp_price}")
            return make_input_error("tp_price必须为正数价格")
        if not isinstance(sl_price, (int, float)) or sl_price <= 0:
            logger.error(f"open_position_tool: sl_price非法 {sl_price}")
            return make_input_error("sl_price必须为正数价格")
        
        # 转换side参数：BUY -> long, SELL -> short
        engine_side = "long" if side == "BUY" else "short"
        
        # 计算名义价值：notional = 保证金 × 杠杆
        notional = float(margin_usdt) * leverage
        
        logger.info(
            f"open_position_tool: 使用保证金输入 => margin={margin_usdt}U, leverage=10x, notional={notional}U"
        )
        
        run_id = get_current_run_id()
        res = eng.open_position(symbol, engine_side, float(notional), int(leverage), tp_price, sl_price, run_id=run_id)
        if isinstance(res, dict) and 'error' in res:
            logger.error(f"open_position_tool: 失败 -> {res['error']}")
        else:
            logger.info(f"open_position_tool: 成功 -> id={res.get('id')}, symbol={res.get('symbol')}, side={res.get('side')}, entry={res.get('entry_price')}\n")
            
            # 仓成功后发送邮件通知
            try:
                _send_position_open_email(symbol, engine_side, margin_usdt, leverage, 
                                         res.get('entry_price'), tp_price, sl_price, notional)
            except Exception as email_error:
                logger.warning(f"open_position_tool: 发送开仓邮件失败 - {email_error}")
        
        return res
    except Exception as e:
        logger.error(f"open_position_tool: 异常 -> {e}", exc_info=True)
        return {"error": f"TOOL_RUNTIME_ERROR: 开仓失败 - {str(e)}"}
