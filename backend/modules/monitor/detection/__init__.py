"""异常检测模块

双门槛检测机制：
- 核心组A（波动性）：ATR, PRICE, VOLUME, BB_WIDTH - 至少2个触发
- 核心组B（突破/动量）：BB_BREAKOUT, OI_SURGE, OI_ZSCORE, MA_DEVIATION - 至少1个触发
"""
from .detector import AnomalyDetector
from .strategy import DetectionStrategy
from .constants import (
    CORE_GROUP_A,
    CORE_GROUP_B,
    AUXILIARY,
    DEFAULT_THRESHOLDS,
    STRONG_THRESHOLDS,
)

__all__ = [
    'AnomalyDetector',
    'DetectionStrategy',
    'CORE_GROUP_A',
    'CORE_GROUP_B',
    'AUXILIARY',
    'DEFAULT_THRESHOLDS',
    'STRONG_THRESHOLDS',
]
