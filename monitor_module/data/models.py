"""数据模型定义"""
from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class Kline:
    """K线数据模型"""
    timestamp: int          # 时间戳（毫秒）
    open: float            # 开盘价
    high: float            # 最高价
    low: float             # 最低价
    close: float           # 收盘价
    volume: float          # 成交量
    is_closed: bool        # 是否已完结
    
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
            is_closed=True  # REST API返回的都是已完结的K线
        )


@dataclass
class AnomalyResult:
    """异常检测结果"""
    symbol: str                      # 交易对符号
    timestamp: int                   # 检测时间戳
    price: float                     # 当前价格
    price_change_rate: float         # 价格变化率
    atr_zscore: float               # ATR Z-Score
    price_change_zscore: float      # 价格变化 Z-Score
    volume_zscore: float            # 成交量 Z-Score
    anomaly_level: int              # 异常等级（1-5星）
    triggered_indicators: List[str] # 触发的指标列表
    engulfing_type: str = '非外包'  # 外包线类型
    
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
    atr: float                      # ATR值
    atr_zscore: float              # ATR Z-Score
    price_change_rate: float        # 价格变化率
    price_change_zscore: float     # 价格变化 Z-Score
    volume: float                   # 当前成交量
    volume_ma: float               # 成交量移动平均
    volume_zscore: float           # 成交量 Z-Score
    stddev: float                  # 标准差
    is_engulfing: bool             # 是否为外包线
    engulfing_type: str            # 外包线类型
    # 下面是优先级A新增字段
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
    # 持仓量相关字段
    open_interest: float = 0.0                    # 当前持仓量
    open_interest_value: float = 0.0              # 当前持仓量价值
    oi_change_rate: float = 0.0                   # 持仓量变化率
    oi_value_change_rate: float = 0.0             # 持仓量价值变化率
    oi_zscore: float = 0.0                        # 持仓量变化Z-Score
    oi_ma: float = 0.0                            # 持仓量移动平均
    oi_momentum: float = 0.0                      # 持仓量动量
    is_oi_divergence: bool = False                # 是否存在价格持仓背离
    oi_divergence_type: str = "无背离"            # 背离类型
    is_oi_surge: bool = False                     # 是否持仓量异常激增

