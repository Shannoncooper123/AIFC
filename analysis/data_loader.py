#!/usr/bin/env python3
"""
数据加载模块
- 加载交易记录
- 解析时间字段
- 提取基础统计信息
"""
import json
import sys
import bisect
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple

sys.path.insert(0, '/Users/bytedance/Desktop/crypto_agentx/backend')

INTERVAL_MINUTES = {
    '1m': 1, '3m': 3, '5m': 5, '15m': 15, '30m': 30,
    '1h': 60, '2h': 120, '4h': 240, '6h': 360, '12h': 720, '1d': 1440
}


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


def parse_datetime(time_str: str) -> Optional[datetime]:
    """解析ISO格式时间字符串"""
    if not time_str:
        return None
    try:
        return datetime.fromisoformat(time_str.replace('Z', '+00:00'))
    except:
        return None


def get_time_range_from_positions(positions: List[Dict]) -> Tuple[datetime, datetime]:
    """从交易记录中获取时间范围"""
    entry_times = []
    exit_times = []
    for p in positions:
        for field, lst in [('entry_time', entry_times), ('exit_time', exit_times)]:
            dt = parse_datetime(p.get(field, ''))
            if dt:
                lst.append(dt)
    
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


def enrich_positions_with_timing(positions: List[Dict]) -> List[Dict]:
    """
    为交易记录添加时间相关的计算字段
    - order_to_entry_minutes: 下单到成交的时间（分钟）
    - entry_to_exit_minutes: 持仓到平仓的时间（分钟）
    - total_duration_minutes: 总时长（分钟）
    """
    enriched = []
    for p in positions:
        p_copy = p.copy()
        
        order_created_time = parse_datetime(p.get('order_created_time', ''))
        entry_time = parse_datetime(p.get('entry_time', ''))
        exit_time = parse_datetime(p.get('exit_time', ''))
        
        if order_created_time and entry_time:
            p_copy['order_to_entry_minutes'] = (entry_time - order_created_time).total_seconds() / 60
        else:
            p_copy['order_to_entry_minutes'] = None
        
        if entry_time and exit_time:
            p_copy['entry_to_exit_minutes'] = (exit_time - entry_time).total_seconds() / 60
        else:
            p_copy['entry_to_exit_minutes'] = None
        
        if order_created_time and exit_time:
            p_copy['total_duration_minutes'] = (exit_time - order_created_time).total_seconds() / 60
        else:
            p_copy['total_duration_minutes'] = None
        
        enriched.append(p_copy)
    
    return enriched


class KlineCache:
    """K线数据缓存 - 批量预加载多周期数据"""
    
    def __init__(self):
        self._cache: Dict[str, Dict[str, List[Dict]]] = {}
        self._timestamps: Dict[str, Dict[str, List[int]]] = {}
    
    def preload(self, symbols: List[str], start_time: datetime, end_time: datetime, 
                intervals: List[str] = None, buffer_bars: int = 200):
        """批量预加载多周期K线数据"""
        from modules.monitor.clients.binance_rest import BinanceRestClient
        
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
