"""ATR (Average True Range) 指标计算
使用Wilder平滑方法，这是ATR的标准计算方式
"""
from typing import List, Optional
from ..data.models import Kline


def calculate_true_range(current: Kline, previous: Kline) -> float:
    """计算真实波幅（True Range）
    
    TR = max(
        当前最高价 - 当前最低价,
        |当前最高价 - 前收盘价|,
        |当前最低价 - 前收盘价|
    )
    
    Args:
        current: 当前K线
        previous: 前一根K线
        
    Returns:
        真实波幅值
    """
    tr1 = current.high - current.low
    tr2 = abs(current.high - previous.close)
    tr3 = abs(current.low - previous.close)
    return max(tr1, tr2, tr3)


def calculate_atr(klines: List[Kline], period: int = 14, use_wilder: bool = True) -> Optional[float]:
    """计算ATR指标
    
    使用Wilder平滑方法（推荐）：
    ATR_t = ATR_{t-1} * (period-1)/period + TR_t / period
    
    或使用简单移动平均（SMA）：
    ATR = SUM(TR, period) / period
    
    Args:
        klines: K线列表
        period: ATR周期
        use_wilder: 是否使用Wilder平滑（默认True，更响应市场变化）
        
    Returns:
        ATR值，数据不足返回None
    """
    if len(klines) < period + 1:
        return None
    
    trs = []
    for i in range(1, len(klines)):
        tr = calculate_true_range(klines[i], klines[i-1])
        trs.append(tr)
    
    if len(trs) < period:
        return None
    
    if use_wilder:
        atr = sum(trs[:period]) / period
        
        for i in range(period, len(trs)):
            atr = atr * (period - 1) / period + trs[i] / period
        
        return atr
    else:
        return sum(trs[-period:]) / period


def calculate_atr_list(klines: List[Kline], period: int = 14, use_wilder: bool = True) -> List[float]:
    """计算ATR序列（用于历史分析）
    
    使用Wilder平滑方法计算完整的ATR序列
    
    Args:
        klines: K线列表
        period: ATR周期
        use_wilder: 是否使用Wilder平滑（默认True）
        
    Returns:
        ATR值列表
    """
    if len(klines) < period + 1:
        return []
    
    trs = []
    for i in range(1, len(klines)):
        tr = calculate_true_range(klines[i], klines[i-1])
        trs.append(tr)
    
    if len(trs) < period:
        return []
    
    atr_values = []
    
    if use_wilder:
        atr = sum(trs[:period]) / period
        atr_values.append(atr)
        
        for i in range(period, len(trs)):
            atr = atr * (period - 1) / period + trs[i] / period
            atr_values.append(atr)
    else:
        for i in range(period, len(trs) + 1):
            atr = sum(trs[i-period:i]) / period
            atr_values.append(atr)
    
    return atr_values

