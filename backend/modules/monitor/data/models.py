"""数据模型定义"""
from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class Kline:
    """K线数据模型"""
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_closed: bool
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Kline':
        """从字典创建K线对象（WebSocket格式）
        
        Args:
            data: K线数据字典
            
        Returns:
            Kline对象
        """
        return cls(
            timestamp=int(data['t']),
            open=float(data['o']),
            high=float(data['h']),
            low=float(data['l']),
            close=float(data['c']),
            volume=float(data['v']),
            is_closed=bool(data['x'])
        )
    
    @classmethod
    def from_rest_api(cls, data: List) -> 'Kline':
        """从REST API响应创建K线对象
        
        Args:
            data: REST API返回的K线数据数组
            
        Returns:
            Kline对象
        """
        return cls(
            timestamp=int(data[0]),
            open=float(data[1]),
            high=float(data[2]),
            low=float(data[3]),
            close=float(data[4]),
            volume=float(data[5]),
            is_closed=True
        )


@dataclass
class AnomalyResult:
    """异常检测结果"""
    symbol: str
    timestamp: int
    price: float
    price_change_rate: float
    atr_zscore: float
    price_change_zscore: float
    volume_zscore: float
    anomaly_level: int
    triggered_indicators: List[str]
    engulfing_type: str = '非外包'
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp,
            'price': self.price,
            'price_change_rate': self.price_change_rate,
            'atr_zscore': self.atr_zscore,
            'price_change_zscore': self.price_change_zscore,
            'volume_zscore': self.volume_zscore,
            'anomaly_level': self.anomaly_level,
            'triggered_indicators': self.triggered_indicators,
            'engulfing_type': self.engulfing_type,
        }


@dataclass
class IndicatorValues:
    """技术指标值"""
    symbol: str
    atr: float
    atr_zscore: float
    price_change_rate: float
    price_change_zscore: float
    volume: float
    volume_ma: float
    volume_zscore: float
    stddev: float
    is_engulfing: bool
    engulfing_type: str
    rsi: float = 0.0
    rsi_zscore: float = 0.0
    is_rsi_overbought: bool = False
    is_rsi_oversold: bool = False
    ema_fast: float = 0.0
    ema_slow: float = 0.0
    is_ma_bullish_cross: bool = False
    is_ma_bearish_cross: bool = False
    ma_deviation: float = 0.0
    ma_deviation_zscore: float = 0.0
    bb_upper: float = 0.0
    bb_middle: float = 0.0
    bb_lower: float = 0.0
    bb_width: float = 0.0
    bb_width_zscore: float = 0.0
    is_bb_breakout_upper: bool = False
    is_bb_breakout_lower: bool = False
    is_bb_squeeze: bool = False
    upper_wick_ratio: float = 0.0
    lower_wick_ratio: float = 0.0
    is_long_upper_wick: bool = False
    is_long_lower_wick: bool = False
    open_interest: float = 0.0
    open_interest_value: float = 0.0
    oi_change_rate: float = 0.0
    oi_value_change_rate: float = 0.0
    oi_zscore: float = 0.0
    oi_ma: float = 0.0
    oi_momentum: float = 0.0
    is_oi_divergence: bool = False
    oi_divergence_type: str = "无背离"
    is_oi_surge: bool = False
