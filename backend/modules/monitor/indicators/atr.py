"""ATR (Average True Range) 指标计算"""
from typing import List, Optional
from ..data.models import Kline


def calculate_true_range(current: Kline, previous: Kline) -> float:
    """计算真实波幅（True Range）
    
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


def calculate_atr(klines: List[Kline], period: int = 14) -> Optional[float]:
    """计算ATR指标
    
    Args:
        klines: K线列表
        period: ATR周期
        
    Returns:
        ATR值，数据不足返回None
    """
    if len(klines) < period + 1:
        return None
    
    # 计算True Range
    trs = []
    for i in range(1, len(klines)):
        tr = calculate_true_range(klines[i], klines[i-1])
        trs.append(tr)
    
    # 计算ATR（最近period个TR的平均值）
    if len(trs) < period:
        return None
    
    atr = sum(trs[-period:]) / period
    return atr


def calculate_atr_list(klines: List[Kline], period: int = 14) -> List[float]:
    """计算ATR序列（用于历史分析）
    
    Args:
        klines: K线列表
        period: ATR周期
        
    Returns:
        ATR值列表
    """
    if len(klines) < period + 1:
        return []
    
    atr_values = []
    trs = []
    
    # 计算所有TR
    for i in range(1, len(klines)):
        tr = calculate_true_range(klines[i], klines[i-1])
        trs.append(tr)
        
        # 当有足够的TR时，计算ATR
        if len(trs) >= period:
            atr = sum(trs[-period:]) / period
            atr_values.append(atr)
    
    return atr_values

