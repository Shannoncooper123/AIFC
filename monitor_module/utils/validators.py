"""数据验证模块"""
from typing import Dict, Any, List


def validate_kline_data(data: Dict[str, Any]) -> bool:
    """验证K线数据格式
    
    Args:
        data: K线数据字典
        
    Returns:
        是否有效
    """
    required_fields = ['t', 'o', 'h', 'l', 'c', 'v', 'x']
    return all(field in data for field in required_fields)


def validate_symbol(symbol: str) -> bool:
    """验证交易对符号格式
    
    Args:
        symbol: 交易对符号
        
    Returns:
        是否有效
    """
    if not symbol or not isinstance(symbol, str):
        return False
    return len(symbol) >= 6 and symbol.isupper()


def validate_config_values(config: Dict[str, Any]) -> List[str]:
    """验证配置值的合理性
    
    Args:
        config: 配置字典
        
    Returns:
        错误信息列表（空列表表示验证通过）
    """
    errors = []
    
    # 验证K线配置
    if config['kline']['history_size'] < 10:
        errors.append("history_size 应该 >= 10")
    
    if config['kline']['warmup_size'] < config['kline']['history_size']:
        errors.append("warmup_size 应该 >= history_size")
    
    # 验证指标周期
    max_period = max(
        config['indicators']['atr_period'],
        config['indicators']['stddev_period'],
        config['indicators']['volume_ma_period']
    )
    
    if config['kline']['history_size'] < max_period:
        errors.append(f"history_size ({config['kline']['history_size']}) 应该 >= 最大指标周期 ({max_period})")
    
    # 验证阈值
    if config['thresholds']['min_indicators_triggered'] > 3:
        errors.append("min_indicators_triggered 最多为 3（ATR、价格变化、成交量）")
    
    return errors

