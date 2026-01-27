"""双门槛检测策略

采用双门槛机制进行异常检测：
1. 核心组A（波动性）：ATR, PRICE, VOLUME, BB_WIDTH - 至少2个触发
2. 核心组B（突破/动量）：BB_BREAKOUT, OI_SURGE, OI_ZSCORE, MA_DEVIATION - 至少1个触发
3. 两组都满足才触发告警，辅助指标用于计算异常等级
"""
from typing import Dict, List, Tuple
from ..data.models import IndicatorValues
from .constants import DEFAULT_THRESHOLDS


class DetectionStrategy:
    """双门槛检测策略"""
    
    def __init__(self, config: Dict):
        """初始化策略
        
        Args:
            config: 配置字典，可包含 detection.thresholds 覆盖默认阈值
        """
        detection_config = config.get('detection', {})
        config_thresholds = detection_config.get('thresholds', {})
        self.thresholds = {**DEFAULT_THRESHOLDS, **config_thresholds}
    
    def detect(self, indicators: IndicatorValues) -> Tuple[bool, List[str]]:
        """执行异常检测
        
        Args:
            indicators: 技术指标值
            
        Returns:
            (是否异常, 触发的指标列表)
        """
        group_a = self._check_group_a(indicators)
        group_b = self._check_group_b(indicators)
        
        min_a = int(self.thresholds['min_group_a'])
        min_b = int(self.thresholds['min_group_b'])
        
        if len(group_a) < min_a or len(group_b) < min_b:
            return False, []
        
        auxiliary = self._check_auxiliary(indicators)
        
        return True, group_a + group_b + auxiliary
    
    def _check_group_a(self, ind: IndicatorValues) -> List[str]:
        """检查核心组A：波动性指标
        
        Args:
            ind: 技术指标值
            
        Returns:
            触发的指标列表
        """
        triggered = []
        
        if abs(ind.atr_zscore) > self.thresholds['atr_zscore']:
            triggered.append('ATR')
        
        if abs(ind.price_change_zscore) > self.thresholds['price_zscore']:
            triggered.append('PRICE')
        
        if ind.volume_zscore > self.thresholds['volume_zscore']:
            triggered.append('VOLUME')
        
        if abs(ind.bb_width_zscore) > self.thresholds['bb_width_zscore']:
            triggered.append('BB_WIDTH')
        
        return triggered
    
    def _check_group_b(self, ind: IndicatorValues) -> List[str]:
        """检查核心组B：突破/动量指标
        
        Args:
            ind: 技术指标值
            
        Returns:
            触发的指标列表
        """
        triggered = []
        
        if ind.is_bb_breakout_upper or ind.is_bb_breakout_lower:
            triggered.append('BB_BREAKOUT')
        
        if ind.is_oi_surge:
            triggered.append('OI_SURGE')
        
        if abs(ind.oi_zscore) > self.thresholds['oi_zscore']:
            triggered.append('OI_ZSCORE')
        
        if abs(ind.ma_deviation_zscore) > self.thresholds['ma_deviation_zscore']:
            triggered.append('MA_DEVIATION')
        
        return triggered
    
    def _check_auxiliary(self, ind: IndicatorValues) -> List[str]:
        """检查辅助指标（用于计算异常等级）
        
        Args:
            ind: 技术指标值
            
        Returns:
            触发的指标列表
        """
        triggered = []
        
        if ind.is_rsi_overbought:
            triggered.append('RSI_OVERBOUGHT')
        if ind.is_rsi_oversold:
            triggered.append('RSI_OVERSOLD')
        
        if ind.is_ma_bullish_cross:
            triggered.append('MA_BULLISH_CROSS')
        if ind.is_ma_bearish_cross:
            triggered.append('MA_BEARISH_CROSS')
        
        if ind.is_engulfing:
            triggered.append('ENGULFING')
        if ind.is_long_upper_wick:
            triggered.append('LONG_UPPER_WICK')
        if ind.is_long_lower_wick:
            triggered.append('LONG_LOWER_WICK')
        
        if ind.is_oi_divergence:
            triggered.append('OI_DIVERGENCE')
        
        if ind.is_bb_squeeze:
            triggered.append('BB_SQUEEZE')
        
        return triggered
