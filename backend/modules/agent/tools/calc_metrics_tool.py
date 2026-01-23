from typing import Any, Dict, Optional
from langchain.tools import tool
from modules.monitor.utils.logger import setup_logger
from modules.monitor.clients.binance_rest import BinanceRestClient
from modules.monitor.data.models import Kline
from modules.config.settings import get_config


logger = setup_logger()


def _error(msg: str, feedback: str = "") -> Dict[str, Any]:
    return {"error": f"TOOL_INPUT_ERROR: {msg}. 请修正参数后重试。", "feedback": feedback}


def _get_latest_price(symbol: str) -> float | None:
    """获取指定交易对的最新价格（使用1m K线的收盘价）"""
    try:
        cfg = get_config()
        client = BinanceRestClient(cfg)
        raw = client.get_klines(symbol, "1m", 1)
        if raw and len(raw) > 0:
            k = Kline.from_rest_api(raw[0])
            return k.close
        return None
    except Exception as e:
        logger.error(f"_get_latest_price: 获取 {symbol} 最新价格失败 -> {e}")
        return None


@tool(
    "calc_metrics",
    description=(
        "交易计算器：便捷计算 rr、1R/2R 触发价位与 TP/SL 建议。"
        "仅支持市价模式，自动获取最新价作为入场价。"
        "返回的 rr/触发价仅用于参考，自主判断。"
    ),
    parse_docstring=True,
)
def calc_metrics_tool(
    symbol: str,
    side: str,
    tp_price: float,
    sl_price: float,
    feedback: str,
) -> Dict[str, Any]:
    """交易计算器：计算R:R、1R/2R触发价位、建议TP/SL（仅支持市价模式）。

    概要:
        - 市价模式：自动获取 symbol 的最新价格作为入场价
        - 自动计算 R:R、1R/2R 触发价位、建议 TP/SL
        - **风控辅助**：提供 R:R 质量评估（Excellent/Good/Poor），辅助决策。

    Args:
        symbol (str): 交易对，如 "BTCUSDT"。必须为非空字符串。
        side (str): 仓位方向，仅支持 "BUY" 或 "SELL"（大写）。多头要求 tp > entry > sl，
            空头要求 sl > entry > tp。
        tp_price (float): 止盈价格（正数，绝对价格）。
        sl_price (float): 止损价格（正数，绝对价格）。
        feedback (str): 当前分析进度总结，详细说明当前的分析阶段与下一步计划。
            必须为非空字符串，用于追溯决策逻辑。
        入场价格不提供，工具会自动获取最新市价。

    Returns:
        Dict[str, Any]: 结构化结果，主要包含：
            - inputs: 原始入参的规范化回显（含自动获取的 entry_price）。
            - metrics:
                - entry_price (float): 自动获取的最新价（入场价）。
                - sl_distance (float): SL 与入场的距离（价格单位）。
                - tp_distance (float): TP 与入场的距离（价格单位）。
                - rr (float): 风险回报比 = tp_distance / sl_distance。
                - r1_price (float): 1R 触发价（用于移动保护到盈亏平衡）。
                - r2_price (float): 2R 触发价（用于启用追踪止盈）。
            - checks:
                - sl_distance_pct (float): 止损距离百分比（仅供参考）。
            - suggestions:
                - is_rr_valid (bool): R:R 是否达标 (>= 1.5)。
                - quality (str): 交易质量评价 (Excellent/Good/Poor)。
                - action_suggestion (str): 基于 R:R 的行动建议。
            - feedback (str): 原路返回调用时提供的分析进度说明。

    Raises:
        无显式异常；错误时以 {"error": "TOOL_INPUT_ERROR/TOOL_RUNTIME_ERROR: ...", "feedback": ...} 返回。
    """
    try:
        # 1. 参数校验
        logger.info(
            f"calc_metrics_tool 被调用 - symbol={symbol}, side={side}, tp={tp_price}, sl={sl_price}, feedback={feedback}"
        )
        
        if not isinstance(symbol, str) or not symbol:
            return _error("参数 symbol 必须为非空字符串，如 'BTCUSDT'", feedback)
        
        if not isinstance(side, str) or side not in ("BUY", "SELL"):
            return _error("参数 side 必须为 'BUY' 或 'SELL'（大写）", feedback)
        
        if not isinstance(tp_price, (int, float)) or tp_price <= 0:
            return _error("参数 tp_price 必须为正数", feedback)
        
        if not isinstance(sl_price, (int, float)) or sl_price <= 0:
            return _error("参数 sl_price 必须为正数", feedback)
        
        if not isinstance(feedback, str) or not feedback:
            return _error("参数 feedback 必须为非空字符串，详细分析当前的阶段并给出下一步计划", feedback)

        # 2. 确定入场价格（市价自动获取）
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
                return _error(
                    f"多头要求 tp_price > entry_price > sl_price，当前: tp={tp}, entry={entry_price}, sl={sl}。"
                    f"请调整 TP/SL 价格后重试。",
                    feedback
                )
            sl_dist = entry_price - sl
            tp_dist = tp - entry_price
            sign = 1.0
            side_norm = "long"
        else:  # SELL
            if not (sl > entry_price > tp):
                return _error(
                    f"空头要求 sl_price > entry_price > tp_price，当前: sl={sl}, entry={entry_price}, tp={tp}。"
                    f"请调整 TP/SL 价格后重试。",
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

        # 6. 质量评估与建议
        is_rr_valid = rr >= 1.5
        if rr >= 2.0:
            quality = "Excellent"
            action_suggestion = "R:R 优秀，建议执行。"
        elif rr >= 1.5:
            quality = "Good"
            action_suggestion = "R:R 达标，可以执行。"
        else:
            quality = "Poor (Risk/Reward too low)"
            action_suggestion = "R:R 不足 1.5，建议拒绝开仓或等待更优入场位。"

        checks = {
            "sl_distance_pct": round(sl_dist_pct, 2),
        }

        suggestions = {
            "is_rr_valid": is_rr_valid,
            "quality": quality,
            "action_suggestion": action_suggestion,
        }

        # 7. 返回结果
        result = {
            "inputs": {
                "symbol": symbol,
                "side": side_norm,
                "entry_price": round(entry_price, 8),
                "tp_price": round(tp, 8),
                "sl_price": round(sl, 8),
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
            "suggestions": suggestions,
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


