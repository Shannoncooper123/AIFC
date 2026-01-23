"""检测策略"""
from typing import Dict, List
from ..data.models import IndicatorValues


class DetectionStrategy:
    """检测策略基类"""
    
    def detect(self, indicators: IndicatorValues, config: Dict) -> tuple:
        """检测异常
        
        Args:
            indicators: 指标值
            config: 配置
            
        Returns:
            (是否异常, 触发的指标列表)
        """
        raise NotImplementedError


class MultiIndicatorStrategy(DetectionStrategy):
    """多指标组合策略"""
    
    def detect(self, indicators: IndicatorValues, config: Dict) -> tuple:
        """多指标组合检测
        
        Args:
            indicators: 指标值
            config: 配置
            
        Returns:
            (是否异常, 触发的指标列表)
        """
        thresholds = config['thresholds']
        triggered = []
        
        # ATR异常检测
        if indicators.atr_zscore > thresholds['atr_zscore']:
            triggered.append('ATR')
        
        # 价格变化率异常检测
        if abs(indicators.price_change_zscore) > thresholds['price_change_zscore']:
            triggered.append('PRICE')
        
        # 成交量异常检测
        if indicators.volume_zscore > thresholds['volume_zscore']:
            triggered.append('VOLUME')
        
        # 外包线检测
        if indicators.is_engulfing:
            triggered.append('ENGULFING')
        
        # --- 新增：RSI ---
        if indicators.is_rsi_overbought:
            triggered.append('RSI_OVERBOUGHT')
        if indicators.is_rsi_oversold:
            triggered.append('RSI_OVERSOLD')
        if abs(indicators.rsi_zscore) > thresholds.get('rsi_zscore', 2.0):
            triggered.append('RSI_ZSCORE')
        
        # --- 新增：布林带 ---
        if indicators.is_bb_breakout_upper:
            triggered.append('BB_BREAKOUT_UPPER')
        if indicators.is_bb_breakout_lower:
            triggered.append('BB_BREAKOUT_LOWER')
        if indicators.is_bb_squeeze and abs(indicators.price_change_zscore) > thresholds.get('bb_squeeze_price_zscore', 1.0):
            triggered.append('BB_SQUEEZE_EXPAND')
        if abs(indicators.bb_width_zscore) > thresholds.get('bb_width_zscore', 2.5):
            triggered.append('BB_WIDTH_ZSCORE')
        
        # --- 新增：均线 ---
        if indicators.is_ma_bullish_cross:
            triggered.append('MA_BULLISH_CROSS')
        if indicators.is_ma_bearish_cross:
            triggered.append('MA_BEARISH_CROSS')
        if abs(indicators.ma_deviation_zscore) > thresholds.get('ma_deviation_zscore', 2.0):
            triggered.append('MA_DEVIATION_ZSCORE')
        
        # --- 新增：长影线 ---
        if indicators.is_long_upper_wick and indicators.upper_wick_ratio >= thresholds.get('long_wick_ratio_threshold', 0.6):
            triggered.append('LONG_UPPER_WICK')
        if indicators.is_long_lower_wick and indicators.lower_wick_ratio >= thresholds.get('long_wick_ratio_threshold', 0.6):
            triggered.append('LONG_LOWER_WICK')
        
        # --- 新增：持仓量 ---
        if indicators.is_oi_surge:
            triggered.append('OI_SURGE')
        if abs(indicators.oi_zscore) > thresholds.get('oi_zscore', 2.5):
            triggered.append('OI_ZSCORE')
        if indicators.is_oi_divergence:
            if indicators.oi_divergence_type == "看涨背离":
                triggered.append('OI_BULLISH_DIVERGENCE')
            elif indicators.oi_divergence_type == "看跌背离":
                triggered.append('OI_BEARISH_DIVERGENCE')
        if abs(indicators.oi_momentum) > thresholds.get('oi_momentum_threshold', 10.0):
            triggered.append('OI_MOMENTUM')
        
        # 判断是否满足最小触发指标数
        min_triggered = thresholds['min_indicators_triggered']
        is_anomaly = len(triggered) >= min_triggered
        
        return is_anomaly, triggered


class AdaptiveThresholdStrategy(DetectionStrategy):
    """自适应阈值策略"""
    
    def __init__(self, base_threshold: float = 2.0, adjustment_factor: float = 0.1):
        """初始化
        
        Args:
            base_threshold: 基础阈值
            adjustment_factor: 调整因子
        """
        self.base_threshold = base_threshold
        self.adjustment_factor = adjustment_factor
        self.threshold_history: Dict[str, float] = {}
    
    def detect(self, indicators: IndicatorValues, config: Dict) -> tuple:
        """自适应阈值检测
        
        Args:
            indicators: 指标值
            config: 配置
            
        Returns:
            (是否异常, 触发的指标列表)
        """
        symbol = indicators.symbol
        
        # 获取或初始化阈值
        if symbol not in self.threshold_history:
            self.threshold_history[symbol] = self.base_threshold
        
        current_threshold = self.threshold_history[symbol]
        triggered = []
        
        # 检测各指标
        if indicators.atr_zscore > current_threshold:
            triggered.append('ATR')
        
        if abs(indicators.price_change_zscore) > current_threshold:
            triggered.append('PRICE')
        
        if indicators.volume_zscore > current_threshold:
            triggered.append('VOLUME')
        
        # 自适应调整阈值
        max_zscore = max(
            abs(indicators.atr_zscore),
            abs(indicators.price_change_zscore),
            abs(indicators.volume_zscore)
        )
        
        if max_zscore > current_threshold:
            # 降低阈值（变得更敏感）
            self.threshold_history[symbol] = max(
                self.base_threshold * 0.5,
                current_threshold - self.adjustment_factor
            )
        else:
            # 提高阈值（变得不那么敏感）
            self.threshold_history[symbol] = min(
                self.base_threshold * 1.5,
                current_threshold + self.adjustment_factor * 0.5
            )
        
        min_triggered = config['thresholds']['min_indicators_triggered']
        is_anomaly = len(triggered) >= min_triggered
        
        return is_anomaly, triggered

