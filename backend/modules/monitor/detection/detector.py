"""异常检测器"""
from typing import Dict, Optional
import time
from ..data.models import IndicatorValues, AnomalyResult
from .strategies import MultiIndicatorStrategy, DetectionStrategy


class AnomalyDetector:
    """异常检测器"""
    
    def __init__(self, config: Dict, strategy: Optional[DetectionStrategy] = None):
        """初始化
        
        Args:
            config: 配置字典
            strategy: 检测策略（默认使用多指标组合策略）
        """
        self.config = config
        self.strategy = strategy or MultiIndicatorStrategy()
    
    def detect(self, indicators: IndicatorValues) -> Optional[AnomalyResult]:
        """检测异常
        
        Args:
            indicators: 技术指标值
            
        Returns:
            异常结果，如果没有异常返回None
        """
        if indicators is None:
            return None
        
        # 使用策略检测异常
        is_anomaly, triggered_indicators = self.strategy.detect(indicators, self.config)
        
        if not is_anomaly:
            return None
        
        # 计算异常等级（1-5星）
        anomaly_level = self.calculate_anomaly_level(indicators)
        
        # 获取当前价格
        from ..data.kline_manager import KlineManager
        # 这里我们从indicators中获取价格信息
        # 实际使用时需要从kline_manager获取最新价格
        
        return AnomalyResult(
            symbol=indicators.symbol,
            timestamp=int(time.time() * 1000),
            price=0.0,  # 需要从外部传入
            price_change_rate=indicators.price_change_rate,
            atr_zscore=indicators.atr_zscore,
            price_change_zscore=indicators.price_change_zscore,
            volume_zscore=indicators.volume_zscore,
            anomaly_level=anomaly_level,
            triggered_indicators=triggered_indicators,
            engulfing_type=indicators.engulfing_type
        )
    
    def calculate_anomaly_level(self, indicators: IndicatorValues) -> int:
        """计算异常等级（1-5星）
        
        Args:
            indicators: 技术指标值
            
        Returns:
            异常等级（1-5）
        """
        # 计算综合Z-Score
        zscores = [
            abs(indicators.atr_zscore),
            abs(indicators.price_change_zscore),
            abs(indicators.volume_zscore)
        ]
        
        max_zscore = max(zscores)
        avg_zscore = sum(zscores) / len(zscores)
        
        # 根据Z-Score计算等级
        if max_zscore > 5.0 or avg_zscore > 4.0:
            return 5
        elif max_zscore > 4.0 or avg_zscore > 3.5:
            return 4
        elif max_zscore > 3.5 or avg_zscore > 3.0:
            return 3
        elif max_zscore > 3.0 or avg_zscore > 2.5:
            return 2
        else:
            return 1

