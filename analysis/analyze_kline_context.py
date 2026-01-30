#!/usr/bin/env python3
"""
深入分析：
1. 盈利日期 vs 亏损日期的K线特征
2. 方向聚集问题
3. 开仓频率分析
"""

import json
from collections import defaultdict
from datetime import datetime, timedelta
import statistics
import urllib.request

BINANCE_API = "https://fapi.binance.com"

def load_positions(filepath: str):
    positions = []
    with open(filepath, 'r') as f:
        for line in f:
            if line.strip():
                data = json.loads(line)
                if data.get('type') == 'trade':
                    positions.append(data)
    return positions


def fetch_klines(symbol: str, interval: str, start_time: int, end_time: int):
    url = f"{BINANCE_API}/fapi/v1/klines?symbol={symbol}&interval={interval}&startTime={start_time}&endTime={end_time}&limit=1000"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"获取K线失败: {e}")
        return []


def get_daily_kline_features(symbol: str, date_str: str):
    """获取某一天的K线特征"""
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        start_ts = int(dt.timestamp() * 1000)
        end_ts = int((dt + timedelta(days=1)).timestamp() * 1000)
        
        klines_15m = fetch_klines(symbol, "15m", start_ts, end_ts)
        
        if len(klines_15m) < 10:
            return None
        
        opens = [float(k[1]) for k in klines_15m]
        highs = [float(k[2]) for k in klines_15m]
        lows = [float(k[3]) for k in klines_15m]
        closes = [float(k[4]) for k in klines_15m]
        volumes = [float(k[5]) for k in klines_15m]
        
        day_open = opens[0]
        day_close = closes[-1]
        day_high = max(highs)
        day_low = min(lows)
        
        day_change_pct = (day_close - day_open) / day_open * 100
        day_range_pct = (day_high - day_low) / day_low * 100
        
        bar_ranges = [(h - l) / l * 100 for h, l in zip(highs, lows)]
        avg_bar_range = statistics.mean(bar_ranges)
        max_bar_range = max(bar_ranges)
        
        trend_direction = "up" if day_close > day_open else "down"
        
        up_bars = sum(1 for o, c in zip(opens, closes) if c > o)
        down_bars = sum(1 for o, c in zip(opens, closes) if c < o)
        
        price_at_25 = closes[len(closes)//4]
        price_at_50 = closes[len(closes)//2]
        price_at_75 = closes[3*len(closes)//4]
        
        first_half_change = (price_at_50 - day_open) / day_open * 100
        second_half_change = (day_close - price_at_50) / price_at_50 * 100
        
        return {
            'day_change_pct': day_change_pct,
            'day_range_pct': day_range_pct,
            'avg_bar_range': avg_bar_range,
            'max_bar_range': max_bar_range,
            'trend_direction': trend_direction,
            'up_bars': up_bars,
            'down_bars': down_bars,
            'day_open': day_open,
            'day_close': day_close,
            'day_high': day_high,
            'day_low': day_low,
            'first_half_change': first_half_change,
            'second_half_change': second_half_change,
            'total_volume': sum(volumes),
        }
    except Exception as e:
        print(f"获取 {date_str} K线特征失败: {e}")
        return None


def analyze_profitable_vs_losing_days(positions):
    """分析盈利日 vs 亏损日的K线特征"""
    print("=" * 100)
    print("盈利日 vs 亏损日 K线特征对比")
    print("=" * 100)
    
    daily_stats = defaultdict(lambda: {'count': 0, 'wins': 0, 'pnl': 0, 'trades': []})
    
    for p in positions:
        entry_time = p.get('entry_time', '')
        if entry_time:
            try:
                dt = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
                date_key = dt.strftime('%Y-%m-%d')
                daily_stats[date_key]['count'] += 1
                if p.get('is_win', False):
                    daily_stats[date_key]['wins'] += 1
                daily_stats[date_key]['pnl'] += p.get('realized_pnl', 0)
                daily_stats[date_key]['trades'].append(p)
            except:
                pass
    
    profitable_days = [(d, s) for d, s in daily_stats.items() if s['pnl'] > 500]
    losing_days = [(d, s) for d, s in daily_stats.items() if s['pnl'] < -500]
    
    profitable_days.sort(key=lambda x: x[1]['pnl'], reverse=True)
    losing_days.sort(key=lambda x: x[1]['pnl'])
    
    print(f"\n盈利日 (P&L > $500): {len(profitable_days)} 天")
    print(f"亏损日 (P&L < -$500): {len(losing_days)} 天")
    
    print("\n" + "=" * 100)
    print("盈利日详情 (Top 10)")
    print("=" * 100)
    
    print(f"\n{'日期':<12} {'交易数':<8} {'胜率':<8} {'P&L':<12} {'多/空':<10} {'日涨跌%':<10} {'日振幅%':<10} {'趋势':<8}")
    print("-" * 90)
    
    for date, stats in profitable_days[:10]:
        winrate = stats['wins'] / stats['count'] * 100 if stats['count'] > 0 else 0
        longs = len([t for t in stats['trades'] if t.get('side') == 'long'])
        shorts = len([t for t in stats['trades'] if t.get('side') == 'short'])
        
        kline_features = get_daily_kline_features("ETHUSDT", date)
        if kline_features:
            print(f"{date:<12} {stats['count']:<8} {winrate:<7.1f}% ${stats['pnl']:<11.2f} {longs}/{shorts:<8} {kline_features['day_change_pct']:<9.2f}% {kline_features['day_range_pct']:<9.2f}% {kline_features['trend_direction']:<8}")
        else:
            print(f"{date:<12} {stats['count']:<8} {winrate:<7.1f}% ${stats['pnl']:<11.2f} {longs}/{shorts:<8} N/A")
    
    print("\n" + "=" * 100)
    print("亏损日详情 (Top 10)")
    print("=" * 100)
    
    print(f"\n{'日期':<12} {'交易数':<8} {'胜率':<8} {'P&L':<12} {'多/空':<10} {'日涨跌%':<10} {'日振幅%':<10} {'趋势':<8}")
    print("-" * 90)
    
    for date, stats in losing_days[:10]:
        winrate = stats['wins'] / stats['count'] * 100 if stats['count'] > 0 else 0
        longs = len([t for t in stats['trades'] if t.get('side') == 'long'])
        shorts = len([t for t in stats['trades'] if t.get('side') == 'short'])
        
        kline_features = get_daily_kline_features("ETHUSDT", date)
        if kline_features:
            print(f"{date:<12} {stats['count']:<8} {winrate:<7.1f}% ${stats['pnl']:<11.2f} {longs}/{shorts:<8} {kline_features['day_change_pct']:<9.2f}% {kline_features['day_range_pct']:<9.2f}% {kline_features['trend_direction']:<8}")
        else:
            print(f"{date:<12} {stats['count']:<8} {winrate:<7.1f}% ${stats['pnl']:<11.2f} {longs}/{shorts:<8} N/A")


def analyze_direction_clustering(positions):
    """分析方向聚集问题"""
    print("\n" + "=" * 100)
    print("方向聚集问题分析")
    print("=" * 100)
    
    daily_directions = defaultdict(lambda: {'long': 0, 'short': 0, 'trades': []})
    
    for p in positions:
        entry_time = p.get('entry_time', '')
        side = p.get('side', '')
        if entry_time and side:
            try:
                dt = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
                date_key = dt.strftime('%Y-%m-%d')
                daily_directions[date_key][side] += 1
                daily_directions[date_key]['trades'].append(p)
            except:
                pass
    
    highly_clustered_days = []
    for date, data in daily_directions.items():
        total = data['long'] + data['short']
        if total >= 10:
            dominant_pct = max(data['long'], data['short']) / total * 100
            if dominant_pct >= 80:
                highly_clustered_days.append({
                    'date': date,
                    'long': data['long'],
                    'short': data['short'],
                    'dominant_pct': dominant_pct,
                    'dominant_side': 'long' if data['long'] > data['short'] else 'short',
                    'trades': data['trades']
                })
    
    print(f"\n高度聚集日 (单方向占比 >= 80%): {len(highly_clustered_days)} 天")
    
    print(f"\n{'日期':<12} {'多':<6} {'空':<6} {'主导方向':<10} {'占比':<8} {'该方向胜率':<12} {'P&L':<12}")
    print("-" * 80)
    
    for day in sorted(highly_clustered_days, key=lambda x: x['date']):
        dominant_trades = [t for t in day['trades'] if t.get('side') == day['dominant_side']]
        dominant_wins = len([t for t in dominant_trades if t.get('is_win', False)])
        dominant_winrate = dominant_wins / len(dominant_trades) * 100 if dominant_trades else 0
        total_pnl = sum(t.get('realized_pnl', 0) for t in day['trades'])
        
        print(f"{day['date']:<12} {day['long']:<6} {day['short']:<6} {day['dominant_side']:<10} {day['dominant_pct']:<7.1f}% {dominant_winrate:<11.1f}% ${total_pnl:<11.2f}")
    
    print("\n" + "-" * 100)
    print("分析单日内方向变化情况")
    print("-" * 100)
    
    for date in ['2025-02-24', '2025-03-02', '2025-02-09', '2025-01-28']:
        if date in daily_directions:
            trades = sorted(daily_directions[date]['trades'], key=lambda x: x.get('entry_time', ''))
            
            print(f"\n{date} 交易序列 (前20笔):")
            print(f"{'时间':<20} {'方向':<8} {'入场价':<12} {'结果':<8} {'P&L':<10}")
            print("-" * 60)
            
            for t in trades[:20]:
                entry_time = t.get('entry_time', '')
                if entry_time:
                    try:
                        dt = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
                        time_str = dt.strftime('%H:%M')
                    except:
                        time_str = entry_time
                else:
                    time_str = 'N/A'
                
                result = "WIN" if t.get('is_win', False) else "LOSS"
                print(f"{time_str:<20} {t.get('side', ''):<8} ${t.get('entry_price', 0):<11.2f} {result:<8} ${t.get('realized_pnl', 0):<9.2f}")


def analyze_trade_frequency(positions):
    """分析开仓频率"""
    print("\n" + "=" * 100)
    print("开仓频率分析")
    print("=" * 100)
    
    hourly_counts = defaultdict(lambda: {'count': 0, 'wins': 0})
    
    sorted_positions = sorted(positions, key=lambda x: x.get('order_created_time', ''))
    
    time_gaps = []
    for i in range(1, len(sorted_positions)):
        prev_time = sorted_positions[i-1].get('order_created_time', '')
        curr_time = sorted_positions[i].get('order_created_time', '')
        
        if prev_time and curr_time:
            try:
                prev_dt = datetime.fromisoformat(prev_time.replace('Z', '+00:00'))
                curr_dt = datetime.fromisoformat(curr_time.replace('Z', '+00:00'))
                gap_minutes = (curr_dt - prev_dt).total_seconds() / 60
                if gap_minutes >= 0:
                    time_gaps.append(gap_minutes)
            except:
                pass
    
    print(f"\n挂单时间间隔统计:")
    if time_gaps:
        print(f"  平均间隔: {statistics.mean(time_gaps):.1f} 分钟")
        print(f"  中位数间隔: {statistics.median(time_gaps):.1f} 分钟")
        print(f"  最小间隔: {min(time_gaps):.1f} 分钟")
        print(f"  最大间隔: {max(time_gaps):.1f} 分钟")
        
        same_bar = len([g for g in time_gaps if g < 15])
        one_bar = len([g for g in time_gaps if 15 <= g < 30])
        two_bars = len([g for g in time_gaps if 30 <= g < 60])
        more = len([g for g in time_gaps if g >= 60])
        
        print(f"\n  间隔分布:")
        print(f"    同一根K线内 (<15min): {same_bar} ({same_bar/len(time_gaps)*100:.1f}%)")
        print(f"    1根K线间隔 (15-30min): {one_bar} ({one_bar/len(time_gaps)*100:.1f}%)")
        print(f"    2根K线间隔 (30-60min): {two_bars} ({two_bars/len(time_gaps)*100:.1f}%)")
        print(f"    更长间隔 (>60min): {more} ({more/len(time_gaps)*100:.1f}%)")
    
    daily_order_counts = defaultdict(int)
    for p in positions:
        order_time = p.get('order_created_time', '')
        if order_time:
            try:
                dt = datetime.fromisoformat(order_time.replace('Z', '+00:00'))
                date_key = dt.strftime('%Y-%m-%d')
                daily_order_counts[date_key] += 1
            except:
                pass
    
    counts = list(daily_order_counts.values())
    print(f"\n每日挂单数量统计:")
    if counts:
        print(f"  平均: {statistics.mean(counts):.1f}")
        print(f"  中位数: {statistics.median(counts):.1f}")
        print(f"  最大: {max(counts)}")
        print(f"  最小: {min(counts)}")


def analyze_same_price_orders(positions):
    """分析相同价格的挂单"""
    print("\n" + "=" * 100)
    print("相同挂单价格分析")
    print("=" * 100)
    
    price_groups = defaultdict(list)
    
    for p in positions:
        limit_price = p.get('limit_price', 0)
        side = p.get('side', '')
        if limit_price:
            key = f"{limit_price}_{side}"
            price_groups[key].append(p)
    
    duplicate_prices = [(k, v) for k, v in price_groups.items() if len(v) >= 3]
    duplicate_prices.sort(key=lambda x: len(x[1]), reverse=True)
    
    print(f"\n相同挂单价格 (>=3笔) 数量: {len(duplicate_prices)}")
    
    print(f"\n{'挂单价格':<15} {'方向':<8} {'数量':<8} {'胜率':<10} {'P&L':<12} {'时间跨度':<20}")
    print("-" * 80)
    
    for key, trades in duplicate_prices[:20]:
        price, side = key.rsplit('_', 1)
        wins = len([t for t in trades if t.get('is_win', False)])
        winrate = wins / len(trades) * 100
        pnl = sum(t.get('realized_pnl', 0) for t in trades)
        
        times = [t.get('order_created_time', '') for t in trades if t.get('order_created_time')]
        if times:
            times.sort()
            first = times[0][:16] if times[0] else 'N/A'
            last = times[-1][:16] if times[-1] else 'N/A'
            time_span = f"{first} ~ {last[-5:]}"
        else:
            time_span = 'N/A'
        
        print(f"${price:<14} {side:<8} {len(trades):<8} {winrate:<9.1f}% ${pnl:<11.2f} {time_span:<20}")


def analyze_workflow_trigger_pattern(positions):
    """分析 workflow 触发模式"""
    print("\n" + "=" * 100)
    print("Workflow 触发模式分析")
    print("=" * 100)
    
    workflow_runs = defaultdict(list)
    
    for p in positions:
        workflow_id = p.get('workflow_run_id', '')
        if workflow_id:
            workflow_runs[workflow_id].append(p)
    
    print(f"\n总 workflow 运行次数: {len(workflow_runs)}")
    print(f"总交易数: {len(positions)}")
    print(f"平均每次 workflow 产生交易数: {len(positions)/len(workflow_runs):.2f}")
    
    orders_per_workflow = [len(v) for v in workflow_runs.values()]
    print(f"\n每次 workflow 产生的订单数分布:")
    print(f"  1个订单: {orders_per_workflow.count(1)}")
    print(f"  2个订单: {orders_per_workflow.count(2)}")
    print(f"  3+个订单: {len([x for x in orders_per_workflow if x >= 3])}")
    
    multi_order_workflows = [(k, v) for k, v in workflow_runs.items() if len(v) >= 2]
    
    print(f"\n多订单 workflow 示例 (前10个):")
    for wf_id, trades in multi_order_workflows[:10]:
        sides = [t.get('side') for t in trades]
        prices = [t.get('limit_price') for t in trades]
        print(f"  {wf_id}: {len(trades)}单, 方向={sides}, 价格={prices}")


def analyze_consecutive_losses(positions):
    """分析连败序列"""
    print("\n" + "=" * 100)
    print("连败序列详细分析")
    print("=" * 100)
    
    sorted_positions = sorted(positions, key=lambda x: x.get('entry_time', ''))
    
    loss_streaks = []
    current_streak = []
    
    for p in sorted_positions:
        is_win = p.get('is_win', False)
        
        if not is_win:
            current_streak.append(p)
        else:
            if len(current_streak) >= 20:
                loss_streaks.append(current_streak.copy())
            current_streak = []
    
    if len(current_streak) >= 20:
        loss_streaks.append(current_streak)
    
    print(f"\n长连败序列 (>=20笔) 数量: {len(loss_streaks)}")
    
    for i, streak in enumerate(loss_streaks[:5]):
        print(f"\n连败序列 {i+1}: {len(streak)} 笔")
        
        first_trade = streak[0]
        last_trade = streak[-1]
        
        start_time = first_trade.get('entry_time', '')[:16]
        end_time = last_trade.get('entry_time', '')[:16]
        
        longs = len([t for t in streak if t.get('side') == 'long'])
        shorts = len([t for t in streak if t.get('side') == 'short'])
        
        total_loss = sum(t.get('realized_pnl', 0) for t in streak)
        
        prices = [t.get('entry_price', 0) for t in streak]
        price_range = f"${min(prices):.0f} - ${max(prices):.0f}"
        
        print(f"  时间: {start_time} ~ {end_time}")
        print(f"  方向: 多={longs}, 空={shorts}")
        print(f"  总亏损: ${total_loss:.2f}")
        print(f"  价格范围: {price_range}")
        
        print(f"  前10笔详情:")
        for t in streak[:10]:
            entry_time = t.get('entry_time', '')
            if entry_time:
                try:
                    dt = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
                    time_str = dt.strftime('%m-%d %H:%M')
                except:
                    time_str = entry_time[:16]
            else:
                time_str = 'N/A'
            
            print(f"    {time_str} | {t.get('side'):<5} | 入场${t.get('entry_price', 0):.0f} | SL${t.get('sl_price', 0):.0f} | 持仓{t.get('holding_bars', 0)}bars | ${t.get('realized_pnl', 0):.2f}")


def main():
    filepath = "/Users/bytedance/Desktop/crypto_agentx/analysis/all_positions.jsonl"
    positions = load_positions(filepath)
    
    print(f"加载了 {len(positions)} 条交易记录")
    
    analyze_profitable_vs_losing_days(positions)
    analyze_direction_clustering(positions)
    analyze_trade_frequency(positions)
    analyze_same_price_orders(positions)
    analyze_workflow_trigger_pattern(positions)
    analyze_consecutive_losses(positions)


if __name__ == "__main__":
    main()
