"""Z-Score计算"""
import numpy as np
from typing import List, Tuple, Optional


def calculate_mean_std(values: List[float]) -> Tuple[float, float]:
    """计算均值和标准差
    
    Args:
        values: 数值列表
        
    Returns:
        (均值, 标准差)
    """
    if not values:
        return 0.0, 0.0
    
    mean = float(np.mean(values))
    std = float(np.std(values))
    return mean, std


def calculate_zscore(value: float, historical_values: List[float]) -> float:
    """计算Z-Score
    
    Z-Score = (当前值 - 均值) / 标准差
    
    Args:
        value: 当前值
        historical_values: 历史值列表
        
    Returns:
        Z-Score值
    """
    if not historical_values:
        return 0.0
    
    mean, std = calculate_mean_std(historical_values)
    
    # 如果标准差为0，返回0
    if std == 0:
        return 0.0
    
    zscore = (value - mean) / std
    return float(zscore)


def is_outlier(zscore: float, threshold: float = 2.0) -> bool:
    """判断是否为异常值
    
    Args:
        zscore: Z-Score值
        threshold: 阈值（通常使用2.0或3.0）
        
    Returns:
        是否为异常值
    """
    return abs(zscore) > threshold


def calculate_modified_zscore(value: float, historical_values: List[float]) -> float:
    """计算修正Z-Score（基于中位数，更robust）
    
    Args:
        value: 当前值
        historical_values: 历史值列表
        
    Returns:
        修正Z-Score值
    """
    if not historical_values:
        return 0.0
    
    median = float(np.median(historical_values))
    mad = float(np.median([abs(v - median) for v in historical_values]))
    
    if mad == 0:
        return 0.0
    
    modified_zscore = 0.6745 * (value - median) / mad
    return float(modified_zscore)

