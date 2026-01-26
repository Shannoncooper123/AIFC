"""K线形态指标"""
from typing import List, Optional, Tuple
from ..data.models import Kline


def is_engulfing_bar(current: Kline, previous: Kline, require_body_engulf: bool = False) -> bool:
    """判断是否为外包线
    
    外包线定义（标准模式）：
    - 当前K线的最低价 < 上一根K线的最低价
    - 当前K线的最高价 > 上一根K线的最高价
    
    外包线定义（严格模式，require_body_engulf=True）：
    - 满足标准模式条件
    - 当前K线实体完全包裹前一根K线实体
    
    Args:
        current: 当前K线
        previous: 上一根K线
        require_body_engulf: 是否要求实体吞没（更严格的判定）
        
    Returns:
        是否为外包线
    """
    range_engulf = (current.low < previous.low and current.high > previous.high)
    
    if not range_engulf:
        return False
    
    if require_body_engulf:
        current_body_high = max(current.open, current.close)
        current_body_low = min(current.open, current.close)
        previous_body_high = max(previous.open, previous.close)
        previous_body_low = min(previous.open, previous.close)
        
        body_engulf = (current_body_high >= previous_body_high and 
                       current_body_low <= previous_body_low)
        return body_engulf
    
    return True


def is_bullish_engulfing(current: Kline, previous: Kline, strict: bool = True) -> bool:
    """判断是否为看涨外包线
    
    看涨外包线条件：
    1. 满足外包线条件
    2. 当前K线为阳线（收盘 > 开盘）
    3. 前一根K线为阴线（收盘 < 开盘）
    4. 严格模式下：当前阳线实体 > 前一根阴线实体
    
    Args:
        current: 当前K线
        previous: 上一根K线
        strict: 是否使用严格模式（要求实体吞没）
        
    Returns:
        是否为看涨外包线
    """
    if not is_engulfing_bar(current, previous, require_body_engulf=strict):
        return False
    
    is_current_bullish = current.close > current.open
    is_previous_bearish = previous.close < previous.open
    
    if not (is_current_bullish and is_previous_bearish):
        return False
    
    if strict:
        current_body = abs(current.close - current.open)
        previous_body = abs(previous.close - previous.open)
        return current_body > previous_body
    
    return True


def is_bearish_engulfing(current: Kline, previous: Kline, strict: bool = True) -> bool:
    """判断是否为看跌外包线
    
    看跌外包线条件：
    1. 满足外包线条件
    2. 当前K线为阴线（收盘 < 开盘）
    3. 前一根K线为阳线（收盘 > 开盘）
    4. 严格模式下：当前阴线实体 > 前一根阳线实体
    
    Args:
        current: 当前K线
        previous: 上一根K线
        strict: 是否使用严格模式（要求实体吞没）
        
    Returns:
        是否为看跌外包线
    """
    if not is_engulfing_bar(current, previous, require_body_engulf=strict):
        return False
    
    is_current_bearish = current.close < current.open
    is_previous_bullish = previous.close > previous.open
    
    if not (is_current_bearish and is_previous_bullish):
        return False
    
    if strict:
        current_body = abs(current.close - current.open)
        previous_body = abs(previous.close - previous.open)
        return current_body > previous_body
    
    return True


def get_engulfing_type(current: Kline, previous: Kline, strict: bool = True) -> str:
    """获取外包线类型
    
    Args:
        current: 当前K线
        previous: 上一根K线
        strict: 是否使用严格模式（要求实体吞没）
        
    Returns:
        外包线类型：'看涨外包'/'看跌外包'/'普通外包'/'非外包'
    """
    if not is_engulfing_bar(current, previous, require_body_engulf=False):
        return '非外包'
    
    if is_bullish_engulfing(current, previous, strict=strict):
        return '看涨外包'
    elif is_bearish_engulfing(current, previous, strict=strict):
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

