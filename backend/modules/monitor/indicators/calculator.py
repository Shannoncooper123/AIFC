"""指标计算器 - 统一接口"""
from typing import Dict, Optional
import time
from ..data.kline_manager import KlineManager
from ..data.models import IndicatorValues
from .atr import calculate_atr, calculate_atr_list
from .volatility import (
    calculate_std_dev,
    calculate_price_change_rate,
    calculate_bollinger_bands,
    calculate_bollinger_bandwidth,
    calculate_ema_list,
    calculate_rsi,
    calculate_rsi_list,
)
from .volume import calculate_volume_ma
from .pattern import is_engulfing_bar, get_engulfing_type, calculate_wick_ratios
from .open_interest import (
    parse_oi_hist_response,
    calculate_oi_change_rate,
    calculate_oi_zscore,
    calculate_oi_ma,
    calculate_oi_momentum,
    analyze_oi_divergence,
    detect_oi_surge,
)
from ..detection.zscore import calculate_zscore


class IndicatorCalculator:
    """技术指标计算器"""
    
    def __init__(self, kline_manager: KlineManager, config: Dict, rest_client=None):
        """初始化
        
        Args:
            kline_manager: K线管理器
            config: 配置字典
            rest_client: REST API客户端（用于获取持仓量数据）
        """
        self.kline_manager = kline_manager
        self.config = config
        self.rest_client = rest_client
        
        # 从配置读取周期参数
        self.atr_period = config['indicators']['atr_period']
        self.stddev_period = config['indicators']['stddev_period']
        self.volume_ma_period = config['indicators']['volume_ma_period']
        # 新增指标配置
        indi_cfg = config['indicators']
        self.bb_period = indi_cfg.get('bb_period', 20)
        self.bb_std_multiplier = indi_cfg.get('bb_std_multiplier', 2.0)
        self.rsi_period = indi_cfg.get('rsi_period', 14)
        self.ema_fast_period = indi_cfg.get('ema_fast_period', 12)
        self.ema_slow_period = indi_cfg.get('ema_slow_period', 26)
        self.long_wick_ratio_threshold = indi_cfg.get('long_wick_ratio_threshold', 0.6)
        # 持仓量配置
        self.oi_ma_period = indi_cfg.get('oi_ma_period', 20)
        self.oi_momentum_period = indi_cfg.get('oi_momentum_period', 10)
        self.oi_divergence_window = indi_cfg.get('oi_divergence_window', 5)
        self.oi_enabled = config.get('open_interest', {}).get('enabled', True)
        self.oi_history_size = config.get('open_interest', {}).get('history_size', 30)
        
        # 持仓量数据缓存：{symbol: {'data': [...], 'last_update': timestamp}}
        self._oi_cache = {}
    
    def calculate_all(self, symbol: str) -> Optional[IndicatorValues]:
        """计算所有指标
        
        Args:
            symbol: 交易对符号
            
        Returns:
            指标值对象，数据不足返回None
        """
        # 检查是否有足够的数据
        required_count = max(
            self.atr_period,
            self.stddev_period,
            self.volume_ma_period,
            self.bb_period,
            self.rsi_period,
            self.ema_slow_period,
        ) + 1
        if not self.kline_manager.has_enough_data(symbol, required_count):
            return None
        
        # 获取K线数据
        klines = self.kline_manager.get_klines(symbol)
        latest_kline = klines[-1]
        closes = self.kline_manager.get_closes(symbol)
        volumes = self.kline_manager.get_volumes(symbol)
        current_close = latest_kline.close
        current_volume = latest_kline.volume
        
        # 计算ATR
        atr = calculate_atr(klines, self.atr_period)
        if atr is None:
            return None
        
        # 历史ATR用于Z-Score
        atr_list = calculate_atr_list(klines, self.atr_period)
        atr_zscore = calculate_zscore(atr, atr_list[:-1]) if len(atr_list) > 1 else 0.0
        
        # 价格变化率
        price_change_rate = calculate_price_change_rate(latest_kline)
        price_changes = []
        for i in range(1, len(klines)):
            pc = calculate_price_change_rate(klines[i])
            price_changes.append(pc)
        price_change_zscore = calculate_zscore(price_change_rate, price_changes[:-1]) if len(price_changes) > 1 else 0.0
        
        # 成交量指标
        volume_ma = calculate_volume_ma(volumes, self.volume_ma_period)
        if volume_ma is None:
            return None
        volume_zscore = calculate_zscore(current_volume, volumes[:-1]) if len(volumes) > 1 else 0.0
        
        # 标准差
        stddev = calculate_std_dev(closes, self.stddev_period) or 0.0
        
        # 形态：外包线（使用严格模式，要求实体吞没）
        is_engulfing = False
        engulfing_type = '非外包'
        engulfing_strict = self.config.get('indicators', {}).get('engulfing_strict_mode', True)
        if len(klines) >= 2:
            is_engulfing = is_engulfing_bar(klines[-1], klines[-2], require_body_engulf=engulfing_strict)
            engulfing_type = get_engulfing_type(klines[-1], klines[-2], strict=engulfing_strict)
        
        # 形态：长影线比例
        upper_wick_ratio, lower_wick_ratio = calculate_wick_ratios(latest_kline)
        is_long_upper_wick = upper_wick_ratio >= self.long_wick_ratio_threshold
        is_long_lower_wick = lower_wick_ratio >= self.long_wick_ratio_threshold
        
        # 布林带
        bb_bands = calculate_bollinger_bands(closes, self.bb_period, self.bb_std_multiplier)
        bb_upper, bb_middle, bb_lower = (0.0, 0.0, 0.0)
        bb_width = 0.0
        bb_width_zscore = 0.0
        is_bb_breakout_upper = False
        is_bb_breakout_lower = False
        is_bb_squeeze = False
        if bb_bands is not None:
            bb_upper, bb_middle, bb_lower = bb_bands
            bb_width = calculate_bollinger_bandwidth(closes, self.bb_period, self.bb_std_multiplier) or 0.0
            # 计算历史宽度用于Z-Score
            bb_width_history = []
            for i in range(self.bb_period, len(closes)):
                recent = closes[i-self.bb_period:i]
                bands = calculate_bollinger_bands(recent, self.bb_period, self.bb_std_multiplier)
                if bands:
                    u, m, l = bands
                    w = (u - l) / m if m != 0 else (u - l)
                    bb_width_history.append(float(w))
            bb_width_zscore = calculate_zscore(bb_width, bb_width_history[:-1]) if len(bb_width_history) > 1 else 0.0
            # 突破判定
            is_bb_breakout_upper = current_close > bb_upper
            is_bb_breakout_lower = current_close < bb_lower
            # Squeeze 判定（带宽显著收缩）
            is_bb_squeeze = bb_width_zscore < -2.0
        
        # RSI
        rsi = calculate_rsi(closes, self.rsi_period) or 0.0
        rsi_history = calculate_rsi_list(closes, self.rsi_period)
        rsi_zscore = calculate_zscore(rsi, rsi_history[:-1]) if len(rsi_history) > 1 else 0.0
        is_rsi_overbought = rsi >= 70
        is_rsi_oversold = rsi <= 30
        
        # EMA 金叉/死叉与乖离
        ema_fast_list = calculate_ema_list(closes, self.ema_fast_period)
        ema_slow_list = calculate_ema_list(closes, self.ema_slow_period)
        ema_fast = float(ema_fast_list[-1]) if ema_fast_list else 0.0
        ema_slow = float(ema_slow_list[-1]) if ema_slow_list else 0.0
        is_ma_bullish_cross = False
        is_ma_bearish_cross = False
        if len(ema_fast_list) >= 2 and len(ema_slow_list) >= 2:
            prev_fast = ema_fast_list[-2]
            prev_slow = ema_slow_list[-2]
            is_ma_bullish_cross = (prev_fast <= prev_slow) and (ema_fast > ema_slow)
            is_ma_bearish_cross = (prev_fast >= prev_slow) and (ema_fast < ema_slow)
        ma_deviation = 0.0
        if ema_slow != 0:
            ma_deviation = (current_close - ema_slow) / ema_slow
        ma_dev_history = []
        if len(ema_slow_list) > 1:
            for i in range(1, len(ema_slow_list)):
                base = ema_slow_list[i]
                close_i = closes[i] if i < len(closes) else closes[-1]
                if base != 0:
                    ma_dev_history.append((close_i - base) / base)
        ma_deviation_zscore = calculate_zscore(ma_deviation, ma_dev_history[:-1]) if len(ma_dev_history) > 1 else 0.0
        
        # 持仓量指标（与K线周期同步更新）
        open_interest = 0.0
        open_interest_value = 0.0
        oi_change_rate = 0.0
        oi_value_change_rate = 0.0
        oi_zscore = 0.0
        oi_ma = 0.0
        oi_momentum = 0.0
        is_oi_divergence = False
        oi_divergence_type = "无背离"
        is_oi_surge = False
        
        if self.oi_enabled and self.rest_client:
            try:
                # 检查缓存是否需要更新（每个K线周期更新一次）
                current_timestamp = latest_kline.timestamp
                cache = self._oi_cache.get(symbol)
                need_update = (
                    cache is None or 
                    current_timestamp - cache.get('last_update', 0) >= self._get_interval_ms()
                )
                
                if need_update:
                    # 获取持仓量历史数据
                    interval = self.config['kline']['interval']
                    raw_oi = self.rest_client.get_open_interest_hist(
                        symbol, interval, self.oi_history_size
                    )
                    if raw_oi:
                        self._oi_cache[symbol] = {
                            'data': raw_oi,
                            'last_update': current_timestamp
                        }
                        cache = self._oi_cache[symbol]
                
                # 计算持仓量指标
                if cache and cache.get('data'):
                    oi_data = cache['data']
                    oi_values, oi_value_values, timestamps = parse_oi_hist_response(oi_data)
                    
                    if len(oi_values) > 0:
                        open_interest = oi_values[-1]
                        open_interest_value = oi_value_values[-1]
                        
                        # 计算变化率
                        if len(oi_values) >= 2:
                            oi_change_rate = calculate_oi_change_rate(oi_values[-1], oi_values[-2])
                            oi_value_change_rate = calculate_oi_change_rate(
                                oi_value_values[-1], oi_value_values[-2]
                            )
                        
                        # 计算变化率列表用于Z-Score
                        oi_changes = []
                        for i in range(1, len(oi_values)):
                            change = calculate_oi_change_rate(oi_values[i], oi_values[i-1])
                            oi_changes.append(change)
                        
                        if len(oi_changes) >= 2:
                            oi_zscore = calculate_oi_zscore(oi_changes) or 0.0
                        
                        # MA和动量
                        oi_ma = calculate_oi_ma(oi_values, self.oi_ma_period) or 0.0
                        oi_momentum = calculate_oi_momentum(oi_values, self.oi_momentum_period) or 0.0
                        
                        # 检测激增
                        if len(oi_changes) > 0:
                            is_oi_surge = detect_oi_surge(
                                oi_change_rate, oi_changes, 2.5
                            )
                        
                        # 分析背离
                        if len(price_changes) >= self.oi_divergence_window and len(oi_changes) >= self.oi_divergence_window:
                            is_oi_divergence, oi_divergence_type = analyze_oi_divergence(
                                price_changes, oi_changes, self.oi_divergence_window,
                                price_threshold=0.5,
                                oi_threshold=1.0
                            )
                        
            except Exception as e:
                # 持仓量获取失败不影响其他指标
                from ..utils.logger import get_logger
                logger = get_logger('calculator')
                logger.warning(f"获取 {symbol} 持仓量失败: {e}")
        
        return IndicatorValues(
            symbol=symbol,
            atr=atr,
            atr_zscore=atr_zscore,
            price_change_rate=price_change_rate,
            price_change_zscore=price_change_zscore,
            volume=current_volume,
            volume_ma=volume_ma,
            volume_zscore=volume_zscore,
            stddev=stddev,
            is_engulfing=is_engulfing,
            engulfing_type=engulfing_type,
            # 新增输出字段
            rsi=rsi,
            rsi_zscore=rsi_zscore,
            is_rsi_overbought=is_rsi_overbought,
            is_rsi_oversold=is_rsi_oversold,
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            is_ma_bullish_cross=is_ma_bullish_cross,
            is_ma_bearish_cross=is_ma_bearish_cross,
            ma_deviation=ma_deviation,
            ma_deviation_zscore=ma_deviation_zscore,
            bb_upper=bb_upper,
            bb_middle=bb_middle,
            bb_lower=bb_lower,
            bb_width=bb_width,
            bb_width_zscore=bb_width_zscore,
            is_bb_breakout_upper=is_bb_breakout_upper,
            is_bb_breakout_lower=is_bb_breakout_lower,
            is_bb_squeeze=is_bb_squeeze,
            upper_wick_ratio=upper_wick_ratio,
            lower_wick_ratio=lower_wick_ratio,
            is_long_upper_wick=is_long_upper_wick,
            is_long_lower_wick=is_long_lower_wick,
            # 持仓量字段
            open_interest=open_interest,
            open_interest_value=open_interest_value,
            oi_change_rate=oi_change_rate,
            oi_value_change_rate=oi_value_change_rate,
            oi_zscore=oi_zscore,
            oi_ma=oi_ma,
            oi_momentum=oi_momentum,
            is_oi_divergence=is_oi_divergence,
            oi_divergence_type=oi_divergence_type,
            is_oi_surge=is_oi_surge,
        )
    
    def _get_interval_ms(self) -> int:
        """获取K线间隔的毫秒数"""
        interval = self.config['kline']['interval']
        unit = interval[-1]
        value = int(interval[:-1])
        
        if unit == 'm':
            return value * 60 * 1000
        elif unit == 'h':
            return value * 60 * 60 * 1000
        elif unit == 'd':
            return value * 24 * 60 * 60 * 1000
        elif unit == 'w':
            return value * 7 * 24 * 60 * 60 * 1000
        elif unit == 'M':
            return value * 30 * 24 * 60 * 60 * 1000  # 近似
        else:
            return 15 * 60 * 1000  # 默认15分钟
    
    def get_required_kline_count(self) -> int:
        """获取计算所需的最小K线数量"""
        return max(
            self.atr_period,
            self.stddev_period,
            self.volume_ma_period,
            self.bb_period,
            self.rsi_period,
            self.ema_slow_period,
        ) + 1

