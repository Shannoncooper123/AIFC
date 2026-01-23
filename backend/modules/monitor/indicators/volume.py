"""成交量指标计算"""
from typing import List, Optional


def calculate_volume_ma(volumes: List[float], period: int = 20) -> Optional[float]:
    """计算成交量移动平均
    
    Args:
        volumes: 成交量列表
        period: 周期
        
    Returns:
        成交量MA，数据不足返回None
    """
    if len(volumes) < period:
        return None
    
    recent_volumes = volumes[-period:]
    return sum(recent_volumes) / period


def calculate_volume_ratio(current_volume: float, volume_ma: float) -> float:
    """计算成交量比率
    
    Args:
        current_volume: 当前成交量
        volume_ma: 成交量移动平均
        
    Returns:
        成交量比率
    """
    if volume_ma == 0:
        return 1.0
    return current_volume / volume_ma


def calculate_obv(klines: List, start_idx: int = 0) -> List[float]:
    """计算OBV (On Balance Volume) 指标
    
    Args:
        klines: K线列表
        start_idx: 开始索引
        
    Returns:
        OBV值列表
    """
    if len(klines) < 2:
        return []
    
    obv_values = [0.0]
    
    for i in range(start_idx + 1, len(klines)):
        if klines[i].close > klines[i-1].close:
            obv_values.append(obv_values[-1] + klines[i].volume)
        elif klines[i].close < klines[i-1].close:
            obv_values.append(obv_values[-1] - klines[i].volume)
        else:
            obv_values.append(obv_values[-1])
    
    return obv_values


def is_volume_surge(current_volume: float, avg_volume: float, threshold: float = 2.0) -> bool:
    """判断是否成交量突增
    
    Args:
        current_volume: 当前成交量
        avg_volume: 平均成交量
        threshold: 阈值倍数
        
    Returns:
        是否突增
    """
    if avg_volume == 0:
        return False
    return current_volume >= avg_volume * threshold

