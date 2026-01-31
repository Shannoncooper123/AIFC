"""辅助函数模块"""
import time
from datetime import datetime
from typing import Optional, Callable, Any
from functools import wraps


def timestamp_to_datetime(timestamp: int) -> str:
    """将时间戳转换为可读的日期时间字符串
    
    Args:
        timestamp: 毫秒级时间戳
        
    Returns:
        格式化的日期时间字符串
    """
    return datetime.fromtimestamp(timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S')


def format_price(price: float) -> str:
    """格式化价格（自动选择合适的小数位数）
    
    Args:
        price: 价格
        
    Returns:
        格式化的价格字符串
    """
    if price == 0:
        return "$0"
    
    # 根据价格大小自动选择小数位数
    if price >= 1000:
        # 大于1000：保留2位小数
        return f"${price:,.2f}"
    elif price >= 1:
        # 1-1000：保留4位小数
        return f"${price:.4f}"
    elif price >= 0.01:
        # 0.01-1：保留6位小数
        return f"${price:.6f}"
    else:
        # 小于0.01：保留8位小数
        return f"${price:.8f}"


def format_percentage(value: float, decimals: int = 2) -> str:
    """格式化百分比
    
    Args:
        value: 数值（如0.05表示5%）
        decimals: 小数位数
        
    Returns:
        格式化的百分比字符串
    """
    sign = '+' if value > 0 else ''
    return f"{sign}{value * 100:.{decimals}f}%"


def format_volume(volume: float) -> str:
    """格式化成交量
    
    Args:
        volume: 成交量
        
    Returns:
        格式化的成交量字符串
    """
    if volume >= 1_000_000:
        return f"{volume / 1_000_000:.2f}M"
    elif volume >= 1_000:
        return f"{volume / 1_000:.2f}K"
    return f"{volume:.2f}"


def retry_on_exception(max_retries: int = 5, delay: float = 1.0, exceptions: tuple = (Exception,)):
    """异常重试装饰器（使用指数退避法，支持429限流特殊处理）
    
    Args:
        max_retries: 最大重试次数（默认5次）
        delay: 基础重试延迟（秒），实际延迟为 delay * (2 ** attempt)
        exceptions: 需要重试的异常类型
        
    Returns:
        装饰器函数
        
    Note:
        使用指数退避策略：
        - 第1次重试：delay * 2^0 = delay 秒
        - 第2次重试：delay * 2^1 = delay * 2 秒
        - 第3次重试：delay * 2^2 = delay * 4 秒
        - 第4次重试：delay * 2^3 = delay * 8 秒
        - 第5次重试：delay * 2^4 = delay * 16 秒
        
        对于429限流错误，会使用更长的等待时间（基础30秒 + 指数退避）
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        backoff_time = _calculate_backoff(e, attempt, delay)
                        time.sleep(backoff_time)
                    continue
            raise last_exception
        return wrapper
    return decorator


def _calculate_backoff(exception: Exception, attempt: int, base_delay: float) -> float:
    """计算退避时间
    
    对于429限流错误使用更长的等待时间。
    
    Args:
        exception: 异常对象
        attempt: 当前重试次数（从0开始）
        base_delay: 基础延迟时间
    
    Returns:
        退避等待时间（秒）
    """
    is_rate_limit = False
    retry_after = None
    
    error_str = str(exception).lower()
    if '429' in error_str or 'too many requests' in error_str or 'rate limit' in error_str:
        is_rate_limit = True
    
    if hasattr(exception, 'response') and exception.response is not None:
        response = exception.response
        if hasattr(response, 'status_code') and response.status_code == 429:
            is_rate_limit = True
        if hasattr(response, 'headers'):
            retry_after_header = response.headers.get('Retry-After')
            if retry_after_header:
                try:
                    retry_after = int(retry_after_header)
                except ValueError:
                    pass
    
    if is_rate_limit:
        if retry_after:
            backoff_time = retry_after + (attempt * 5)
        else:
            backoff_time = 30 + (attempt * 15)
        return backoff_time
    
    return base_delay * (2 ** attempt)


def get_binance_kline_url(symbol: str, interval: str = '1m') -> str:
    """生成币安K线图表链接
    
    Args:
        symbol: 交易对符号
        interval: K线间隔
        
    Returns:
        币安图表URL
    """
    return f"https://www.binance.com/zh-CN/futures/{symbol}"


def safe_float(value: Any, default: float = 0.0) -> float:
    """安全转换为浮点数
    
    Args:
        value: 待转换的值
        default: 默认值
        
    Returns:
        浮点数
    """
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def get_anomaly_stars(level: int) -> str:
    """获取异常等级的星级表示
    
    Args:
        level: 异常等级（1-5）
        
    Returns:
        星级字符串
    """
    return '⭐' * min(max(level, 1), 5)

