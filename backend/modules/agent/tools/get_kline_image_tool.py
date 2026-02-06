"""获取K线图图像的工具（含技术指标）

使用 Pillow 渲染器实现高并发图表生成，线程安全，无需子进程隔离。
"""
import time
from typing import Dict, Any, List
from langchain.tools import tool

from modules.agent.tools.tool_utils import validate_symbol, validate_interval
from modules.agent.utils.kline_utils import fetch_klines, get_kline_provider
from modules.agent.tools.chart_renderer_pillow import render_kline_chart_pillow
from modules.monitor.utils.logger import get_logger

logger = get_logger('agent.tool.get_kline_image')


@tool("get_kline_image", description="获取K线图图像数据（含技术指标）", parse_docstring=True)
def get_kline_image_tool(
    symbol: str,
    interval: str = "1h",
    feedback: str = "",
) -> List[Dict[str, Any]]:
    """获取单周期K线图并进行视觉分析（含技术指标：EMA、MACD、RSI、Bollinger Bands）。
    
    该工具生成指定时间周期的K线图，返回多模态内容（文本描述+图像），供模型进行视觉分析。
    返回格式为 list[dict]，包含文本和图像内容块。错误时返回包含错误信息的文本块。
    
    Args:
        symbol: 交易对，如 "BTCUSDT"
        interval: 时间周期，如 "3m"、"15m"、"1h"。默认为 "1h"。注意：仅支持单个周期。
        feedback: 分析进度笔记。请填写：1) 上一周期分析的关键结论（趋势方向、关键位、动能状态）；2) 本次调用的分析目的（如"验证4h趋势是否与1d一致"或"寻找1h级别的入场触发信号"）。
    """
    def _make_error(msg: str) -> List[Dict[str, Any]]:
        return [{"type": "text", "text": f"TOOL_INPUT_ERROR: {msg}. 请修正参数后重试。"}]
    
    def _make_runtime_error(msg: str) -> List[Dict[str, Any]]:
        return [{"type": "text", "text": f"TOOL_RUNTIME_ERROR: {msg}"}]
    
    try:
        t_start = time.perf_counter()
        limit = 100
        
        logger.info(f"get_kline_image_tool 被调用 - symbol={symbol}, interval={interval}")
        
        error = validate_symbol(symbol)
        if error:
            return _make_error(error)
        
        error = validate_interval(interval)
        if error:
            return _make_error(error)
        
        if ',' in interval:
             return _make_error("参数 interval 仅支持单个周期，请不要使用逗号分隔。如需多个周期请多次调用。")
        
        interval = interval.strip()
        
        fetch_limit = limit + 100
        
        t_fetch_start = time.perf_counter()
        indicators = None
        provider = get_kline_provider()
        if provider and hasattr(provider, "get_klines_with_indicators"):
            klines, indicators = provider.get_klines_with_indicators(symbol, interval, fetch_limit)
            error = None if klines else f"未获取到 {symbol} {interval} 的K线数据"
        else:
            klines, error = fetch_klines(symbol, interval, fetch_limit)
        t_fetch_end = time.perf_counter()
        fetch_ms = (t_fetch_end - t_fetch_start) * 1000
        
        if error or not klines:
            return _make_runtime_error(error or f"未获取到 {symbol} {interval} 的K线数据")
        
        t_render_start = time.perf_counter()
        image_base64 = render_kline_chart_pillow(klines, symbol, interval, limit, indicators)
        t_render_end = time.perf_counter()
        render_ms = (t_render_end - t_render_start) * 1000
        
        total_ms = (t_render_end - t_start) * 1000
        logger.info(f"[PERF] {symbol} {interval}: fetch={fetch_ms:.1f}ms, render={render_ms:.1f}ms, total={total_ms:.1f}ms")
        
        return [
            {
                "type": "text",
                "text": f"K线图生成成功\n交易对: {symbol}\n时间周期: {interval}\nK线数量: {limit}"
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{image_base64}",
                    "detail": "high"
                }
            }
        ]
        
    except TimeoutError as e:
        logger.error(f"K线图渲染超时: {symbol} {interval}")
        return _make_runtime_error(str(e))
    except Exception as e:
        logger.error(f"K线图分析失败: {e}", exc_info=True)
        return _make_runtime_error(f"生成K线图失败 - {str(e)}")
