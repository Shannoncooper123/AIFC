"""常量模块 - 集中管理所有硬编码常量，遵循 Single Source of Truth 原则"""

from .intervals import VALID_INTERVALS, INTRADAY_INTERVALS
from .indicators import INDICATOR_NAMES
from .defaults import (
    DEFAULT_LEVERAGE,
    DEFAULT_TAKER_FEE_RATE,
    DEFAULT_MAKER_FEE_RATE,
)

__all__ = [
    'VALID_INTERVALS',
    'INTRADAY_INTERVALS',
    'INDICATOR_NAMES',
    'DEFAULT_LEVERAGE',
    'DEFAULT_TAKER_FEE_RATE',
    'DEFAULT_MAKER_FEE_RATE',
]
