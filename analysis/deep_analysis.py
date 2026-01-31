#!/usr/bin/env python3
"""
深度分析做空方向问题
- 对比做多和做空的各项指标差异
- 获取实际K线数据分析入场时的市场状态
- 分析持仓周期内的价格走势
"""
import json
import sys
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple
import time
import bisect

sys.path.insert(0, '/Users/bytedance/Desktop/crypto_agentx/backend')

from modules.monitor.clients.binance_rest import BinanceRestClient

DATA_FILE = '/Users/bytedance/Desktop/crypto_agentx/analysis/all_positions.jsonl'

INTERVAL_MINUTES = {
    '1m': 1, '3m': 3, '5m': 5, '15m': 15, '30m': 30,
    '1h': 60, '2h': 120, '4h': 240, '6h': 360, '12h': 720, '1d': 1440
}


class KlineCache:
    """K线数据缓存 - 批量预加载多周期数据"""
    
    def __init__(self):
        self._cache: Dict[str, Dict[str, List[Dict]]] = {}
        self._timestamps: Dict[str, Dict[str, List[int]]] = {}
    
    def preload(self, symbols: List[str], start_time: datetime, end_time: datetime, 
                intervals: List[str] = None, buffer_bars: int = 200):
        """
        批量预加载多周期K线数据
        """
        if intervals is None:
            intervals = ['15m', '1h', '4h']
        
        print(f'\n预加载K线数据: {len(symbols)} 个交易对, {len(intervals)} 个周期')
        print(f'时间范围: {start_time} ~ {end_time}')
        
        config = {
            'api': {
                'base_url': 'https://fapi.binance.com',
                'timeout': 30,
                'retry_times': 5
            }
        }
        client = BinanceRestClient(config)
        
        for symbol in symbols:
            symbol = symbol.upper()
            if symbol not in self._cache:
                self._cache[symbol] = {}
                self._timestamps[symbol] = {}
            
            for interval in intervals:
                interval_minutes = INTERVAL_MINUTES.get(interval, 15)
                buffer_ms = buffer_bars * interval_minutes * 60 * 1000
                
                start_ms = int(start_time.timestamp() * 1000) - buffer_ms
                end_ms = int(end_time.timestamp() * 1000) + (24 * 60 * 60 * 1000)
                
                print(f'  加载 {symbol} {interval}...', end=' ', flush=True)
                
                try:
                    all_klines = []
                    current_start = start_ms
                    batch_count = 0
                    
                    while current_start < end_ms:
                        raw = client.get_klines(
                            symbol=symbol,
                            interval=interval,
                            limit=1500,
                            start_time=current_start,
                            end_time=end_ms
                        )
                        
                        if not raw:
                            break
                        
                        for k in raw:
                            all_klines.append({
                                'timestamp': k[0],
                                'open': float(k[1]),
                                'high': float(k[2]),
                                'low': float(k[3]),
                                'close': float(k[4]),
                                'volume': float(k[5])
                            })
                        
                        batch_count += 1
                        
                        if len(raw) < 1500:
                            break
                        
                        last_ts = raw[-1][0]
                        current_start = last_ts + interval_minutes * 60 * 1000
                        
                        time.sleep(0.1)
                    
                    seen = set()
                    unique_klines = []
                    for k in all_klines:
                        if k['timestamp'] not in seen:
                            seen.add(k['timestamp'])
                            unique_klines.append(k)
                    
                    unique_klines.sort(key=lambda x: x['timestamp'])
                    
                    self._cache[symbol][interval] = unique_klines
                    self._timestamps[symbol][interval] = [k['timestamp'] for k in unique_klines]
                    
                    print(f'{len(unique_klines)} 根K线')
                    
                except Exception as e:
                    print(f'失败: {e}')
                    self._cache[symbol][interval] = []
                    self._timestamps[symbol][interval] = []
        
        client.close()
        print('K线数据预加载完成\n')
    
    def get_klines_before(self, symbol: str, interval: str, 
                          target_time: datetime, limit: int = 20) -> Optional[List[Dict]]:
        """获取目标时间之前的K线数据"""
        symbol = symbol.upper()
        
        if symbol not in self._cache or interval not in self._cache[symbol]:
            return None
        
        klines = self._cache[symbol][interval]
        timestamps = self._timestamps[symbol][interval]
        
        if not klines:
            return None
        
        target_ts = int(target_time.timestamp() * 1000)
        idx = bisect.bisect_right(timestamps, target_ts)
        
        if idx == 0:
            return None
        
        start_idx = max(0, idx - limit)
        result = klines[start_idx:idx]
        
        return result if result else None
    
    def get_klines_range(self, symbol: str, interval: str,
                         start_time: datetime, end_time: datetime) -> Optional[List[Dict]]:
        """获取时间范围内的K线数据"""
        symbol = symbol.upper()
        
        if symbol not in self._cache or interval not in self._cache[symbol]:
            return None
        
        klines = self._cache[symbol][interval]
        timestamps = self._timestamps[symbol][interval]
        
        if not klines:
            return None
        
        start_ts = int(start_time.timestamp() * 1000)
        end_ts = int(end_time.timestamp() * 1000)
        
        start_idx = bisect.bisect_left(timestamps, start_ts)
        end_idx = bisect.bisect_right(timestamps, end_ts)
        
        result = klines[start_idx:end_idx]
        return result if result else None


kline_cache = KlineCache()


def load_positions(filepath: str) -> List[Dict]:
    """加载交易数据"""
    positions = []
    with open(filepath, 'r') as f:
        for line in f:
            if line.strip():
                data = json.loads(line)
                if data.get('type') == 'trade':
                    positions.append(data)
    return positions


def get_time_range_from_positions(positions: List[Dict]) -> Tuple[datetime, datetime]:
    """从交易记录中获取时间范围"""
    entry_times = []
    exit_times = []
    for p in positions:
        for field, lst in [('entry_time', entry_times), ('exit_time', exit_times)]:
            time_str = p.get(field, '')
            if time_str:
                try:
                    dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                    lst.append(dt)
                except:
                    pass
    
    if not entry_times:
        now = datetime.now(timezone.utc)
        return now - timedelta(days=7), now
    
    return min(entry_times), max(exit_times) if exit_times else max(entry_times)


def get_symbols_from_positions(positions: List[Dict]) -> List[str]:
    """从交易记录中获取所有交易对"""
    symbols = set()
    for p in positions:
        symbol = p.get('symbol', '')
        if symbol:
            symbols.add(symbol.upper())
    return list(symbols)


def calculate_trend(klines: List[Dict], period: int = None) -> Dict:
    """
    计算趋势指标
    
    Returns:
        trend_pct: 涨跌幅百分比
        direction: 'up' / 'down' / 'sideways'
        strength: 'strong' / 'moderate' / 'weak'
        higher_highs: 是否形成更高的高点
        lower_lows: 是否形成更低的低点
    """
    if not klines or len(klines) < 2:
        return {'trend_pct': 0, 'direction': 'unknown', 'strength': 'unknown'}
    
    if period:
        klines = klines[-period:]
    
    start_price = klines[0]['open']
    end_price = klines[-1]['close']
    trend_pct = (end_price - start_price) / start_price * 100
    
    highs = [k['high'] for k in klines]
    lows = [k['low'] for k in klines]
    
    mid = len(klines) // 2
    first_half_high = max(highs[:mid]) if mid > 0 else highs[0]
    second_half_high = max(highs[mid:])
    first_half_low = min(lows[:mid]) if mid > 0 else lows[0]
    second_half_low = min(lows[mid:])
    
    higher_highs = second_half_high > first_half_high
    lower_lows = second_half_low < first_half_low
    
    if trend_pct > 1.0:
        direction = 'up'
        strength = 'strong' if trend_pct > 2.0 else 'moderate'
    elif trend_pct < -1.0:
        direction = 'down'
        strength = 'strong' if trend_pct < -2.0 else 'moderate'
    elif abs(trend_pct) < 0.3:
        direction = 'sideways'
        strength = 'weak'
    else:
        direction = 'up' if trend_pct > 0 else 'down'
        strength = 'weak'
    
    return {
        'trend_pct': trend_pct,
        'direction': direction,
        'strength': strength,
        'higher_highs': higher_highs,
        'lower_lows': lower_lows
    }


def calculate_volatility(klines: List[Dict]) -> Dict:
    """计算波动率指标"""
    if not klines:
        return {'atr_pct': 0, 'level': 'unknown'}
    
    atr_values = []
    for k in klines:
        tr = k['high'] - k['low']
        atr_values.append(tr / k['open'] * 100)
    
    atr_pct = sum(atr_values) / len(atr_values)
    
    if atr_pct > 1.0:
        level = 'high'
    elif atr_pct > 0.5:
        level = 'medium'
    else:
        level = 'low'
    
    return {'atr_pct': atr_pct, 'level': level}


def calculate_price_position(price: float, klines: List[Dict]) -> Dict:
    """计算价格在区间中的位置"""
    if not klines:
        return {'position_pct': 50, 'zone': 'middle'}
    
    highs = [k['high'] for k in klines]
    lows = [k['low'] for k in klines]
    
    range_high = max(highs)
    range_low = min(lows)
    
    if range_high == range_low:
        return {'position_pct': 50, 'zone': 'middle', 'range_high': range_high, 'range_low': range_low}
    
    position_pct = (price - range_low) / (range_high - range_low) * 100
    
    if position_pct >= 80:
        zone = 'top'
    elif position_pct >= 60:
        zone = 'upper'
    elif position_pct >= 40:
        zone = 'middle'
    elif position_pct >= 20:
        zone = 'lower'
    else:
        zone = 'bottom'
    
    return {
        'position_pct': position_pct,
        'zone': zone,
        'range_high': range_high,
        'range_low': range_low
    }


def analyze_holding_period(klines: List[Dict], entry_price: float, 
                           tp_price: float, sl_price: float, side: str) -> Dict:
    """
    分析持仓周期内的价格走势
    
    Returns:
        max_favorable: 最大有利方向移动
        max_adverse: 最大不利方向移动
        touched_tp_first: 是否先触及止盈区域
        touched_sl_first: 是否先触及止损区域
        price_path: 价格路径特征
    """
    if not klines:
        return {}
    
    if side == 'long':
        favorable_prices = [k['high'] for k in klines]
        adverse_prices = [k['low'] for k in klines]
        max_favorable = max((p - entry_price) / entry_price * 100 for p in favorable_prices)
        max_adverse = min((p - entry_price) / entry_price * 100 for p in adverse_prices)
    else:
        favorable_prices = [k['low'] for k in klines]
        adverse_prices = [k['high'] for k in klines]
        max_favorable = max((entry_price - p) / entry_price * 100 for p in favorable_prices)
        max_adverse = min((entry_price - p) / entry_price * 100 for p in adverse_prices)
    
    tp_touch_idx = None
    sl_touch_idx = None
    
    for i, k in enumerate(klines):
        if side == 'long':
            if tp_touch_idx is None and k['high'] >= tp_price:
                tp_touch_idx = i
            if sl_touch_idx is None and k['low'] <= sl_price:
                sl_touch_idx = i
        else:
            if tp_touch_idx is None and k['low'] <= tp_price:
                tp_touch_idx = i
            if sl_touch_idx is None and k['high'] >= sl_price:
                sl_touch_idx = i
    
    if tp_touch_idx is not None and sl_touch_idx is not None:
        touched_first = 'tp' if tp_touch_idx < sl_touch_idx else 'sl'
    elif tp_touch_idx is not None:
        touched_first = 'tp'
    elif sl_touch_idx is not None:
        touched_first = 'sl'
    else:
        touched_first = 'none'
    
    closes = [k['close'] for k in klines]
    if len(closes) >= 3:
        first_third = sum(closes[:len(closes)//3]) / (len(closes)//3)
        last_third = sum(closes[-len(closes)//3:]) / (len(closes)//3)
        if side == 'long':
            path_direction = 'favorable' if last_third > first_third else 'adverse'
        else:
            path_direction = 'favorable' if last_third < first_third else 'adverse'
    else:
        path_direction = 'unknown'
    
    return {
        'max_favorable_pct': max_favorable,
        'max_adverse_pct': max_adverse,
        'touched_first': touched_first,
        'price_path': path_direction
    }


def analyze_market_structure(klines_15m: List[Dict], klines_1h: List[Dict], 
                             klines_4h: List[Dict], entry_price: float) -> Dict:
    """
    多周期市场结构分析
    """
    result = {}
    
    if klines_15m:
        trend_15m = calculate_trend(klines_15m, 20)
        result['trend_15m'] = trend_15m['direction']
        result['trend_15m_pct'] = trend_15m['trend_pct']
        result['trend_15m_strength'] = trend_15m['strength']
        
        vol_15m = calculate_volatility(klines_15m[-10:])
        result['volatility_15m'] = vol_15m['level']
        result['atr_15m'] = vol_15m['atr_pct']
        
        pos_15m = calculate_price_position(entry_price, klines_15m[-20:])
        result['position_15m'] = pos_15m['zone']
        result['position_15m_pct'] = pos_15m['position_pct']
    
    if klines_1h:
        trend_1h = calculate_trend(klines_1h, 24)
        result['trend_1h'] = trend_1h['direction']
        result['trend_1h_pct'] = trend_1h['trend_pct']
        result['trend_1h_strength'] = trend_1h['strength']
        
        pos_1h = calculate_price_position(entry_price, klines_1h[-24:])
        result['position_1h'] = pos_1h['zone']
        result['position_1h_pct'] = pos_1h['position_pct']
    
    if klines_4h:
        trend_4h = calculate_trend(klines_4h, 30)
        result['trend_4h'] = trend_4h['direction']
        result['trend_4h_pct'] = trend_4h['trend_pct']
        result['trend_4h_strength'] = trend_4h['strength']
        
        pos_4h = calculate_price_position(entry_price, klines_4h[-30:])
        result['position_4h'] = pos_4h['zone']
        result['position_4h_pct'] = pos_4h['position_pct']
    
    trends = [result.get('trend_15m'), result.get('trend_1h'), result.get('trend_4h')]
    trends = [t for t in trends if t and t != 'unknown']
    
    if trends:
        up_count = sum(1 for t in trends if t == 'up')
        down_count = sum(1 for t in trends if t == 'down')
        
        if up_count == len(trends):
            result['multi_tf_alignment'] = 'all_up'
        elif down_count == len(trends):
            result['multi_tf_alignment'] = 'all_down'
        elif up_count > down_count:
            result['multi_tf_alignment'] = 'mixed_bullish'
        elif down_count > up_count:
            result['multi_tf_alignment'] = 'mixed_bearish'
        else:
            result['multi_tf_alignment'] = 'conflicting'
    else:
        result['multi_tf_alignment'] = 'unknown'
    
    return result


def analyze_trade_context(trade: Dict) -> Optional[Dict]:
    """
    分析单个交易的完整上下文
    """
    try:
        entry_time_str = trade.get('entry_time', '')
        exit_time_str = trade.get('exit_time', '')
        if not entry_time_str:
            return None
        
        entry_dt = datetime.fromisoformat(entry_time_str.replace('Z', '+00:00'))
        exit_dt = datetime.fromisoformat(exit_time_str.replace('Z', '+00:00')) if exit_time_str else None
        
        symbol = trade.get('symbol', '')
        side = trade.get('side', '')
        entry_price = trade.get('entry_price', 0)
        tp_price = trade.get('tp_price', 0)
        sl_price = trade.get('sl_price', 0)
        
        klines_15m = kline_cache.get_klines_before(symbol, '15m', entry_dt, 50)
        klines_1h = kline_cache.get_klines_before(symbol, '1h', entry_dt, 48)
        klines_4h = kline_cache.get_klines_before(symbol, '4h', entry_dt, 60)
        
        market = analyze_market_structure(klines_15m, klines_1h, klines_4h, entry_price)
        
        holding_analysis = {}
        if exit_dt and entry_dt:
            holding_klines = kline_cache.get_klines_range(symbol, '15m', entry_dt, exit_dt)
            if holding_klines:
                holding_analysis = analyze_holding_period(
                    holding_klines, entry_price, tp_price, sl_price, side
                )
        
        ctx = {
            'symbol': symbol,
            'side': side,
            'is_win': trade.get('is_win', False),
            'pnl': trade.get('realized_pnl', 0),
            'sl_distance': trade.get('sl_distance_percent', 0),
            'tp_distance': trade.get('tp_distance_percent', 0),
            **market,
            **holding_analysis
        }
        
        if side == 'long':
            ctx['is_counter_trend_4h'] = market.get('trend_4h') == 'down'
            ctx['is_counter_trend_1h'] = market.get('trend_1h') == 'down'
        else:
            ctx['is_counter_trend_4h'] = market.get('trend_4h') == 'up'
            ctx['is_counter_trend_1h'] = market.get('trend_1h') == 'up'
        
        return ctx
        
    except Exception as e:
        return None


def basic_analysis(positions: List[Dict]):
    """基础统计分析"""
    print('='*80)
    print('1. 基础统计对比')
    print('='*80)
    
    long_trades = [p for p in positions if p.get('side') == 'long']
    short_trades = [p for p in positions if p.get('side') == 'short']
    
    print(f'\n总交易数: {len(positions)}')
    print(f'做多交易数: {len(long_trades)} ({len(long_trades)/len(positions)*100:.1f}%)')
    print(f'做空交易数: {len(short_trades)} ({len(short_trades)/len(positions)*100:.1f}%)')
    
    for side, trades in [('做多', long_trades), ('做空', short_trades)]:
        wins = [p for p in trades if p.get('is_win')]
        losses = [p for p in trades if not p.get('is_win')]
        total_pnl = sum(p.get('realized_pnl', 0) for p in trades)
        
        win_pnls = [p.get('realized_pnl', 0) for p in wins]
        loss_pnls = [p.get('realized_pnl', 0) for p in losses]
        
        avg_win = sum(win_pnls) / len(win_pnls) if win_pnls else 0
        avg_loss = sum(loss_pnls) / len(loss_pnls) if loss_pnls else 0
        rr = abs(avg_win / avg_loss) if avg_loss != 0 else 0
        
        sl_dists = [p.get('sl_distance_percent', 0) for p in trades]
        tp_dists = [p.get('tp_distance_percent', 0) for p in trades]
        
        print(f'\n--- {side} ---')
        print(f'胜率: {len(wins)/len(trades)*100:.1f}% ({len(wins)}/{len(trades)})')
        print(f'总P&L: ${total_pnl:.2f}')
        print(f'平均盈利: ${avg_win:.2f}')
        print(f'平均亏损: ${avg_loss:.2f}')
        print(f'盈亏比: {rr:.2f}')
        print(f'平均止损距离: {sum(sl_dists)/len(sl_dists):.3f}%')
        print(f'平均止盈距离: {sum(tp_dists)/len(tp_dists):.3f}%')
    
    return long_trades, short_trades


def detailed_comparison(long_trades: List[Dict], short_trades: List[Dict]):
    """详细对比分析"""
    print('\n' + '='*80)
    print('2. 止损止盈距离详细对比')
    print('='*80)
    
    for side, trades in [('做多', long_trades), ('做空', short_trades)]:
        print(f'\n--- {side} 止损距离分布 ---')
        for sl_min, sl_max, label in [(0, 0.3, '<0.3%'), (0.3, 0.5, '0.3-0.5%'), 
                                       (0.5, 0.7, '0.5-0.7%'), (0.7, 1.0, '0.7-1%'), 
                                       (1.0, 100, '>1%')]:
            subset = [p for p in trades if sl_min <= p.get('sl_distance_percent', 0) < sl_max]
            if subset:
                wins = len([p for p in subset if p.get('is_win')])
                pnl = sum(p.get('realized_pnl', 0) for p in subset)
                wr = wins / len(subset) * 100
                print(f'  SL {label}: {len(subset):4d} trades, WR {wr:5.1f}%, P&L ${pnl:>10.2f}')


def kline_context_analysis(positions: List[Dict]):
    """
    K线上下文分析 - 多周期市场结构分析
    """
    print('\n' + '='*80)
    print('3. K线上下文分析 (多周期市场结构)')
    print('='*80)
    
    symbols = get_symbols_from_positions(positions)
    start_time_dt, end_time_dt = get_time_range_from_positions(positions)
    
    kline_cache.preload(symbols, start_time_dt, end_time_dt, 
                        intervals=['15m', '1h', '4h'], buffer_bars=200)
    
    print(f'分析所有交易: {len(positions)} 条')
    
    contexts = []
    failed = 0
    
    start_time = time.time()
    
    for i, trade in enumerate(positions):
        if (i + 1) % 500 == 0 or i == len(positions) - 1:
            elapsed = time.time() - start_time
            print(f'  进度: {i+1}/{len(positions)} ({(i+1)/len(positions)*100:.1f}%) - 耗时 {elapsed:.1f}s')
        
        ctx = analyze_trade_context(trade)
        if ctx:
            contexts.append(ctx)
        else:
            failed += 1
    
    elapsed = time.time() - start_time
    print(f'\n完成! 耗时 {elapsed:.1f}s, 成功 {len(contexts)}, 失败 {failed}')
    
    long_ctx = [c for c in contexts if c.get('side') == 'long']
    short_ctx = [c for c in contexts if c.get('side') == 'short']
    
    print_multi_timeframe_analysis(long_ctx, short_ctx)
    print_position_analysis(long_ctx, short_ctx)
    print_holding_period_analysis(long_ctx, short_ctx)
    print_counter_trend_analysis(long_ctx, short_ctx)
    
    return contexts


def print_multi_timeframe_analysis(long_ctx: List[Dict], short_ctx: List[Dict]):
    """多周期趋势分析"""
    print('\n' + '='*80)
    print('4. 多周期趋势对齐分析')
    print('='*80)
    
    for side, contexts in [('做多', long_ctx), ('做空', short_ctx)]:
        if not contexts:
            continue
        
        print(f'\n--- {side} 多周期对齐情况 ---')
        
        alignments = defaultdict(list)
        for c in contexts:
            align = c.get('multi_tf_alignment', 'unknown')
            alignments[align].append(c)
        
        for align in ['all_up', 'all_down', 'mixed_bullish', 'mixed_bearish', 'conflicting', 'unknown']:
            subset = alignments.get(align, [])
            if subset:
                wins = len([c for c in subset if c.get('is_win')])
                pnl = sum(c.get('pnl', 0) for c in subset)
                wr = wins / len(subset) * 100 if subset else 0
                print(f'  {align:15s}: {len(subset):4d} ({len(subset)/len(contexts)*100:5.1f}%), WR {wr:5.1f}%, P&L ${pnl:>10.2f}')


def print_position_analysis(long_ctx: List[Dict], short_ctx: List[Dict]):
    """价格位置分析"""
    print('\n' + '='*80)
    print('5. 多周期价格位置分析')
    print('='*80)
    
    for tf in ['4h', '1h', '15m']:
        print(f'\n--- {tf} 周期价格位置 ---')
        
        for side, contexts in [('做多', long_ctx), ('做空', short_ctx)]:
            if not contexts:
                continue
            
            print(f'\n  {side}:')
            
            zones = defaultdict(list)
            for c in contexts:
                zone = c.get(f'position_{tf}', 'unknown')
                zones[zone].append(c)
            
            for zone in ['top', 'upper', 'middle', 'lower', 'bottom', 'unknown']:
                subset = zones.get(zone, [])
                if subset:
                    wins = len([c for c in subset if c.get('is_win')])
                    pnl = sum(c.get('pnl', 0) for c in subset)
                    wr = wins / len(subset) * 100 if subset else 0
                    print(f'    {zone:8s}: {len(subset):4d} ({len(subset)/len(contexts)*100:5.1f}%), WR {wr:5.1f}%, P&L ${pnl:>10.2f}')


def print_holding_period_analysis(long_ctx: List[Dict], short_ctx: List[Dict]):
    """持仓周期分析"""
    print('\n' + '='*80)
    print('6. 持仓周期价格走势分析')
    print('='*80)
    
    for side, contexts in [('做多', long_ctx), ('做空', short_ctx)]:
        if not contexts:
            continue
        
        print(f'\n--- {side} ---')
        
        with_max_favorable = [c for c in contexts if 'max_favorable_pct' in c]
        if with_max_favorable:
            avg_favorable = sum(c['max_favorable_pct'] for c in with_max_favorable) / len(with_max_favorable)
            avg_adverse = sum(c['max_adverse_pct'] for c in with_max_favorable) / len(with_max_favorable)
            print(f'  平均最大有利移动: {avg_favorable:.2f}%')
            print(f'  平均最大不利移动: {avg_adverse:.2f}%')
        
        touched_first = defaultdict(list)
        for c in contexts:
            tf = c.get('touched_first', 'unknown')
            touched_first[tf].append(c)
        
        print(f'\n  先触及分析:')
        for tf_type in ['tp', 'sl', 'none', 'unknown']:
            subset = touched_first.get(tf_type, [])
            if subset:
                wins = len([c for c in subset if c.get('is_win')])
                pnl = sum(c.get('pnl', 0) for c in subset)
                wr = wins / len(subset) * 100 if subset else 0
                print(f'    先触及{tf_type:4s}: {len(subset):4d} ({len(subset)/len(contexts)*100:5.1f}%), WR {wr:5.1f}%, P&L ${pnl:>10.2f}')
        
        price_paths = defaultdict(list)
        for c in contexts:
            pp = c.get('price_path', 'unknown')
            price_paths[pp].append(c)
        
        print(f'\n  价格路径:')
        for path in ['favorable', 'adverse', 'unknown']:
            subset = price_paths.get(path, [])
            if subset:
                wins = len([c for c in subset if c.get('is_win')])
                pnl = sum(c.get('pnl', 0) for c in subset)
                wr = wins / len(subset) * 100 if subset else 0
                print(f'    {path:10s}: {len(subset):4d} ({len(subset)/len(contexts)*100:5.1f}%), WR {wr:5.1f}%, P&L ${pnl:>10.2f}')


def print_counter_trend_analysis(long_ctx: List[Dict], short_ctx: List[Dict]):
    """逆势交易分析"""
    print('\n' + '='*80)
    print('7. 逆势交易分析 (按周期)')
    print('='*80)
    
    for tf in ['4h', '1h']:
        print(f'\n--- {tf} 周期逆势分析 ---')
        
        for side, contexts in [('做多', long_ctx), ('做空', short_ctx)]:
            if not contexts:
                continue
            
            counter_key = f'is_counter_trend_{tf}'
            counter = [c for c in contexts if c.get(counter_key)]
            with_trend = [c for c in contexts if not c.get(counter_key)]
            
            print(f'\n  {side}:')
            
            if counter:
                wins = len([c for c in counter if c.get('is_win')])
                pnl = sum(c.get('pnl', 0) for c in counter)
                wr = wins / len(counter) * 100
                print(f'    逆势入场: {len(counter):4d} ({len(counter)/len(contexts)*100:5.1f}%), WR {wr:5.1f}%, P&L ${pnl:>10.2f}')
            
            if with_trend:
                wins = len([c for c in with_trend if c.get('is_win')])
                pnl = sum(c.get('pnl', 0) for c in with_trend)
                wr = wins / len(with_trend) * 100
                print(f'    顺势入场: {len(with_trend):4d} ({len(with_trend)/len(contexts)*100:5.1f}%), WR {wr:5.1f}%, P&L ${pnl:>10.2f}')


def print_trend_strength_analysis(long_ctx: List[Dict], short_ctx: List[Dict]):
    """趋势强度分析"""
    print('\n' + '='*80)
    print('8. 趋势强度分析')
    print('='*80)
    
    for tf in ['4h', '1h', '15m']:
        print(f'\n--- {tf} 周期趋势强度 ---')
        
        for side, contexts in [('做多', long_ctx), ('做空', short_ctx)]:
            if not contexts:
                continue
            
            print(f'\n  {side}:')
            
            trend_key = f'trend_{tf}'
            strength_key = f'trend_{tf}_strength'
            
            for direction in ['up', 'down', 'sideways']:
                for strength in ['strong', 'moderate', 'weak']:
                    subset = [c for c in contexts 
                              if c.get(trend_key) == direction and c.get(strength_key) == strength]
                    if subset:
                        wins = len([c for c in subset if c.get('is_win')])
                        pnl = sum(c.get('pnl', 0) for c in subset)
                        wr = wins / len(subset) * 100 if subset else 0
                        label = f'{direction}_{strength}'
                        print(f'    {label:15s}: {len(subset):4d} ({len(subset)/len(contexts)*100:5.1f}%), WR {wr:5.1f}%, P&L ${pnl:>10.2f}')


def summary_table(long_trades: List[Dict], short_trades: List[Dict]):
    """输出汇总对比表格"""
    print('\n' + '='*80)
    print('9. 核心数据汇总对比')
    print('='*80)
    
    long_wins = len([p for p in long_trades if p.get('is_win')])
    short_wins = len([p for p in short_trades if p.get('is_win')])
    long_wr = long_wins / len(long_trades) * 100
    short_wr = short_wins / len(short_trades) * 100
    
    long_pnl = sum(p.get('realized_pnl', 0) for p in long_trades)
    short_pnl = sum(p.get('realized_pnl', 0) for p in short_trades)
    
    long_sl = sum(p.get('sl_distance_percent', 0) for p in long_trades) / len(long_trades)
    short_sl = sum(p.get('sl_distance_percent', 0) for p in short_trades) / len(short_trades)
    long_tp = sum(p.get('tp_distance_percent', 0) for p in long_trades) / len(long_trades)
    short_tp = sum(p.get('tp_distance_percent', 0) for p in short_trades) / len(short_trades)
    
    print(f'''
┌─────────────────────────────────────────────────────────────────────────────┐
│                              核心数据对比                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  指标              │  做多                │  做空                │  差异     │
├─────────────────────────────────────────────────────────────────────────────┤
│  交易数量          │  {len(long_trades):>5d}               │  {len(short_trades):>5d}               │  {len(long_trades)-len(short_trades):>+5d}    │
│  胜率              │  {long_wr:>5.1f}%              │  {short_wr:>5.1f}%              │  {long_wr-short_wr:>+5.1f}%   │
│  总P&L             │  ${long_pnl:>9.2f}         │  ${short_pnl:>9.2f}         │  ${long_pnl-short_pnl:>+9.2f}│
│  平均止损距离      │  {long_sl:>5.3f}%              │  {short_sl:>5.3f}%              │  {long_sl-short_sl:>+5.3f}%   │
│  平均止盈距离      │  {long_tp:>5.3f}%              │  {short_tp:>5.3f}%              │  {long_tp-short_tp:>+5.3f}%   │
│  R:R (TP/SL)       │  {long_tp/long_sl:>5.2f}               │  {short_tp/short_sl:>5.2f}               │  {long_tp/long_sl - short_tp/short_sl:>+5.2f}    │
└─────────────────────────────────────────────────────────────────────────────┘
''')


def main():
    print('='*80)
    print('深度分析: 做多 vs 做空 决策差异 (多周期版)')
    print('='*80)
    
    positions = load_positions(DATA_FILE)
    print(f'\n加载交易记录: {len(positions)} 条')
    
    long_trades, short_trades = basic_analysis(positions)
    
    detailed_comparison(long_trades, short_trades)
    
    contexts = kline_context_analysis(positions)
    
    long_ctx = [c for c in contexts if c.get('side') == 'long']
    short_ctx = [c for c in contexts if c.get('side') == 'short']
    print_trend_strength_analysis(long_ctx, short_ctx)
    
    summary_table(long_trades, short_trades)
    
    print('\n' + '='*80)
    print('分析完成')
    print('='*80)


if __name__ == "__main__":
    main()
