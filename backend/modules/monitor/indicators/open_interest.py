"""持仓量指标计算"""
from typing import List, Dict, Optional, Tuple
import statistics


def calculate_oi_change_rate(current_oi: float, previous_oi: float) -> float:
    """计算持仓量变化率
    
    Args:
        current_oi: 当前持仓量
        previous_oi: 前一个持仓量
        
    Returns:
        变化率（百分比）
    """
    if previous_oi == 0:
        return 0.0
    return ((current_oi - previous_oi) / previous_oi) * 100


def calculate_oi_value_change_rate(current_value: float, previous_value: float) -> float:
    """计算持仓量价值变化率
    
    Args:
        current_value: 当前持仓量价值
        previous_value: 前一个持仓量价值
        
    Returns:
        变化率（百分比）
    """
    if previous_value == 0:
        return 0.0
    return ((current_value - previous_value) / previous_value) * 100


def calculate_oi_zscore(oi_changes: List[float]) -> Optional[float]:
    """计算持仓量变化的Z-Score
    
    Args:
        oi_changes: 持仓量变化率列表
        
    Returns:
        Z-Score值，数据不足返回None
    """
    if len(oi_changes) < 2:
        return None
    
    mean = statistics.mean(oi_changes)
    
    try:
        stdev = statistics.stdev(oi_changes)
    except statistics.StatisticsError:
        return None
    
    if stdev == 0:
        return 0.0
    
    current_change = oi_changes[-1]
    return (current_change - mean) / stdev


def calculate_oi_ma(oi_values: List[float], period: int = 20) -> Optional[float]:
    """计算持仓量移动平均
    
    Args:
        oi_values: 持仓量列表
        period: 周期
        
    Returns:
        持仓量MA，数据不足返回None
    """
    if len(oi_values) < period:
        return None
    
    recent_oi = oi_values[-period:]
    return sum(recent_oi) / period


def analyze_oi_divergence(
    price_changes: List[float], 
    oi_changes: List[float], 
    window: int = 5,
    price_threshold: float = 0.5,
    oi_threshold: float = 1.0
) -> Tuple[bool, str]:
    """分析价格和持仓量的背离
    
    背离分析逻辑：
    1. 看涨背离（底部信号）：价格持续下跌但持仓量上升
       - 表示空头在加仓，但价格下跌动能减弱
       - 可能预示底部反转
    
    2. 看跌背离（顶部信号）：价格持续上涨但持仓量下降
       - 表示多头在减仓，上涨缺乏后续资金支撑
       - 可能预示顶部反转
    
    3. 增强信号：价格和持仓量同向变动
       - 价格涨+持仓涨：强势上涨，多头加仓
       - 价格跌+持仓跌：弱势下跌，多头平仓
    
    Args:
        price_changes: 价格变化率列表（百分比）
        oi_changes: 持仓量变化率列表（百分比）
        window: 分析窗口（最近N个数据点）
        price_threshold: 价格变化阈值（百分比，默认0.5%）
        oi_threshold: 持仓量变化阈值（百分比，默认1.0%）
        
    Returns:
        (是否背离, 背离类型)
        背离类型: "看涨背离"/"看跌背离"/"无背离"
    """
    if len(price_changes) < window or len(oi_changes) < window:
        return False, "无背离"
    
    recent_price = price_changes[-window:]
    recent_oi = oi_changes[-window:]
    
    avg_price_change = sum(recent_price) / window
    avg_oi_change = sum(recent_oi) / window
    
    price_trend_down = avg_price_change < -price_threshold
    price_trend_up = avg_price_change > price_threshold
    oi_increasing = avg_oi_change > oi_threshold
    oi_decreasing = avg_oi_change < -oi_threshold
    
    if price_trend_down and oi_increasing:
        return True, "看涨背离"
    
    if price_trend_up and oi_decreasing:
        return True, "看跌背离"
    
    return False, "无背离"


def detect_oi_surge(current_oi_change: float, oi_changes: List[float], 
                    threshold_zscore: float = 2.5) -> bool:
    """检测持仓量异常激增
    
    Args:
        current_oi_change: 当前持仓量变化率
        oi_changes: 历史持仓量变化率列表
        threshold_zscore: Z-Score阈值
        
    Returns:
        是否异常激增
    """
    if len(oi_changes) < 10:
        # 数据不足，使用简单阈值
        return abs(current_oi_change) > 5.0  # 5%变化视为异常
    
    zscore = calculate_oi_zscore(oi_changes)
    if zscore is None:
        return False
    
    return abs(zscore) > threshold_zscore


def parse_oi_hist_response(data: List[Dict]) -> Tuple[List[float], List[float], List[int]]:
    """解析持仓量历史数据响应
    
    Args:
        data: API返回的持仓量历史数据
        
    Returns:
        (持仓量列表, 持仓量价值列表, 时间戳列表)
    """
    oi_values = []
    oi_value_values = []
    timestamps = []
    
    for item in data:
        try:
            oi_values.append(float(item.get('sumOpenInterest', 0)))
            oi_value_values.append(float(item.get('sumOpenInterestValue', 0)))
            timestamps.append(int(item.get('timestamp', 0)))
        except (ValueError, TypeError):
            continue
    
    return oi_values, oi_value_values, timestamps


def calculate_oi_momentum(oi_values: List[float], period: int = 10) -> Optional[float]:
    """计算持仓量动量（类似价格动量）
    
    Args:
        oi_values: 持仓量列表
        period: 周期
        
    Returns:
        持仓量动量，数据不足返回None
    """
    if len(oi_values) < period + 1:
        return None
    
    current_oi = oi_values[-1]
    past_oi = oi_values[-(period + 1)]
    
    if past_oi == 0:
        return 0.0
    
    return ((current_oi - past_oi) / past_oi) * 100

