"""获取指定币种的技术指标数据工具（按类型返回指定指标的时间序列）"""
from typing import Dict, Any, List
from langchain.tools import tool

from modules.agent.tools.tool_utils import (
    make_input_error_list,
    make_runtime_error_list,
    validate_common_params,
    fetch_klines,
    get_binance_client,
    get_kline_provider,
)
from modules.config.settings import get_config
from modules.monitor.utils.logger import get_logger

logger = get_logger('agent.tool.get_indicators')

from modules.monitor.indicators.atr import calculate_atr_list
from modules.monitor.indicators.volatility import (
    calculate_ema_list,
    calculate_rsi_list,
    calculate_bollinger_bandwidth,
    calculate_bollinger_bands,
    calculate_macd_list,
)
from modules.monitor.indicators.open_interest import (
    parse_oi_hist_response,
)


@tool(
    "get_indicators",
    description="获取指定币种、周期和指标类型的技术指标时间序列（支持 macd/ema/bb/oi/rsi/atr）",
    parse_docstring=True
)
def get_indicators_tool(symbol: str, interval: str, indicator_type: str, feedback: str) -> List[Dict[str, Any]]:
    """获取指定币种、周期和指标类型的技术指标时间序列（固定30根）。
    
    根据指定的指标类型返回相应的技术指标数据，用于趋势判断、背离分析、动能确认等。
    
    Args:
        symbol: 交易对，如 BTCUSDT。
        interval: K线间隔，如 3m、15m、1h、4h。
        indicator_type: 指标类型，支持 macd（返回 histogram/signal_line/macd_line）、ema（返回 ema_fast/ema_slow）、bb（返回 bb_width/bb_upper/bb_lower）、oi（返回 oi/oi_value，仅5m及以上周期）、rsi（返回 rsi）、atr（返回 atr）。
        feedback: 当前分析进度总结，详细说明当前的分析阶段，并给出下一步的计划。
    
    Returns:
        指标数据列表（30个数据点），每个元素根据 indicator_type 包含不同字段。
        注：工具自动获取额外历史数据确保所有指标完整计算，返回最近30个数据点
    """
    try:
        return_limit = 30
        fetch_limit = 60
        
        logger.info(f"get_indicators_tool 被调用 - symbol={symbol}, interval={interval}, indicator_type={indicator_type}, feedback={feedback}")
        
        error = validate_common_params(symbol=symbol, interval=interval, feedback=feedback)
        if error:
            return make_input_error_list(error, feedback)
        
        if not isinstance(indicator_type, str) or indicator_type not in ['macd', 'ema', 'bb', 'oi', 'rsi', 'atr']:
            return make_input_error_list("参数 indicator_type 必须为以下之一: macd, ema, bb, oi, rsi, atr", feedback)
        
        if indicator_type == 'oi' and interval in ['1m', '3m']:
            return make_input_error_list(f"持仓量(oi)指标不支持 {interval} 周期，请使用 5m 或更高周期", feedback)
        
        logger.info(f"调用API - {symbol} {interval} indicator_type={indicator_type} | feedback: {feedback}")
        klines, fetch_error = fetch_klines(symbol, interval, fetch_limit)
        if fetch_error:
            return make_runtime_error_list(fetch_error, feedback)
        
        closes = [k.close for k in klines]
        cfg = get_config()
        
        # 读取配置参数
        indi_cfg = cfg['indicators']
        
        # 根据指标类型计算相应的数据
        all_points: List[Dict[str, Any]] = []
        
        if indicator_type == 'atr':
            atr_period = int(indi_cfg['atr_period'])
            atr_list = calculate_atr_list(klines, atr_period) or []
            for i in range(len(klines)):
                point = {
                    "atr": round(float(atr_list[i - atr_period]), 4) if i >= atr_period and (i - atr_period) < len(atr_list) else None
                }
                all_points.append(point)
        
        elif indicator_type == 'rsi':
            rsi_period = int(indi_cfg['rsi_period'])
            rsi_list = calculate_rsi_list(closes, rsi_period) or []
            for i in range(len(klines)):
                point = {
                    "rsi": round(float(rsi_list[i - rsi_period]), 6) if i >= rsi_period and (i - rsi_period) < len(rsi_list) else None
                }
                all_points.append(point)
        
        elif indicator_type == 'ema':
            ema_fast_period = int(indi_cfg['ema_fast_period'])
            ema_slow_period = int(indi_cfg['ema_slow_period'])
            ema_fast_list = calculate_ema_list(closes, ema_fast_period) or []
            ema_slow_list = calculate_ema_list(closes, ema_slow_period) or []
            for i in range(len(klines)):
                point = {
                    "ema_fast": round(float(ema_fast_list[i]), 5) if i < len(ema_fast_list) else None,
                    "ema_slow": round(float(ema_slow_list[i]), 5) if i < len(ema_slow_list) else None
                }
                all_points.append(point)
        
        elif indicator_type == 'macd':
            macd_fast_period = int(indi_cfg['macd_fast_period'])
            macd_slow_period = int(indi_cfg['macd_slow_period'])
            macd_signal_period = int(indi_cfg['macd_signal_period'])
            macd_line, signal_line, histogram = calculate_macd_list(closes, macd_fast_period, macd_slow_period, macd_signal_period)
            for i in range(len(klines)):
                point = {
                    "macd_line": round(float(macd_line[i]), 6) if i < len(macd_line) else None,
                    "signal_line": round(float(signal_line[i]), 6) if i < len(signal_line) else None,
                    "histogram": round(float(histogram[i]), 6) if i < len(histogram) else None
                }
                all_points.append(point)
        
        elif indicator_type == 'bb':
            bb_period = int(indi_cfg['bb_period'])
            bb_std_multiplier = float(indi_cfg['bb_std_multiplier'])
            
            # 计算布林带上下轨和宽度
            for i in range(len(closes)):
                if i + 1 >= bb_period:
                    bands = calculate_bollinger_bands(closes[:i + 1], bb_period, bb_std_multiplier)
                    bandwidth = calculate_bollinger_bandwidth(closes[:i + 1], bb_period, bb_std_multiplier)
                    if bands:
                        bb_upper, bb_middle, bb_lower = bands
                        point = {
                            "bb_upper": round(float(bb_upper), 5),
                            "bb_lower": round(float(bb_lower), 5),
                            "bb_width": round(float(bandwidth), 4) if bandwidth is not None else None
                        }
                    else:
                        point = {"bb_upper": None, "bb_lower": None, "bb_width": None}
                else:
                    point = {"bb_upper": None, "bb_lower": None, "bb_width": None}
                all_points.append(point)
        
        elif indicator_type == 'oi':
            provider = get_kline_provider()
            if provider is not None:
                logger.warning("回测模式下不支持持仓量(oi)指标，返回空数据")
                for i in range(len(klines)):
                    all_points.append({"oi": None, "oi_value": None})
            else:
                try:
                    client = get_binance_client()
                    raw_oi = client.get_open_interest_hist(symbol, interval, fetch_limit)
                    if raw_oi:
                        oi_values, oi_value_values, _ = parse_oi_hist_response(raw_oi)
                        for i in range(len(klines)):
                            point = {
                                "oi": round(float(oi_values[i]), 2) if i < len(oi_values) else None,
                                "oi_value": round(float(oi_value_values[i]), 2) if i < len(oi_value_values) else None
                            }
                            all_points.append(point)
                    else:
                        return make_runtime_error_list("未获取到持仓量数据", feedback)
                except Exception as e:
                    logger.error(f"获取持仓量数据失败: {e}")
                    return make_runtime_error_list(f"获取持仓量数据失败 - {str(e)}", feedback)
        
        series = all_points[-return_limit:] if len(all_points) >= return_limit else all_points
        
        if series:
            series[0]["feedback"] = feedback

        return series
    except Exception as e:
        return make_runtime_error_list(f"获取指标序列失败 - {str(e)}", feedback)