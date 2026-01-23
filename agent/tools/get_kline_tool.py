"""获取指定币种K线数据的工具"""
from typing import Dict, Any, List
from langchain.tools import tool
from monitor_module.clients.binance_rest import BinanceRestClient
from monitor_module.data.models import Kline
from config.settings import get_config
from monitor_module.utils.logger import setup_logger

logger = setup_logger()


@tool("get_kline", description="获取指定交易对的K线数据", parse_docstring=True)
def get_kline_tool(symbol: str, interval: str, feedback: str, limit: int = 50) -> List[Dict[str, Any]]:
    """获取标准化K线数据。
    
    为后续分析/可视化提供轻量的K线基础数据（仅返回OHLCV）。适合先做概览，
    再按需获取单一指标序列。先用该工具获取K线，再按需使用 get_indicators(type=...) 
    获取单一指标的时间序列。调用时必须提供 feedback 参数，详细分析当前的阶段，并且
    给出下一步的计划。
    
    Args:
        symbol: 交易对，如 "BTCUSDT"。
        interval: K线间隔，如 "3m"、"15m"、"1h"、"4h"。
        feedback: 当前分析进度总结，详细说明当前的分析阶段，并给出下一步的计划。
        limit: 返回数量，建议 30-50。
    
    Returns:    
        K线数据列表，每个元素为字典：{"开": float, "高": float, "低": float, "收": float, 
        "量": float, "涨跌": str, "振幅": str}。首个元素包含额外的 "feedback" 字段，
        原路返回调用时提供的分析进度说明。
    """
    def _error(msg: str) -> List[Dict[str, Any]]:
        return [{"error": f"TOOL_INPUT_ERROR: {msg}. 请修正参数后重试。", "feedback": feedback if isinstance(feedback, str) else ""}]
    try:
        # 记录工具调用
        logger.info(f"get_kline_tool 被调用 - symbol={symbol}, interval={interval}, limit={limit}, feedback={feedback}")
        # 参数校验
        if not isinstance(symbol, str) or not symbol:
            return _error("参数 symbol 必须为非空字符串，如 'BTCUSDT'")
        if not isinstance(interval, str) or not interval:
            return _error("参数 interval 必须为非空字符串，如 '15m' 或 '1h'")
        if not isinstance(feedback, str) or not feedback:
            return _error("参数 feedback 必须为非空字符串，详细分析当前的阶段，并且给出以及下一步的计划")
        valid_intervals = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '3d', '1w', '1M']
        if interval not in valid_intervals:
            return _error(f"无效的 interval: {interval}，支持: {', '.join(valid_intervals)}")
        if not isinstance(limit, int) or limit <= 0 or limit > 50:
            return _error("参数 limit 必须为 1..50 的整数（建议<=50）")
        # 调用API获取K线数据
        logger.info(f"调用API - {symbol} {interval} limit={limit} | feedback: {feedback}")
        cfg = get_config()
        client = BinanceRestClient(cfg)
        raw = client.get_klines(symbol, interval, limit)
        if not raw:
            return [{"error": "TOOL_RUNTIME_ERROR: 未获取到K线数据，请检查 symbol/interval 或稍后重试。", "feedback": feedback}]
        klines: List[Dict[str, Any]] = []
        for item in raw:
            k = Kline.from_rest_api(item)
            # 计算涨跌幅和振幅
            chg_pct = 0.0
            amp_pct = 0.0
            if k.open != 0:
                chg_pct = (k.close - k.open) / k.open * 100
                amp_pct = (k.high - k.low) / k.open * 100
            
            chg_str = f"+{chg_pct:.2f}%" if chg_pct >= 0 else f"{chg_pct:.2f}%"

            klines.append({
                "开": k.open,
                "高": k.high,
                "低": k.low,
                "收": k.close,
                "量": k.volume,
                "涨跌": chg_str,
                "振幅": f"{amp_pct:.2f}%"
            })
        # 在第一个元素中添加 feedback 字段
        if klines:
            klines[0]["feedback"] = feedback
        return klines
    except Exception as e:
        return [{"error": f"TOOL_RUNTIME_ERROR: 获取K线失败 - {str(e)}", "feedback": feedback if isinstance(feedback, str) else ""}]