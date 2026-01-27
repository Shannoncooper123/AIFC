from typing import Any, Dict, Optional
from langchain.tools import tool
from modules.monitor.utils.logger import get_logger
from modules.agent.tools.tool_utils import make_input_error, make_runtime_error, fetch_klines, get_kline_provider

logger = get_logger('agent.tool.calc_metrics')


def _get_latest_price(symbol: str) -> float | None:
    """获取指定交易对的最新价格
    
    回测模式下使用 KlineProvider 的当前模拟价格，
    实盘模式下使用1m K线的收盘价。
    """
    try:
        provider = get_kline_provider()
        if provider is not None:
            klines = provider.get_klines(symbol, "15m", 1)
            if klines:
                return klines[-1].close
            return None
        
        klines, error = fetch_klines(symbol, "1m", 1)
        if klines and len(klines) > 0:
            return klines[-1].close
        return None
    except Exception as e:
        logger.error(f"_get_latest_price: 获取 {symbol} 最新价格失败 -> {e}")
        return None


@tool(
    "calc_metrics",
    description=(
        "交易指标计算器：计算 R:R、1R/2R 触发价位。"
        "支持市价模式（自动获取最新价）和挂单模式（指定 limit_price）。"
        "纯计算工具，不提供交易建议。"
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
    """交易指标计算器：计算R:R、1R/2R触发价位（支持市价/挂单模式）。

    概要:
        - 市价模式：不传入 limit_price，自动获取 symbol 的最新价格作为入场价
        - 挂单模式：传入 limit_price，以此价格作为入场价计算
        - 自动计算 R:R、1R/2R 触发价位
        - 纯计算工具，不提供任何交易建议

    返回结构化字典，包含：
        - inputs: 原始入参回显（含使用的 entry_price）
        - metrics: entry_price, sl_distance, tp_distance, rr, r1_price, r2_price
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
            entry_price = _get_latest_price(symbol)
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
            sign = 1.0
            side_norm = "long"
        else:  # SELL
            if not (sl > entry_price > tp):
                return make_input_error(
                    f"空头要求 sl_price > entry_price > tp_price，当前: sl={sl}, entry={entry_price}, tp={tp}。"
                    f"请调整 TP/SL 价格后重试",
                    feedback
                )
            sl_dist = sl - entry_price
            tp_dist = entry_price - tp
            sign = -1.0
            side_norm = "short"
        
        sl_dist_pct = (sl_dist / entry_price) * 100

        # 4. 计算指标
        rr = tp_dist / sl_dist

        # 5. 1R/2R 触发价位
        r1_price = entry_price + sign * sl_dist
        r2_price = entry_price + sign * (2.0 * sl_dist)

        checks = {
            "sl_distance_pct": round(sl_dist_pct, 2),
        }

        result = {
            "inputs": {
                "symbol": symbol,
                "side": side_norm,
                "entry_price": round(entry_price, 8),
                "tp_price": round(tp, 8),
                "sl_price": round(sl, 8),
                "limit_price": round(float(limit_price), 8) if limit_price else None,
            },
            "metrics": {
                "entry_price": round(entry_price, 8),
                "sl_distance": round(sl_dist, 8),
                "tp_distance": round(tp_dist, 8),
                "rr": round(rr, 6),
                "r1_price": round(r1_price, 8),
                "r2_price": round(r2_price, 8),
            },
            "checks": checks,
            "feedback": feedback,
        }

        logger.info(
            "calc_metrics_tool: 计算完成 -> symbol=%s, entry=%.8f, rr=%.3f",
            symbol,
            entry_price,
            result["metrics"]["rr"],
        )
        return result

    except Exception as e:
        logger.error(f"calc_metrics_tool: 异常 -> {e}")
        return {"error": f"TOOL_RUNTIME_ERROR: 计算失败 - {str(e)}", "feedback": feedback if isinstance(feedback, str) else ""}


