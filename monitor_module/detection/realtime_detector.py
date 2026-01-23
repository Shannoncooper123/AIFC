"""实时刺破检测器"""
import time
from typing import Dict, Optional, Callable
from ..data.kline_manager import KlineManager
from ..indicators.calculator import IndicatorCalculator
from ..utils.logger import get_logger

logger = get_logger('realtime_detector')


class RealtimeBreakoutDetector:
    """实时布林线下轨刺破检测器"""
    
    def __init__(self, 
                 kline_manager: KlineManager,
                 indicator_calculator: IndicatorCalculator,
                 config: Dict,
                 on_breakout_callback: Optional[Callable] = None):
        """初始化
        
        Args:
            kline_manager: K线管理器
            indicator_calculator: 指标计算器
            config: 配置字典
            on_breakout_callback: 刺破回调函数 callback(symbol, breakout_data)
        """
        self.kline_manager = kline_manager
        self.indicator_calculator = indicator_calculator
        self.config = config
        self.on_breakout_callback = on_breakout_callback
        
        # 从配置读取参数
        rule_cfg = config.get('rule_strategy', {})
        realtime_cfg = rule_cfg.get('realtime_monitoring', {})
        
        self.enabled = realtime_cfg.get('enabled', True)
        self.rsi_threshold = rule_cfg.get('entry', {}).get('rsi_entry', 40)
        
        # 冷却时间追踪：记录上次触发的K线时间戳
        self.last_trigger_kline_ts: Dict[str, int] = {}
        
        logger.info(f"实时刺破检测器初始化完成")
        logger.info(f"  启用: {self.enabled}")
        logger.info(f"  冷却机制: 每根K线只触发一次")
        logger.info(f"  RSI阈值: {self.rsi_threshold}")
    
    def check_breakout(self, symbol: str, current_low: float, kline_open_time: int) -> bool:
        """检测是否刺破布林线下轨
        
        Args:
            symbol: 交易对
            current_low: 当前K线最低价
            kline_open_time: K线开盘时间戳（毫秒）
            
        Returns:
            是否触发刺破信号
        """
        if not self.enabled:
            return False
        
        # 检查是否已在当前K线触发过
        last_kline_ts = self.last_trigger_kline_ts.get(symbol, 0)
        if kline_open_time == last_kline_ts:
            return False  # 同一根K线已触发过
        
        # 计算指标（基于历史K线）
        indicators = self.indicator_calculator.calculate_all(symbol)
        if not indicators:
            return False
        
        # 检查条件
        bb_lower = indicators.bb_lower
        rsi = indicators.rsi
        
        # 触发条件：低价刺破布林线下轨 且 RSI < 40
        # 具体是Level 1还是Level 2由策略执行器根据RSI值判断
        is_below = current_low < bb_lower
        is_rsi_ok = rsi < self.rsi_threshold  # 默认40
        
        if is_below and is_rsi_ok:
            # 触发信号，记录K线时间戳
            self.last_trigger_kline_ts[symbol] = kline_open_time
            
            logger.warning(
                f"🔴 实时刺破 {symbol}: "
                f"Low={current_low:.6f} < BB_Lower={bb_lower:.6f}, "
                f"RSI={rsi:.1f}"
            )
            
            # 回调
            if self.on_breakout_callback:
                breakout_data = {
                    'symbol': symbol,
                    'trigger_price': current_low,
                    'bb_lower': bb_lower,
                    'rsi': rsi,
                    'atr': indicators.atr,  # 添加真实ATR值
                    'timestamp': time.time()
                }
                self.on_breakout_callback(symbol, breakout_data)
            
            return True
        
        return False
    
    def reset_cooldown(self, symbol: str):
        """重置冷却时间（用于测试或手动触发）
        
        Args:
            symbol: 交易对
        """
        if symbol in self.last_trigger_time:
            del self.last_trigger_time[symbol]
