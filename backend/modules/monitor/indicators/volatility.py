"""波动率指标计算"""
import numpy as np
from typing import List, Optional
from ..data.models import Kline


def calculate_std_dev(values: List[float], period: int = 20) -> Optional[float]:
    """计算标准差
    
    Args:
        values: 数值列表
        period: 周期
        
    Returns:
        标准差，数据不足返回None
    """
    if len(values) < period:
        return None
    
    recent_values = values[-period:]
    return float(np.std(recent_values))


def calculate_price_change_rate(kline: Kline) -> float:
    """计算单根K线的价格变化率
    
    Args:
        kline: K线数据
        
    Returns:
        价格变化率（百分比，如0.05表示5%）
    """
    if kline.open == 0:
        return 0.0
    return (kline.close - kline.open) / kline.open


def calculate_historical_volatility(closes: List[float], period: int = 20) -> Optional[float]:
    """计算历史波动率
    
    Args:
        closes: 收盘价列表
        period: 周期
        
    Returns:
        历史波动率，数据不足返回None
    """
    if len(closes) < period + 1:
        return None
    
    # 计算收益率
    returns = []
    for i in range(1, len(closes)):
        if closes[i-1] != 0:
            ret = (closes[i] - closes[i-1]) / closes[i-1]
            returns.append(ret)
    
    if len(returns) < period:
        return None
    
    # 计算收益率的标准差
    recent_returns = returns[-period:]
    return float(np.std(recent_returns))


def calculate_bollinger_bands(closes: List[float], period: int = 20, std_multiplier: float = 2.0) -> Optional[tuple]:
    """计算布林带
    
    Args:
        closes: 收盘价列表
        period: 周期
        std_multiplier: 标准差倍数
        
    Returns:
        (上轨, 中轨, 下轨)，数据不足返回None
    """
    if len(closes) < period:
        return None
    
    recent_closes = closes[-period:]
    middle = np.mean(recent_closes)
    std = np.std(recent_closes)
    
    upper = middle + std_multiplier * std
    lower = middle - std_multiplier * std
    
    return (float(upper), float(middle), float(lower))


def calculate_bollinger_bandwidth(closes: List[float], period: int = 20, std_multiplier: float = 2.0) -> Optional[float]:
    """计算布林带带宽
    
    带宽 = (上轨 - 下轨) / 中轨（若中轨为0，则返回上轨-下轨）
    
    Args:
        closes: 收盘价列表
        period: 周期
        std_multiplier: 标准差倍数
        
    Returns:
        布林带带宽，数据不足返回None
    """
    bands = calculate_bollinger_bands(closes, period, std_multiplier)
    if bands is None:
        return None
    upper, middle, lower = bands
    width = (upper - lower)
    if middle != 0:
        width = width / middle
    return float(width)


def calculate_sma(values: List[float], period: int) -> Optional[float]:
    """计算简单移动平均（SMA）"""
    if len(values) < period:
        return None
    return float(np.mean(values[-period:]))


def calculate_ema_list(values: List[float], period: int) -> List[float]:
    """计算EMA序列（用于检测金叉/死叉）
    
    使用Wilder平滑：EMA_t = value_t * k + EMA_{t-1} * (1-k)，其中k = 2/(period+1)
    """
    if not values:
        return []
    k = 2 / (period + 1)
    ema_values: List[float] = []
    for i, v in enumerate(values):
        if i == 0:
            ema_values.append(float(v))
        else:
            ema_values.append(float(v * k + ema_values[-1] * (1 - k)))
    return ema_values


def calculate_rsi(closes: List[float], period: int = 14) -> Optional[float]:
    """计算RSI（相对强弱指标）
    
    使用Wilder平滑的RSI计算。
    """
    rsi_list = calculate_rsi_list(closes, period)
    if not rsi_list:
        return None
    return float(rsi_list[-1])


def calculate_rsi_list(closes: List[float], period: int = 14) -> List[float]:
    """计算RSI序列（用于Z-Score与趋势判断）"""
    if len(closes) < period + 1:
        return []
    # 计算每步涨跌幅
    changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [max(c, 0.0) for c in changes]
    losses = [abs(min(c, 0.0)) for c in changes]
    
    # 初始化平均涨跌
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    
    rsi_values: List[float] = []
    # 从第 period+1 根开始滚动计算
    for i in range(period, len(gains)):
        # Wilder平滑
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))
        rsi_values.append(float(rsi))
    return rsi_values


def calculate_macd_list(closes: List[float], fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> tuple[List[float], List[float], List[float]]:
    """计算MACD完整指标序列（DIF、Signal、Histogram）
    
    MACD（Moving Average Convergence Divergence）是一个趋势跟踪动量指标。
    本函数返回MACD的三个组成部分：
    - MACD线（DIF）：快速EMA与慢速EMA的差值
    - 信号线（Signal/DEA）：MACD线的EMA平滑
    - 柱状图（Histogram）：MACD线与信号线的差值
    
    Args:
        closes: 收盘价列表
        fast_period: 快线周期（默认12）
        slow_period: 慢线周期（默认26）
        signal_period: 信号线周期（默认9）
        
    Returns:
        (macd_line, signal_line, histogram) 三个列表的元组
        - macd_line (DIF): 快线EMA - 慢线EMA
        - signal_line (DEA): MACD线的EMA平滑
        - histogram (MACD柱): MACD线 - 信号线
    """
    if len(closes) < slow_period:
        return [], [], []
    
    # 计算快慢EMA
    ema_fast = calculate_ema_list(closes, fast_period)
    ema_slow = calculate_ema_list(closes, slow_period)
    
    # 计算MACD线（DIF）= 快线 - 慢线
    macd_line: List[float] = []
    for i in range(len(closes)):
        if i < len(ema_fast) and i < len(ema_slow):
            macd = ema_fast[i] - ema_slow[i]
            macd_line.append(float(macd))
    
    # 计算信号线（Signal/DEA）= MACD线的EMA
    signal_line = calculate_ema_list(macd_line, signal_period)
    
    # 计算柱状图（Histogram）= MACD线 - 信号线
    histogram: List[float] = []
    for i in range(len(macd_line)):
        if i < len(signal_line):
            hist = macd_line[i] - signal_line[i]
            histogram.append(float(hist))
        else:
            histogram.append(0.0)
    
    return macd_line, signal_line, histogram