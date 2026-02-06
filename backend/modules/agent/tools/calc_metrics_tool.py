from typing import Any, Dict, Optional
from langchain.tools import tool
from modules.monitor.utils.logger import get_logger
from modules.agent.tools.tool_utils import make_input_error, make_runtime_error
from modules.agent.utils.kline_utils import get_current_price

logger = get_logger('agent.tool.calc_metrics')


from modules.monitor.indicators.atr import calculate_atr_list
from modules.agent.utils.kline_utils import fetch_klines
from modules.config.settings import get_config

def _validate_min_distance(symbol: str, entry_price: float, sl_dist: float, tp_dist: float, feedback: str) -> Optional[Dict]:
    """校验最小止盈止损距离（基于ATR动态计算，降级使用固定百分比）"""
    try:
        # 获取最近的K线数据计算ATR
        # 默认使用15m周期计算ATR，取最近50根
        klines, _ = fetch_klines(symbol, "15m", 50)
        if klines and len(klines) > 20:
            config = get_config()
            atr_period = int(config.get('indicators', {}).get('atr_period', 14))
            atr_list = calculate_atr_list(klines, atr_period)
            current_atr = atr_list[-1] if atr_list else 0
            
            # 最小距离设定为 1.0 * ATR (1倍ATR的波动幅度)
            # 这样能动态适应不同币种的波动率
            min_dist = current_atr * 1.0
            
            if min_dist > 0:
                if sl_dist < min_dist:
                    return make_input_error(
                        f"止损距离过近 ({sl_dist:.4f})，小于 1.0倍ATR ({min_dist:.4f})。请扩大止损距离，同时确保 R:R < 1（即亏损空间 > 盈利空间）以符合亏钱原则。",
                        feedback
                    )
                if tp_dist < min_dist:
                    return make_input_error(
                        f"止盈距离过近 ({tp_dist:.4f})，小于 1.0倍ATR ({min_dist:.4f})。请扩大止盈距离，同时确保 R:R < 1（即亏损空间 > 盈利空间）以符合亏钱原则。",
                        feedback
                    )
                return None
    except Exception as e:
        logger.warning(f"ATR计算失败，降级使用固定百分比校验: {e}")
    
    # 降级方案：保留原有固定百分比校验作为兜底
    min_dist_pct = 0.002 # 0.2% 最小距离
    if sl_dist / entry_price < min_dist_pct:
        return make_input_error(
            f"止损距离过近 ({sl_dist/entry_price:.4%})，容易被噪音触发。建议至少保留 0.2% ({entry_price * min_dist_pct:.4f}) 的空间。",
            feedback
        )
    if tp_dist / entry_price < min_dist_pct:
        return make_input_error(
            f"止盈距离过近 ({tp_dist/entry_price:.4%})，容易被噪音触发。建议至少保留 0.2% ({entry_price * min_dist_pct:.4f}) 的空间。",
            feedback
        )
    return None

@tool(
    "calc_metrics",
    description=(
        "交易指标计算器：计算 R:R（风险回报率）。"
        "支持市价模式（自动获取最新价）和挂单模式（指定 limit_price）。"
    ),
    parse_docstring=True,
)
def calc_metrics_tool(
    symbol: str,
    side: str,
    tp_price: float,
    sl_price: float,
    feedback: str,
    limit_price: Optional[float] = None,
) -> Dict[str, Any]:
    """交易指标计算器：计算R:R风险回报率（支持市价/挂单模式）。

    概要:
        - 市价模式：不传入 limit_price，自动获取 symbol 的最新价格作为入场价
        - 挂单模式：传入 limit_price，以此价格作为入场价计算
        - 自动计算 R:R（风险回报率）

    返回结构化字典，包含：
        - inputs: 原始入参回显（含使用的 entry_price）
        - metrics: entry_price, sl_distance, tp_distance, rr
        - checks: sl_distance_pct（止损距离百分比）
        - feedback: 原路返回的分析进度说明
    错误时返回 {"error": "...", "feedback": ...}

    Args:
        symbol: 交易对，如 "BTCUSDT"。必须为非空字符串。
        side: 仓位方向，仅支持 "BUY" 或 "SELL"（大写）。多头要求 tp > entry > sl，空头要求 sl > entry > tp。
        tp_price: 止盈价格（正数，绝对价格）。
        sl_price: 止损价格（正数，绝对价格）。
        feedback: 当前分析进度总结，详细说明当前的分析阶段与下一步计划。必须为非空字符串。
        limit_price: 可选。挂单价格（正数）。如果提供，将使用此价格作为入场价进行计算；如果不提供，则自动获取当前市价。
    """
    try:
        # 1. 参数校验
        logger.info(
            f"calc_metrics_tool 被调用 - symbol={symbol}, side={side}, tp={tp_price}, sl={sl_price}, limit_price={limit_price}, feedback={feedback}"
        )
        
        if not isinstance(symbol, str) or not symbol:
            return make_input_error("参数 symbol 必须为非空字符串，如 'BTCUSDT'", feedback)
        
        if not isinstance(side, str) or side not in ("BUY", "SELL"):
            return make_input_error("参数 side 必须为 'BUY' 或 'SELL'（大写）", feedback)
        
        if not isinstance(tp_price, (int, float)) or tp_price <= 0:
            return make_input_error("参数 tp_price 必须为正数", feedback)
        
        if not isinstance(sl_price, (int, float)) or sl_price <= 0:
            return make_input_error("参数 sl_price 必须为正数", feedback)
        
        if not isinstance(feedback, str) or not feedback:
            return make_input_error("参数 feedback 必须为非空字符串，详细分析当前的阶段并给出下一步计划", feedback)
            
        if limit_price is not None:
            if not isinstance(limit_price, (int, float)) or limit_price <= 0:
                return make_input_error("参数 limit_price 必须为正数", feedback)

        # 2. 确定入场价格（挂单价 或 市价）
        if limit_price is not None and limit_price > 0:
            entry_price = float(limit_price)
            logger.info(f"calc_metrics_tool: 挂单模式，使用指定价格 -> {entry_price}")
        else:
            entry_price = get_current_price(symbol)
            if entry_price is None or entry_price <= 0:
                return {
                    "error": f"TOOL_RUNTIME_ERROR: 无法获取 {symbol} 的最新价格，请检查 symbol 或稍后重试。",
                    "feedback": feedback,
                }
            logger.info(f"calc_metrics_tool: 市价模式，自动获取 {symbol} 最新价格 -> {entry_price}")

        # 3. 价格关系校验
        tp = float(tp_price)
        sl = float(sl_price)
        
        if side == "BUY":
            if not (tp > entry_price > sl):
                return make_input_error(
                    f"多头要求 tp_price > entry_price > sl_price，当前: tp={tp}, entry={entry_price}, sl={sl}。"
                    f"请调整 TP/SL 价格后重试",
                    feedback
                )
            sl_dist = entry_price - sl
            tp_dist = tp - entry_price
            side_norm = "long"
            
            # 新增：动态最小止盈止损距离校验（基于ATR）
            error = _validate_min_distance(symbol, entry_price, sl_dist, tp_dist, feedback)
            if error:
                return error

        else:  # SELL
            if not (sl > entry_price > tp):
                return make_input_error(
                    f"空头要求 sl_price > entry_price > tp_price，当前: sl={sl}, entry={entry_price}, tp={tp}。"
                    f"请调整 TP/SL 价格后重试",
                    feedback
                )
            sl_dist = sl - entry_price
            tp_dist = entry_price - tp
            side_norm = "short"
            
            # 新增：动态最小止盈止损距离校验（基于ATR）
            error = _validate_min_distance(symbol, entry_price, sl_dist, tp_dist, feedback)
            if error:
                return error
        
        sl_dist_pct = (sl_dist / entry_price) * 100

        # 4. 计算指标
        rr = tp_dist / sl_dist
        tp_dist_pct = (tp_dist / entry_price) * 100

        # 5. 构建易读的摘要（纯计算结果，不含建议）
        side_cn = "做多" if side_norm == "long" else "做空"
        
        summary = f"""风险回报率计算结果
交易对: {symbol} | 方向: {side_cn}
入场价: ${entry_price:.4f}
止盈价: ${tp:.4f} (+{tp_dist_pct:.2f}%) | 距离: {tp_dist:.4f}
止损价: ${sl:.4f} (-{sl_dist_pct:.2f}%) | 距离: {sl_dist:.4f}
风险回报率 (R:R): {rr:.2f}:1"""

        result = {
            "summary": summary,
            "direction": side_norm,
            "prices": {
                "entry": round(entry_price, 8),
                "tp": round(tp, 8),
                "sl": round(sl, 8),
                "limit": round(float(limit_price), 8) if limit_price else None,
            },
            "distances": {
                "tp": {
                    "abs": round(tp_dist, 8),
                    "pct": round(tp_dist_pct, 2),
                },
                "sl": {
                    "abs": round(sl_dist, 8),
                    "pct": round(sl_dist_pct, 2),
                },
            },
            "rr": {
                "value": round(rr, 6),
                "text": f"{rr:.2f}:1",
            },
            "checks": {
                "rr_lt_1": rr < 1,
                "rr_lt_0_8": rr < 0.8,
            },
            "inputs": {
                "symbol": symbol,
                "side": side_norm,
                "entry_price": round(entry_price, 8),
                "tp_price": round(tp, 8),
                "sl_price": round(sl, 8),
                "limit_price": round(float(limit_price), 8) if limit_price else None,
            },
            "feedback": feedback,
        }

        logger.info(
            "calc_metrics_tool: 计算完成 -> symbol=%s, entry=%.8f, rr=%.2f",
            symbol,
            entry_price,
            rr,
        )
        return result

    except Exception as e:
        logger.error(f"calc_metrics_tool: 异常 -> {e}")
        return {"error": f"TOOL_RUNTIME_ERROR: 计算失败 - {str(e)}", "feedback": feedback if isinstance(feedback, str) else ""}

