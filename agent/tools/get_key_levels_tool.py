import json
from typing import Dict, Any, List
from langchain.tools import tool
from config.settings import get_config
from monitor_module.clients.binance_rest import BinanceRestClient
from monitor_module.data.models import Kline
from monitor_module.utils.logger import setup_logger
from monitor_module.indicators.atr import calculate_atr_list

logger = setup_logger()

def _error(msg: str, feedback: str) -> Dict[str, Any]:
    return {"error": f"TOOL_INPUT_ERROR: {msg}. 请修正参数后重试。", "feedback": feedback if isinstance(feedback, str) else ""}

def _swing_points(kl: List[Kline]) -> Dict[str, List[Dict[str, Any]]]:
    highs: List[Dict[str, Any]] = []
    lows: List[Dict[str, Any]] = []
    n = len(kl)
    for i in range(2, n - 2):
        h = kl[i].high
        l = kl[i].low
        if h > kl[i - 1].high and h > kl[i + 1].high and h >= kl[i - 2].high and h >= kl[i + 2].high:
            highs.append({"price": float(h)})
        if l < kl[i - 1].low and l < kl[i + 1].low and l <= kl[i - 2].low and l <= kl[i + 2].low:
            lows.append({"price": float(l)})
    return {"highs": highs, "lows": lows}

def _cluster_levels(points: List[Dict[str, Any]], eps: float) -> List[Dict[str, Any]]:
    if not points:
        return []
    pts = sorted(points, key=lambda x: x["price"])  
    clusters: List[Dict[str, Any]] = []
    cur: Dict[str, Any] = {"center": pts[0]["price"], "members": [pts[0]]}
    for p in pts[1:]:
        if abs(p["price"] - cur["center"]) <= eps:
            cur["members"].append(p)
            cur["center"] = sum(m["price"] for m in cur["members"]) / len(cur["members"])  
        else:
            clusters.append(cur)
            cur = {"center": p["price"], "members": [p]}
    clusters.append(cur)
    out: List[Dict[str, Any]] = []
    for c in clusters:
        prices = [m["price"] for m in c["members"]]
        lower = float(c["center"] - eps)
        upper = float(c["center"] + eps)
        out.append({
            "price": float(c["center"]),
            "zone_lower": lower,
            "zone_upper": upper,
            "touches": int(len(prices)),
        })
    return out

@tool("get_key_levels", description="计算关键价格水平(支撑/阻力/SR翻转)，为交易决策提供核心锚点。支持 1h/4h/15m。", parse_docstring=True)
def get_key_levels_tool(symbol: str, interval: str, feedback: str, limit: int = 200) -> Dict[str, Any]:
    """计算关键价格水平(支撑/阻力/SR翻转)，为交易决策提供核心锚点。支持 1h/4h/15m。

    这是高周期分析的核心工具，用于识别市场结构定义的关键价格区间。
    
    **使用指南**：
    1. **锚定作用**：所有的入场、止损(SL)、止盈(TP)都必须基于这些识别出的区域(Zone)。
    2. **区域概念**：关键位是一个区间 [zone_lower, zone_upper]，而非单一直线。价格进入该区域即视为测试关键位。
    3. **交易纪律**：
       - **入场**：应在价格回踩支撑区或反抽阻力区时寻找机会。
       - **止损**：应设置在关键位区域外侧，并留有一定缓冲。
       - **拒绝**：如果价格远离这些关键位（处于"半空中"），应拒绝开仓，等待价格回归结构。
    
    工作原理:
    通过识别K线图上的重要摆动高/低点，并使用基于ATR的动态容差进行聚类，从而找出被市场
    多次验证的支撑、阻力及SR翻转区。

    Args:
        symbol: 交易对，如 "BTCUSDT"。
        interval: 周期，必须为 "1h"、"4h" 或 "15m"。
        feedback: 当前分析进度总结及下一步计划。
        limit: 获取K线数量，建议≥120根，以确保能识别出足够多的有效摆动点。

    Returns:
        一个包含关键位信息的字典，核心字段为 `supports`, `resistances`, `sr_flips`。
        {
          "interval": str,
          "current_price": float,
          "atr": float,
          "supports": [{"price": float, "zone_lower": float, "zone_upper": float, "touches": int}],
          "resistances": [...],
          "sr_flips": [...]
        }
    """
    try:
        logger.info(f"get_key_levels_tool 被调用 - symbol={symbol}, interval={interval}, limit={limit}, feedback={feedback}")
        if not isinstance(symbol, str) or not symbol.strip():
            return _error("参数 symbol 必须为非空字符串，如 'BTCUSDT'", feedback)
        if not isinstance(interval, str) or not interval.strip():
            return _error("参数 interval 必须为非空字符串，如 '1h' 或 '4h'", feedback)
        valid = ['1h', '4h', '15m']
        if interval not in valid:
            return _error(f"无效的 interval: {interval}，仅支持: {', '.join(valid)}", feedback)
        if not isinstance(limit, int) or limit < 60 or limit > 500:
            return _error("参数 limit 必须为 60..500 的整数", feedback)

        cfg = get_config()
        client = BinanceRestClient(cfg)
        raw = client.get_klines(symbol, interval, limit)
        if not raw:
            return {"error": "TOOL_RUNTIME_ERROR: 未获取到K线数据", "feedback": feedback}

        kl: List[Kline] = [Kline.from_rest_api(item) for item in raw]
        closes = [k.close for k in kl]
        atr_period = int(cfg['indicators']['atr_period'])
        atr_list = calculate_atr_list(kl, atr_period)
        atr_val = float(atr_list[-1]) if atr_list else 0.0

        eps_factor = 0.1
        eps = max(atr_val * eps_factor, 1e-8)

        swings = _swing_points(kl)
        sup_clusters = _cluster_levels([{"price": x["price"]} for x in swings["lows"]], eps)
        res_clusters = _cluster_levels([{"price": x["price"]} for x in swings["highs"]], eps)
        sup_clusters = [c for c in sup_clusters if c["touches"] >= 3]
        res_clusters = [c for c in res_clusters if c["touches"] >= 3]

        flips: List[Dict[str, Any]] = []
        for s in sup_clusters:
            for r in res_clusters:
                if max(s["zone_lower"], r["zone_lower"]) <= min(s["zone_upper"], r["zone_upper"]):
                    center = (s["price"] + r["price"]) / 2.0
                    flip_touches = int(s["touches"] + r["touches"])
                    if flip_touches >= 3:
                        flips.append({
                            "price": float(center),
                            "zone_lower": float(max(s["zone_lower"], r["zone_lower"])),
                            "zone_upper": float(min(s["zone_upper"], r["zone_upper"])),
                            "touches": flip_touches,
                        })

        current_price = float(closes[-1]) if closes else 0.0
        result = {
            "interval": interval,
            "current_price": current_price,
            "atr": atr_val,
            "supports": sup_clusters,
            "resistances": res_clusters,
            "sr_flips": flips,
        }
        result["feedback"] = feedback
        logger.info(
            "get_key_levels_tool: 构造的关键位:\n%s",
            json.dumps(result, ensure_ascii=False, indent=2)
        )
        return result
    except Exception as e:
        return {"error": f"TOOL_RUNTIME_ERROR: 关键位计算失败 - {str(e)}", "feedback": feedback}