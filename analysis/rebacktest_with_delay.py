#!/usr/bin/env python3
"""
重回测脚本 - 模拟真实交易延迟

问题背景：
当前回测直接使用K线收盘价开始模拟限价单成交，但实盘中从workflow运行到agent创建限价单
平均有3分钟延迟。这导致回测中"即时成交"占比过高（72.4%），不符合真实场景。

解决方案：
1. 读取原始回测结果 all_positions.jsonl
2. 对每个限价单，将开始模拟时间往后推移3个1分钟K线（模拟分析延迟）
3. 使用1分钟K线重新模拟限价单成交和TP/SL触发
4. 输出新的回测结果用于对比分析

使用方法：
    python rebacktest_with_delay.py [--delay-minutes 3] [--data all_positions.jsonl]
"""
import sys
import os
import argparse
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend'))

from data_loader import load_positions, parse_datetime


@dataclass
class DelayedTradeResult:
    """延迟重回测的交易结果"""
    original_trade_id: str
    symbol: str
    side: str
    
    original_order_created_time: datetime
    original_entry_time: datetime
    original_exit_time: datetime
    original_exit_type: str
    original_realized_pnl: float
    
    delayed_order_created_time: datetime
    delayed_entry_time: Optional[datetime]
    delayed_exit_time: Optional[datetime]
    delayed_exit_type: Optional[str]
    delayed_realized_pnl: Optional[float]
    
    limit_price: float
    tp_price: float
    sl_price: float
    margin_usdt: float
    leverage: int
    
    delay_minutes: int
    status: str
    status_reason: str = ""
    
    order_to_entry_minutes_original: Optional[float] = None
    order_to_entry_minutes_delayed: Optional[float] = None
    entry_to_exit_minutes_original: Optional[float] = None
    entry_to_exit_minutes_delayed: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "trade",
            "original_trade_id": self.original_trade_id,
            "symbol": self.symbol,
            "side": self.side,
            "original_order_created_time": self.original_order_created_time.isoformat(),
            "original_entry_time": self.original_entry_time.isoformat(),
            "original_exit_time": self.original_exit_time.isoformat(),
            "original_exit_type": self.original_exit_type,
            "original_realized_pnl": round(self.original_realized_pnl, 4),
            "delayed_order_created_time": self.delayed_order_created_time.isoformat(),
            "delayed_entry_time": self.delayed_entry_time.isoformat() if self.delayed_entry_time else None,
            "delayed_exit_time": self.delayed_exit_time.isoformat() if self.delayed_exit_time else None,
            "delayed_exit_type": self.delayed_exit_type,
            "delayed_realized_pnl": round(self.delayed_realized_pnl, 4) if self.delayed_realized_pnl is not None else None,
            "limit_price": self.limit_price,
            "tp_price": self.tp_price,
            "sl_price": self.sl_price,
            "margin_usdt": self.margin_usdt,
            "leverage": self.leverage,
            "delay_minutes": self.delay_minutes,
            "status": self.status,
            "status_reason": self.status_reason,
            "order_to_entry_minutes_original": round(self.order_to_entry_minutes_original, 2) if self.order_to_entry_minutes_original else None,
            "order_to_entry_minutes_delayed": round(self.order_to_entry_minutes_delayed, 2) if self.order_to_entry_minutes_delayed else None,
            "entry_to_exit_minutes_original": round(self.entry_to_exit_minutes_original, 2) if self.entry_to_exit_minutes_original else None,
            "entry_to_exit_minutes_delayed": round(self.entry_to_exit_minutes_delayed, 2) if self.entry_to_exit_minutes_delayed else None,
            "is_win": self.delayed_realized_pnl > 0 if self.delayed_realized_pnl is not None else None,
        }


class KlineDataProvider:
    """K线数据提供者 - 从本地parquet缓存加载"""
    
    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
        self._cache: Dict[str, Dict[str, List[Dict]]] = {}
        self._index: Dict[str, Dict[str, List[int]]] = {}
    
    def load_symbol(self, symbol: str, intervals: List[str] = None):
        """加载指定交易对的K线数据"""
        if intervals is None:
            intervals = ['1m']
        
        symbol = symbol.upper()
        symbol_dir = os.path.join(self.cache_dir, symbol)
        
        if not os.path.exists(symbol_dir):
            print(f"警告: 未找到 {symbol} 的K线缓存目录: {symbol_dir}")
            return
        
        if symbol not in self._cache:
            self._cache[symbol] = {}
            self._index[symbol] = {}
        
        for interval in intervals:
            parquet_path = os.path.join(symbol_dir, f"{interval}.parquet")
            if not os.path.exists(parquet_path):
                print(f"警告: 未找到 {symbol} {interval} 的parquet文件")
                continue
            
            try:
                import pandas as pd
                df = pd.read_parquet(parquet_path)
                
                klines = []
                for _, row in df.iterrows():
                    klines.append({
                        'timestamp': int(row['timestamp']),
                        'open': float(row['open']),
                        'high': float(row['high']),
                        'low': float(row['low']),
                        'close': float(row['close']),
                        'volume': float(row['volume']) if 'volume' in row else 0.0
                    })
                
                klines.sort(key=lambda x: x['timestamp'])
                self._cache[symbol][interval] = klines
                self._index[symbol][interval] = [k['timestamp'] for k in klines]
                
                print(f"  加载 {symbol} {interval}: {len(klines)} 根K线")
                
            except Exception as e:
                print(f"加载 {symbol} {interval} 失败: {e}")
    
    def get_kline_at_time(self, symbol: str, interval: str, target_time: datetime) -> Optional[Dict]:
        """获取指定时间点的K线"""
        import bisect
        
        symbol = symbol.upper()
        if symbol not in self._cache or interval not in self._cache[symbol]:
            return None
        
        klines = self._cache[symbol][interval]
        timestamps = self._index[symbol][interval]
        
        if not klines:
            return None
        
        target_ts = int(target_time.timestamp() * 1000)
        
        idx = bisect.bisect_right(timestamps, target_ts) - 1
        if idx < 0:
            return None
        
        kline = klines[idx]
        interval_ms = self._get_interval_ms(interval)
        
        if kline['timestamp'] <= target_ts < kline['timestamp'] + interval_ms:
            return kline
        
        return None
    
    def get_klines_after(self, symbol: str, interval: str, start_time: datetime, 
                         limit: int = 1000) -> List[Dict]:
        """获取指定时间之后的K线"""
        import bisect
        
        symbol = symbol.upper()
        if symbol not in self._cache or interval not in self._cache[symbol]:
            return []
        
        klines = self._cache[symbol][interval]
        timestamps = self._index[symbol][interval]
        
        if not klines:
            return []
        
        start_ts = int(start_time.timestamp() * 1000)
        start_idx = bisect.bisect_left(timestamps, start_ts)
        
        end_idx = min(start_idx + limit, len(klines))
        return klines[start_idx:end_idx]
    
    def _get_interval_ms(self, interval: str) -> int:
        """获取K线周期的毫秒数"""
        interval_map = {
            '1m': 60 * 1000,
            '3m': 3 * 60 * 1000,
            '5m': 5 * 60 * 1000,
            '15m': 15 * 60 * 1000,
            '30m': 30 * 60 * 1000,
            '1h': 60 * 60 * 1000,
            '4h': 4 * 60 * 60 * 1000,
            '1d': 24 * 60 * 60 * 1000,
        }
        return interval_map.get(interval, 60 * 1000)


class DelayedPositionSimulator:
    """延迟仓位模拟器 - 模拟带延迟的限价单成交和TP/SL触发"""
    
    def __init__(self, kline_provider: KlineDataProvider, delay_minutes: int = 3):
        self.kline_provider = kline_provider
        self.delay_minutes = delay_minutes
        self.max_simulation_minutes = 1000 * 15
    
    def simulate_trade(self, position: Dict) -> DelayedTradeResult:
        """
        模拟单个交易，加入延迟后重新计算结果
        
        流程：
        1. 原始order_created_time + delay_minutes = 新的开始模拟时间
        2. 从新的开始时间开始，用1m K线检查限价单是否成交
        3. 如果成交，继续用1m K线检查TP/SL是否触发
        4. 返回新的交易结果
        """
        symbol = position.get('symbol', 'UNKNOWN')
        side = position.get('side', '')
        
        original_order_created_time = parse_datetime(position.get('order_created_time', ''))
        original_entry_time = parse_datetime(position.get('entry_time', ''))
        original_exit_time = parse_datetime(position.get('exit_time', ''))
        
        if not original_order_created_time:
            original_order_created_time = original_entry_time
        
        limit_price = position.get('limit_price', position.get('entry_price', 0))
        tp_price = position.get('tp_price', position.get('original_tp_price', 0))
        sl_price = position.get('sl_price', position.get('original_sl_price', 0))
        margin_usdt = position.get('margin_usdt', 500)
        leverage = position.get('leverage', 10)
        
        order_to_entry_original = None
        if original_order_created_time and original_entry_time:
            order_to_entry_original = (original_entry_time - original_order_created_time).total_seconds() / 60
        
        entry_to_exit_original = None
        if original_entry_time and original_exit_time:
            entry_to_exit_original = (original_exit_time - original_entry_time).total_seconds() / 60
        
        delayed_start_time = original_order_created_time + timedelta(minutes=self.delay_minutes)
        
        filled_time, filled_price = self._simulate_limit_order_fill(
            symbol, side, limit_price, delayed_start_time
        )
        
        if filled_time is None:
            return DelayedTradeResult(
                original_trade_id=position.get('trade_id', ''),
                symbol=symbol,
                side=side,
                original_order_created_time=original_order_created_time,
                original_entry_time=original_entry_time,
                original_exit_time=original_exit_time,
                original_exit_type=position.get('exit_type', ''),
                original_realized_pnl=position.get('realized_pnl', 0),
                delayed_order_created_time=delayed_start_time,
                delayed_entry_time=None,
                delayed_exit_time=None,
                delayed_exit_type=None,
                delayed_realized_pnl=None,
                limit_price=limit_price,
                tp_price=tp_price,
                sl_price=sl_price,
                margin_usdt=margin_usdt,
                leverage=leverage,
                delay_minutes=self.delay_minutes,
                status="not_filled",
                status_reason="限价单在模拟期间未成交",
                order_to_entry_minutes_original=order_to_entry_original,
                order_to_entry_minutes_delayed=None,
                entry_to_exit_minutes_original=entry_to_exit_original,
                entry_to_exit_minutes_delayed=None,
            )
        
        exit_time, exit_type, exit_price = self._simulate_tp_sl(
            symbol, side, filled_time, filled_price, tp_price, sl_price
        )
        
        if exit_time is None:
            return DelayedTradeResult(
                original_trade_id=position.get('trade_id', ''),
                symbol=symbol,
                side=side,
                original_order_created_time=original_order_created_time,
                original_entry_time=original_entry_time,
                original_exit_time=original_exit_time,
                original_exit_type=position.get('exit_type', ''),
                original_realized_pnl=position.get('realized_pnl', 0),
                delayed_order_created_time=delayed_start_time,
                delayed_entry_time=filled_time,
                delayed_exit_time=None,
                delayed_exit_type="timeout",
                delayed_realized_pnl=0,
                limit_price=limit_price,
                tp_price=tp_price,
                sl_price=sl_price,
                margin_usdt=margin_usdt,
                leverage=leverage,
                delay_minutes=self.delay_minutes,
                status="timeout",
                status_reason="TP/SL在模拟期间未触发",
                order_to_entry_minutes_original=order_to_entry_original,
                order_to_entry_minutes_delayed=(filled_time - delayed_start_time).total_seconds() / 60,
                entry_to_exit_minutes_original=entry_to_exit_original,
                entry_to_exit_minutes_delayed=None,
            )
        
        realized_pnl = self._calculate_pnl(
            side, filled_price, exit_price, margin_usdt, leverage
        )
        
        order_to_entry_delayed = (filled_time - delayed_start_time).total_seconds() / 60
        entry_to_exit_delayed = (exit_time - filled_time).total_seconds() / 60
        
        return DelayedTradeResult(
            original_trade_id=position.get('trade_id', ''),
            symbol=symbol,
            side=side,
            original_order_created_time=original_order_created_time,
            original_entry_time=original_entry_time,
            original_exit_time=original_exit_time,
            original_exit_type=position.get('exit_type', ''),
            original_realized_pnl=position.get('realized_pnl', 0),
            delayed_order_created_time=delayed_start_time,
            delayed_entry_time=filled_time,
            delayed_exit_time=exit_time,
            delayed_exit_type=exit_type,
            delayed_realized_pnl=realized_pnl,
            limit_price=limit_price,
            tp_price=tp_price,
            sl_price=sl_price,
            margin_usdt=margin_usdt,
            leverage=leverage,
            delay_minutes=self.delay_minutes,
            status="completed",
            status_reason="",
            order_to_entry_minutes_original=order_to_entry_original,
            order_to_entry_minutes_delayed=order_to_entry_delayed,
            entry_to_exit_minutes_original=entry_to_exit_original,
            entry_to_exit_minutes_delayed=entry_to_exit_delayed,
        )
    
    def _simulate_limit_order_fill(
        self, 
        symbol: str, 
        side: str, 
        limit_price: float, 
        start_time: datetime
    ) -> Tuple[Optional[datetime], Optional[float]]:
        """
        模拟限价单成交
        
        做多限价单：价格 <= limit_price 时成交
        做空限价单：价格 >= limit_price 时成交
        """
        klines = self.kline_provider.get_klines_after(symbol, '1m', start_time, self.max_simulation_minutes)
        
        for kline in klines:
            kline_time = datetime.fromtimestamp(kline['timestamp'] / 1000, tz=timezone.utc)
            
            if side == 'long':
                if kline['low'] <= limit_price:
                    return kline_time, limit_price
            else:
                if kline['high'] >= limit_price:
                    return kline_time, limit_price
        
        return None, None
    
    def _simulate_tp_sl(
        self,
        symbol: str,
        side: str,
        entry_time: datetime,
        entry_price: float,
        tp_price: float,
        sl_price: float
    ) -> Tuple[Optional[datetime], Optional[str], Optional[float]]:
        """
        模拟TP/SL触发
        
        做多：
        - TP: high >= tp_price
        - SL: low <= sl_price
        
        做空：
        - TP: low <= tp_price
        - SL: high >= sl_price
        """
        start_time = entry_time + timedelta(minutes=1)
        klines = self.kline_provider.get_klines_after(symbol, '1m', start_time, self.max_simulation_minutes)
        
        for kline in klines:
            kline_time = datetime.fromtimestamp(kline['timestamp'] / 1000, tz=timezone.utc)
            high = kline['high']
            low = kline['low']
            
            if side == 'long':
                if tp_price and high >= tp_price:
                    return kline_time, 'tp', tp_price
                if sl_price and low <= sl_price:
                    return kline_time, 'sl', sl_price
            else:
                if tp_price and low <= tp_price:
                    return kline_time, 'tp', tp_price
                if sl_price and high >= sl_price:
                    return kline_time, 'sl', sl_price
        
        return None, None, None
    
    def _calculate_pnl(
        self,
        side: str,
        entry_price: float,
        exit_price: float,
        margin_usdt: float,
        leverage: int
    ) -> float:
        """计算盈亏"""
        notional = margin_usdt * leverage
        qty = notional / entry_price
        
        if side == 'long':
            pnl = (exit_price - entry_price) * qty
        else:
            pnl = (entry_price - exit_price) * qty
        
        fee_rate = 0.00045
        fees = notional * fee_rate * 2
        
        return pnl - fees


def run_delayed_backtest(
    positions: List[Dict],
    kline_cache_dir: str,
    delay_minutes: int = 3
) -> List[DelayedTradeResult]:
    """运行延迟回测"""
    
    print(f"\n{'='*80}")
    print(f"延迟回测 - 模拟 {delay_minutes} 分钟分析延迟")
    print(f"{'='*80}")
    
    symbols = set()
    for p in positions:
        symbol = p.get('symbol', '')
        if symbol:
            symbols.add(symbol.upper())
    
    print(f"\n加载K线数据...")
    kline_provider = KlineDataProvider(kline_cache_dir)
    for symbol in symbols:
        kline_provider.load_symbol(symbol, ['1m'])
    
    print(f"\n开始模拟 {len(positions)} 个交易...")
    simulator = DelayedPositionSimulator(kline_provider, delay_minutes)
    
    results = []
    for i, position in enumerate(positions):
        result = simulator.simulate_trade(position)
        results.append(result)
        
        if (i + 1) % 1000 == 0:
            print(f"  已处理 {i + 1}/{len(positions)} 个交易")
    
    print(f"\n模拟完成，共 {len(results)} 个结果")
    
    return results


def analyze_delayed_results(results: List[DelayedTradeResult]):
    """分析延迟回测结果"""
    
    print(f"\n{'='*80}")
    print("延迟回测结果分析")
    print(f"{'='*80}")
    
    completed = [r for r in results if r.status == 'completed']
    not_filled = [r for r in results if r.status == 'not_filled']
    timeout = [r for r in results if r.status == 'timeout']
    
    print(f"\n--- 状态统计 ---")
    print(f"  总交易数: {len(results)}")
    print(f"  完成: {len(completed)} ({len(completed)/len(results)*100:.1f}%)")
    print(f"  未成交: {len(not_filled)} ({len(not_filled)/len(results)*100:.1f}%)")
    print(f"  超时: {len(timeout)} ({len(timeout)/len(results)*100:.1f}%)")
    
    if not completed:
        print("\n无完成的交易，跳过详细分析")
        return
    
    original_wins = len([r for r in completed if r.original_realized_pnl > 0])
    original_wr = original_wins / len(completed) * 100
    original_pnl = sum(r.original_realized_pnl for r in completed)
    
    delayed_wins = len([r for r in completed if r.delayed_realized_pnl and r.delayed_realized_pnl > 0])
    delayed_wr = delayed_wins / len(completed) * 100
    delayed_pnl = sum(r.delayed_realized_pnl for r in completed if r.delayed_realized_pnl)
    
    print(f"\n--- 原始 vs 延迟对比 (仅完成的交易) ---")
    print(f"  原始胜率: {original_wr:.1f}%")
    print(f"  延迟胜率: {delayed_wr:.1f}%")
    print(f"  胜率变化: {delayed_wr - original_wr:+.1f}%")
    print(f"\n  原始总P&L: ${original_pnl:.2f}")
    print(f"  延迟总P&L: ${delayed_pnl:.2f}")
    print(f"  P&L变化: ${delayed_pnl - original_pnl:+.2f}")
    
    original_order_to_entry = [r.order_to_entry_minutes_original for r in completed if r.order_to_entry_minutes_original is not None]
    delayed_order_to_entry = [r.order_to_entry_minutes_delayed for r in completed if r.order_to_entry_minutes_delayed is not None]
    
    if original_order_to_entry and delayed_order_to_entry:
        print(f"\n--- 等待成交时间对比 ---")
        print(f"  原始平均: {sum(original_order_to_entry)/len(original_order_to_entry):.1f} 分钟")
        print(f"  延迟平均: {sum(delayed_order_to_entry)/len(delayed_order_to_entry):.1f} 分钟")
    
    duration_buckets = [
        (0, 5, '即时成交 (≤5分钟)'),
        (5, 15, '快速成交 (5-15分钟)'),
        (15, 30, '正常成交 (15-30分钟)'),
        (30, 60, '较慢成交 (30-60分钟)'),
        (60, 120, '慢速成交 (1-2小时)'),
        (120, 240, '很慢成交 (2-4小时)'),
        (240, float('inf'), '超长等待 (>4小时)')
    ]
    
    print(f"\n--- 原始等待时间分布 ---")
    for min_m, max_m, label in duration_buckets:
        subset = [r for r in completed if r.order_to_entry_minutes_original is not None 
                  and min_m <= r.order_to_entry_minutes_original < max_m]
        if subset:
            count = len(subset)
            pct = count / len(completed) * 100
            wins = len([r for r in subset if r.original_realized_pnl > 0])
            wr = wins / count * 100
            pnl = sum(r.original_realized_pnl for r in subset)
            bar = '█' * int(pct / 2)
            print(f'  {label:25s}: {count:4d} ({pct:5.1f}%) WR {wr:5.1f}% P&L ${pnl:>9.2f} {bar}')
    
    print(f"\n--- 延迟后等待时间分布 ---")
    for min_m, max_m, label in duration_buckets:
        subset = [r for r in completed if r.order_to_entry_minutes_delayed is not None 
                  and min_m <= r.order_to_entry_minutes_delayed < max_m]
        if subset:
            count = len(subset)
            pct = count / len(completed) * 100
            wins = len([r for r in subset if r.delayed_realized_pnl and r.delayed_realized_pnl > 0])
            wr = wins / count * 100
            pnl = sum(r.delayed_realized_pnl for r in subset if r.delayed_realized_pnl)
            bar = '█' * int(pct / 2)
            print(f'  {label:25s}: {count:4d} ({pct:5.1f}%) WR {wr:5.1f}% P&L ${pnl:>9.2f} {bar}')
    
    outcome_changes = {
        'tp_to_tp': 0,
        'tp_to_sl': 0,
        'sl_to_tp': 0,
        'sl_to_sl': 0,
    }
    
    for r in completed:
        orig = r.original_exit_type
        delayed = r.delayed_exit_type
        if orig and delayed:
            key = f"{orig}_to_{delayed}"
            if key in outcome_changes:
                outcome_changes[key] += 1
    
    print(f"\n--- 结果变化矩阵 ---")
    print(f"  TP→TP: {outcome_changes['tp_to_tp']:4d}")
    print(f"  TP→SL: {outcome_changes['tp_to_sl']:4d}")
    print(f"  SL→TP: {outcome_changes['sl_to_tp']:4d}")
    print(f"  SL→SL: {outcome_changes['sl_to_sl']:4d}")
    
    print(f"\n--- 按方向分析 ---")
    for side_name, side_key in [('做多', 'long'), ('做空', 'short')]:
        side_data = [r for r in completed if r.side == side_key]
        if side_data:
            orig_wins = len([r for r in side_data if r.original_realized_pnl > 0])
            orig_wr = orig_wins / len(side_data) * 100
            orig_pnl = sum(r.original_realized_pnl for r in side_data)
            
            delayed_wins = len([r for r in side_data if r.delayed_realized_pnl and r.delayed_realized_pnl > 0])
            delayed_wr = delayed_wins / len(side_data) * 100
            delayed_pnl = sum(r.delayed_realized_pnl for r in side_data if r.delayed_realized_pnl)
            
            print(f"\n  {side_name} ({len(side_data)} 笔):")
            print(f"    原始: WR {orig_wr:.1f}%, P&L ${orig_pnl:.2f}")
            print(f"    延迟: WR {delayed_wr:.1f}%, P&L ${delayed_pnl:.2f}")
            print(f"    变化: WR {delayed_wr - orig_wr:+.1f}%, P&L ${delayed_pnl - orig_pnl:+.2f}")


def save_results(results: List[DelayedTradeResult], output_path: str):
    """保存结果到JSONL文件"""
    with open(output_path, 'w') as f:
        header = {
            "type": "header",
            "description": "延迟回测结果",
            "delay_minutes": results[0].delay_minutes if results else 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        f.write(json.dumps(header, ensure_ascii=False) + '\n')
        
        for result in results:
            f.write(json.dumps(result.to_dict(), ensure_ascii=False) + '\n')
    
    print(f"\n结果已保存到: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='延迟回测 - 模拟真实交易延迟')
    parser.add_argument('--delay-minutes', type=int, default=3, 
                        help='延迟分钟数（默认3分钟）')
    parser.add_argument('--data', type=str, 
                        default='/Users/bytedance/Desktop/crypto_agentx/analysis/all_positions.jsonl',
                        help='原始回测数据文件路径')
    parser.add_argument('--kline-cache', type=str,
                        default='/Users/bytedance/Desktop/crypto_agentx/backend/modules/data/kline_cache',
                        help='K线缓存目录')
    parser.add_argument('--output', type=str, default=None,
                        help='输出文件路径（默认为 delayed_positions_{delay}m.jsonl）')
    args = parser.parse_args()
    
    if args.output is None:
        output_dir = os.path.dirname(args.data)
        args.output = os.path.join(output_dir, f'delayed_positions_{args.delay_minutes}m.jsonl')
    
    print(f"{'='*80}")
    print("延迟回测工具")
    print(f"{'='*80}")
    print(f"延迟时间: {args.delay_minutes} 分钟")
    print(f"数据文件: {args.data}")
    print(f"K线缓存: {args.kline_cache}")
    print(f"输出文件: {args.output}")
    
    positions = load_positions(args.data)
    print(f"\n加载交易记录: {len(positions)} 条")
    
    results = run_delayed_backtest(
        positions=positions,
        kline_cache_dir=args.kline_cache,
        delay_minutes=args.delay_minutes
    )
    
    analyze_delayed_results(results)
    
    save_results(results, args.output)
    
    print(f"\n{'='*80}")
    print("延迟回测完成")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
