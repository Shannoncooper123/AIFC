"""指标分组常量定义

异常检测采用双门槛机制：
- 核心组A（波动性）：ATR, PRICE, VOLUME, BB_WIDTH - 至少2个触发
- 核心组B（突破/动量）：BB_BREAKOUT, OI_SURGE, OI_ZSCORE, MA_DEVIATION - 至少1个触发
- 辅助指标：用于计算异常等级，不参与门槛判断
"""
from typing import FrozenSet, Dict

# 核心组A：波动性指标
CORE_GROUP_A: FrozenSet[str] = frozenset(['ATR', 'PRICE', 'VOLUME', 'BB_WIDTH'])

# 核心组B：突破/动量指标
CORE_GROUP_B: FrozenSet[str] = frozenset(['BB_BREAKOUT', 'OI_SURGE', 'OI_ZSCORE', 'MA_DEVIATION'])

# 辅助指标
AUXILIARY: FrozenSet[str] = frozenset([
    'RSI_OVERBOUGHT', 'RSI_OVERSOLD',
    'MA_BULLISH_CROSS', 'MA_BEARISH_CROSS',
    'ENGULFING', 'LONG_UPPER_WICK', 'LONG_LOWER_WICK',
    'OI_DIVERGENCE', 'BB_SQUEEZE'
])

# 默认阈值（代码内置，config可覆盖）
DEFAULT_THRESHOLDS: Dict[str, float] = {
    # 核心组A阈值
    'atr_zscore': 3.0,
    'price_zscore': 3.0,
    'volume_zscore': 3.5,
    'bb_width_zscore': 3.0,
    # 核心组B阈值
    'oi_zscore': 2.5,
    'ma_deviation_zscore': 2.5,
    # 门槛规则
    'min_group_a': 2,
    'min_group_b': 1,
}

# 异常等级计算的强触发阈值
STRONG_THRESHOLDS: Dict[str, float] = {
    'atr_zscore': 4.0,
    'price_zscore': 4.0,
    'volume_zscore': 4.5,
    'bb_width_zscore': 4.0,
}
