"""K线形态指标"""
from typing import List, Optional, Tuple
from ..data.models import Kline


def is_engulfing_bar(current: Kline, previous: Kline) -> bool:
    """判断是否为外包线
    
    外包线定义：
    - 当前K线的最低价 < 上一根K线的最低价
    - 当前K线的最高价 > 上一根K线的最高价
    
    Args:
        current: 当前K线
        previous: 上一根K线
        
    Returns:
        是否为外包线
    """
    return (current.low < previous.low and 
            current.high > previous.high)


def is_bullish_engulfing(current: Kline, previous: Kline) -> bool:
    """判断是否为看涨外包线
    
    Args:
        current: 当前K线
        previous: 上一根K线
        
    Returns:
        是否为看涨外包线
    """
    return (is_engulfing_bar(current, previous) and 
            current.close > current.open and  # 当前为阳线
            previous.close < previous.open)   # 前一根为阴线


def is_bearish_engulfing(current: Kline, previous: Kline) -> bool:
    """判断是否为看跌外包线
    
    Args:
        current: 当前K线
        previous: 上一根K线
        
    Returns:
        是否为看跌外包线
    """
    return (is_engulfing_bar(current, previous) and 
            current.close < current.open and  # 当前为阴线
            previous.close > previous.open)   # 前一根为阳线


def get_engulfing_type(current: Kline, previous: Kline) -> str:
    """获取外包线类型
    
    Args:
        current: 当前K线
        previous: 上一根K线
        
    Returns:
        外包线类型：'看涨外包'/'看跌外包'/'普通外包'/'非外包'
    """
    if not is_engulfing_bar(current, previous):
        return '非外包'
    
    if is_bullish_engulfing(current, previous):
        return '看涨外包'
    elif is_bearish_engulfing(current, previous):
        return '看跌外包'
    else:
        return '普通外包'


def calculate_engulfing_strength(current: Kline, previous: Kline) -> float:
    """计算外包线的强度
    
    强度 = (当前K线实体 / 前一根K线实体) × (当前K线振幅 / 前一根K线振幅)
    
    Args:
        current: 当前K线
        previous: 上一根K线
        
    Returns:
        外包强度（>1表示强，>2表示非常强）
    """
    if not is_engulfing_bar(current, previous):
        return 0.0
    
    # 计算实体大小
    current_body = abs(current.close - current.open)
    previous_body = abs(previous.close - previous.open)
    
    # 计算振幅
    current_range = current.high - current.low
    previous_range = previous.high - previous.low
    
    if previous_body == 0 or previous_range == 0:
        return 1.0
    
    body_ratio = current_body / previous_body
    range_ratio = current_range / previous_range
    
    strength = body_ratio * range_ratio
    return strength


def calculate_wick_ratios(kline: Kline) -> Tuple[float, float]:
    """计算长上影线/下影线的比例（相对于整根K线振幅）
    
    返回 (upper_wick_ratio, lower_wick_ratio)
    """
    total_range = kline.high - kline.low
    if total_range <= 0:
        return 0.0, 0.0
    upper_body_top = max(kline.open, kline.close)
    lower_body_bottom = min(kline.open, kline.close)
    upper_wick = max(0.0, kline.high - upper_body_top)
    lower_wick = max(0.0, lower_body_bottom - kline.low)
    upper_ratio = upper_wick / total_range
    lower_ratio = lower_wick / total_range
    return float(upper_ratio), float(lower_ratio)

