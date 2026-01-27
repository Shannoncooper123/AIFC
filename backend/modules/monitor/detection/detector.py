"""异常检测器

基于双门槛机制进行异常检测：
- 核心组A（波动性）+ 核心组B（突破/动量）双重确认
- 辅助指标用于计算异常等级
"""
from typing import Dict, List, Optional
import time
from ..data.models import IndicatorValues, AnomalyResult
from .strategy import DetectionStrategy
from .constants import CORE_GROUP_A, CORE_GROUP_B, STRONG_THRESHOLDS


class AnomalyDetector:
    """异常检测器"""
    
    def __init__(self, config: Dict):
        """初始化
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.strategy = DetectionStrategy(config)
    
    def detect(self, indicators: IndicatorValues) -> Optional[AnomalyResult]:
        """检测异常
        
        Args:
            indicators: 技术指标值
            
        Returns:
            异常结果，如果没有异常返回None
        """
        if indicators is None:
            return None
        
        is_anomaly, triggered_indicators = self.strategy.detect(indicators)
        
        if not is_anomaly:
            return None
        
        anomaly_level = self._calculate_level(indicators, triggered_indicators)
        
        return AnomalyResult(
            symbol=indicators.symbol,
            timestamp=int(time.time() * 1000),
            price=0.0,
            price_change_rate=indicators.price_change_rate,
            atr_zscore=indicators.atr_zscore,
            price_change_zscore=indicators.price_change_zscore,
            volume_zscore=indicators.volume_zscore,
            anomaly_level=anomaly_level,
            triggered_indicators=triggered_indicators,
            engulfing_type=indicators.engulfing_type
        )
    
    def _calculate_level(self, ind: IndicatorValues, triggered: List[str]) -> int:
        """计算异常等级（1-5星）
        
        基于核心指标强度 + 核心组B数量 + 辅助指标数量综合计算
        
        Args:
            ind: 技术指标值
            triggered: 触发的指标列表
            
        Returns:
            异常等级（1-5）
        """
        score = 0
        
        # 核心组A强度评分（每个指标最多2分）
        if abs(ind.atr_zscore) > STRONG_THRESHOLDS['atr_zscore']:
            score += 2
        elif abs(ind.atr_zscore) > self.strategy.thresholds['atr_zscore']:
            score += 1
        
        if abs(ind.price_change_zscore) > STRONG_THRESHOLDS['price_zscore']:
            score += 2
        elif abs(ind.price_change_zscore) > self.strategy.thresholds['price_zscore']:
            score += 1
        
        if ind.volume_zscore > STRONG_THRESHOLDS['volume_zscore']:
            score += 2
        elif ind.volume_zscore > self.strategy.thresholds['volume_zscore']:
            score += 1
        
        if abs(ind.bb_width_zscore) > STRONG_THRESHOLDS['bb_width_zscore']:
            score += 2
        elif abs(ind.bb_width_zscore) > self.strategy.thresholds['bb_width_zscore']:
            score += 1
        
        # 核心组B数量评分（每个指标2分）
        group_b_count = len([t for t in triggered if t in CORE_GROUP_B])
        score += group_b_count * 2
        
        # 辅助指标数量评分（每个指标1分）
        aux_count = len([t for t in triggered 
                        if t not in CORE_GROUP_A and t not in CORE_GROUP_B])
        score += aux_count
        
        # 根据总分计算等级
        if score >= 12:
            return 5
        elif score >= 9:
            return 4
        elif score >= 6:
            return 3
        elif score >= 3:
            return 2
        else:
            return 1
