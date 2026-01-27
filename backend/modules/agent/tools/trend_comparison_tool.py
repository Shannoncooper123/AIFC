"""趋势对比工具：对比目标币种相对于BTC的趋势强度"""
from typing import Dict, Any, List
from langchain.tools import tool

from modules.monitor.data.models import Kline
from modules.monitor.utils.logger import get_logger
from modules.agent.tools.tool_utils import fetch_klines

logger = get_logger('agent.tool.trend_comparison')


def _calculate_zscore_trend(klines_data: List[Kline], window: int = 20) -> List[float]:
    """计算标准化趋势强度（Z-score）
    
    Args:
        klines_data: K线数据列表
        window: 滚动窗口大小（默认20期）
    
    Returns:
        Z-score序列
    """
    # 计算收盘价之间的变化率 (close[i] - close[i-1]) / close[i-1] * 100
    # 这反映了价格趋势的方向和强度
    returns = []
    for i in range(len(klines_data)):
        if i == 0:
            # 第一根K线没有前一根，收益率为0
            returns.append(0.0)
        else:
            prev_close = klines_data[i - 1].close
            curr_close = klines_data[i].close
            if prev_close != 0:
                ret = (curr_close - prev_close) / prev_close * 100
                returns.append(ret)
            else:
                returns.append(0.0)
    
    # 计算Z-score
    zscores = []
    for i in range(len(returns)):
        if i < window:
            # 数据不足，返回None
            zscores.append(None)
        else:
            # 计算窗口内的均值和标准差
            window_returns = returns[i - window + 1:i + 1]
            mean_ret = sum(window_returns) / len(window_returns)
            
            # 计算标准差
            variance = sum((r - mean_ret) ** 2 for r in window_returns) / len(window_returns)
            std_ret = variance ** 0.5
            
            # 计算Z-score
            if std_ret != 0:
                zscore = (returns[i] - mean_ret) / std_ret
                zscores.append(zscore)
            else:
                zscores.append(0.0)
    
    return zscores


@tool(
    "trend_comparison",
    description="对比目标币种相对于BTC的趋势强度（基于Z-score标准化）",
    parse_docstring=True
)
def trend_comparison_tool(symbol: str, interval: str, feedback: str) -> List[float]:
    """对比目标币种相对于BTC的趋势强度时间序列（固定30根）。
    
    通过计算目标币种和BTC的Z-score差值，判断该币种相对市场（BTC）的相对强弱：
    - **正值**：目标币种趋势强于BTC（独立上涨或抗跌）
    - **负值**：目标币种趋势弱于BTC（跟随下跌或涨幅不及）
    - **持续正值**：强势特征，适合做多
    - **持续负值**：弱势特征，适合做空或观望
    
    返回：30个浮点数列表，从旧到新排列，正值表示强于BTC，负值表示弱于BTC。
    
    Args:
        symbol: 交易对，如 ETHUSDT。注意：如果是 BTCUSDT，所有值将返回0
        interval: K线间隔，如 3m、15m、1h、4h
        feedback: 当前分析进度总结，详细说明当前的分析阶段，并给出下一步的计划
    """
    def _error(msg: str) -> str:
        import json
        return json.dumps({"error": f"TOOL_INPUT_ERROR: {msg}. 请修正参数后重试。"}, ensure_ascii=False)
    
    try:
        return_limit = 30
        fetch_limit = 80
        
        logger.info(f"trend_comparison_tool 被调用 - symbol={symbol}, interval={interval}, feedback={feedback}")
        
        if not isinstance(symbol, str) or not symbol:
            return _error("参数 symbol 必须为非空字符串，如 'ETHUSDT'")
        if not isinstance(interval, str) or not interval:
            return _error("参数 interval 必须为非空字符串，如 '15m' 或 '1h'")
        from modules.constants import VALID_INTERVALS
        if interval not in VALID_INTERVALS:
            return _error(f"无效的 interval: {interval}，支持: {', '.join(VALID_INTERVALS)}")
        if not isinstance(feedback, str) or not feedback:
            return _error("参数 feedback 必须为非空字符串，详细分析当前的阶段，并且给出下一步的计划")
        
        klines, error = fetch_klines(symbol, interval, fetch_limit)
        if error or not klines:
            import json
            return json.dumps({"error": f"TOOL_RUNTIME_ERROR: {error or '未获取到K线数据'}"}, ensure_ascii=False)
        
        all_values: List[float] = []
        
        if symbol.upper() == 'BTCUSDT':
            logger.info(f"目标币种为BTCUSDT，趋势对比值全部返回0")
            all_values = [0.0] * len(klines)
        else:
            btc_klines, btc_error = fetch_klines('BTCUSDT', interval, fetch_limit)
            if btc_error or not btc_klines:
                import json
                return json.dumps({"error": f"TOOL_RUNTIME_ERROR: {btc_error or '未获取到BTC K线数据'}"}, ensure_ascii=False)
            
            min_len = min(len(klines), len(btc_klines))
            klines = klines[:min_len]
            btc_klines = btc_klines[:min_len]
            
            symbol_zscores = _calculate_zscore_trend(klines)
            btc_zscores = _calculate_zscore_trend(btc_klines)
            
            for i in range(len(klines)):
                symbol_z = symbol_zscores[i]
                btc_z = btc_zscores[i]
                
                if symbol_z is not None and btc_z is not None:
                    trend_comp = round(float(symbol_z - btc_z), 2)
                    all_values.append(trend_comp)
            
            logger.info(f"趋势对比指标计算完成 - {symbol} vs BTC，共{len(all_values)}个有效数据点")
        
        series = all_values[-return_limit:] if len(all_values) >= return_limit else all_values
        
        return series
        
    except Exception as e:
        logger.error(f"计算趋势对比指标失败: {e}", exc_info=True)
        import json
        return json.dumps({"error": f"TOOL_RUNTIME_ERROR: 计算趋势对比指标失败 - {str(e)}"}, ensure_ascii=False)
