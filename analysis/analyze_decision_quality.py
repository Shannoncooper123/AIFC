#!/usr/bin/env python3
"""
分析 Agent 决策质量
核心问题：Agent 的方向判断与市场实际走势的关系
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


def analyze_direction_vs_future_price(positions):
    """分析 agent 方向判断与未来价格走势的关系"""
    print("=" * 100)
    print("Agent 方向判断 vs 未来价格走势")
    print("=" * 100)
    
    results = {
        'long_price_up': {'count': 0, 'wins': 0, 'pnl': 0},
        'long_price_down': {'count': 0, 'wins': 0, 'pnl': 0},
        'short_price_up': {'count': 0, 'wins': 0, 'pnl': 0},
        'short_price_down': {'count': 0, 'wins': 0, 'pnl': 0},
    }
    
    for p in positions:
        side = p.get('side', '')
        entry_price = p.get('entry_price', 0)
        exit_price = p.get('exit_price', 0)
        is_win = p.get('is_win', False)
        pnl = p.get('realized_pnl', 0)
        
        if entry_price and exit_price:
            price_moved = 'up' if exit_price > entry_price else 'down'
            key = f"{side}_price_{price_moved}"
            
            results[key]['count'] += 1
            if is_win:
                results[key]['wins'] += 1
            results[key]['pnl'] += pnl
    
    print(f"\n{'组合':<25} {'数量':<10} {'胜率':<10} {'P&L':<15}")
    print("-" * 60)
    for key, data in results.items():
        if data['count'] > 0:
            winrate = data['wins'] / data['count'] * 100
            print(f"{key:<25} {data['count']:<10} {winrate:<9.1f}% ${data['pnl']:<14.2f}")
    
    total = sum(d['count'] for d in results.values())
    correct_direction = results['long_price_up']['count'] + results['short_price_down']['count']
    wrong_direction = results['long_price_down']['count'] + results['short_price_up']['count']
    
    print(f"\n方向判断正确率: {correct_direction}/{total} = {correct_direction/total*100:.1f}%")
    print(f"方向判断错误率: {wrong_direction}/{total} = {wrong_direction/total*100:.1f}%")


def analyze_entry_timing(positions):
    """分析入场时机：入场后价格先往哪个方向走"""
    print("\n" + "=" * 100)
    print("入场时机分析：入场后价格的初始走势")
    print("=" * 100)
    
    timing_stats = {
        'long': {'immediate_up': 0, 'immediate_down': 0, 'total': 0},
        'short': {'immediate_up': 0, 'immediate_down': 0, 'total': 0},
    }
    
    for p in positions:
        side = p.get('side', '')
        entry_price = p.get('entry_price', 0)
        sl_price = p.get('sl_price', 0)
        tp_price = p.get('tp_price', 0)
        exit_price = p.get('exit_price', 0)
        exit_type = p.get('exit_type', '')
        holding_bars = p.get('holding_bars', 0)
        
        if side and entry_price:
            timing_stats[side]['total'] += 1
            
            if holding_bars <= 3:
                if exit_type == 'sl':
                    if side == 'long':
                        timing_stats[side]['immediate_down'] += 1
                    else:
                        timing_stats[side]['immediate_up'] += 1
                elif exit_type == 'tp':
                    if side == 'long':
                        timing_stats[side]['immediate_up'] += 1
                    else:
                        timing_stats[side]['immediate_down'] += 1
    
    print(f"\n做多入场后 (3 bars 内):")
    long_total = timing_stats['long']['immediate_up'] + timing_stats['long']['immediate_down']
    if long_total > 0:
        print(f"  价格立即上涨 (正确): {timing_stats['long']['immediate_up']} ({timing_stats['long']['immediate_up']/long_total*100:.1f}%)")
        print(f"  价格立即下跌 (错误): {timing_stats['long']['immediate_down']} ({timing_stats['long']['immediate_down']/long_total*100:.1f}%)")
    
    print(f"\n做空入场后 (3 bars 内):")
    short_total = timing_stats['short']['immediate_up'] + timing_stats['short']['immediate_down']
    if short_total > 0:
        print(f"  价格立即下跌 (正确): {timing_stats['short']['immediate_down']} ({timing_stats['short']['immediate_down']/short_total*100:.1f}%)")
        print(f"  价格立即上涨 (错误): {timing_stats['short']['immediate_up']} ({timing_stats['short']['immediate_up']/short_total*100:.1f}%)")


def analyze_sl_tp_distance_effectiveness(positions):
    """分析止损止盈距离的有效性"""
    print("\n" + "=" * 100)
    print("止损止盈距离有效性分析")
    print("=" * 100)
    
    sl_hit_distances = []
    tp_hit_distances = []
    
    for p in positions:
        entry_price = p.get('entry_price', 0)
        sl_price = p.get('sl_price', 0)
        tp_price = p.get('tp_price', 0)
        exit_type = p.get('exit_type', '')
        side = p.get('side', '')
        
        if entry_price and sl_price and tp_price:
            if side == 'long':
                sl_dist = (entry_price - sl_price) / entry_price * 100
                tp_dist = (tp_price - entry_price) / entry_price * 100
            else:
                sl_dist = (sl_price - entry_price) / entry_price * 100
                tp_dist = (entry_price - tp_price) / entry_price * 100
            
            if exit_type == 'sl':
                sl_hit_distances.append(sl_dist)
            elif exit_type == 'tp':
                tp_hit_distances.append(tp_dist)
    
    print(f"\n止损触发时的止损距离:")
    if sl_hit_distances:
        print(f"  数量: {len(sl_hit_distances)}")
        print(f"  平均: {statistics.mean(sl_hit_distances):.2f}%")
        print(f"  中位数: {statistics.median(sl_hit_distances):.2f}%")
        print(f"  最小: {min(sl_hit_distances):.2f}%")
        print(f"  最大: {max(sl_hit_distances):.2f}%")
    
    print(f"\n止盈触发时的止盈距离:")
    if tp_hit_distances:
        print(f"  数量: {len(tp_hit_distances)}")
        print(f"  平均: {statistics.mean(tp_hit_distances):.2f}%")
        print(f"  中位数: {statistics.median(tp_hit_distances):.2f}%")
        print(f"  最小: {min(tp_hit_distances):.2f}%")
        print(f"  最大: {max(tp_hit_distances):.2f}%")
    
    print(f"\n止损/止盈触发比例: {len(sl_hit_distances)}:{len(tp_hit_distances)} = {len(sl_hit_distances)/(len(sl_hit_distances)+len(tp_hit_distances))*100:.1f}%:{len(tp_hit_distances)/(len(sl_hit_distances)+len(tp_hit_distances))*100:.1f}%")


def analyze_price_at_order_vs_entry(positions):
    """分析挂单时价格与入场价的关系"""
    print("\n" + "=" * 100)
    print("挂单价格 vs 当时市场价格分析")
    print("=" * 100)
    
    limit_vs_entry = []
    
    for p in positions:
        limit_price = p.get('limit_price', 0)
        entry_price = p.get('entry_price', 0)
        side = p.get('side', '')
        
        if limit_price and entry_price and limit_price == entry_price:
            limit_vs_entry.append({
                'side': side,
                'limit_price': limit_price,
                'entry_price': entry_price,
                'is_win': p.get('is_win', False),
                'pnl': p.get('realized_pnl', 0),
            })
    
    print(f"\n挂单价 = 入场价 的交易数: {len(limit_vs_entry)} / {len(positions)} = {len(limit_vs_entry)/len(positions)*100:.1f}%")


def analyze_market_regime_detection(positions):
    """分析 agent 对市场状态的识别能力"""
    print("\n" + "=" * 100)
    print("市场状态识别能力分析")
    print("=" * 100)
    
    daily_data = defaultdict(lambda: {
        'trades': [],
        'long_count': 0,
        'short_count': 0,
    })
    
    for p in positions:
        entry_time = p.get('entry_time', '')
        side = p.get('side', '')
        if entry_time:
            try:
                dt = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
                date_key = dt.strftime('%Y-%m-%d')
                daily_data[date_key]['trades'].append(p)
                if side == 'long':
                    daily_data[date_key]['long_count'] += 1
                else:
                    daily_data[date_key]['short_count'] += 1
            except:
                pass
    
    regime_results = {
        'trending_up': {'agent_long': 0, 'agent_short': 0, 'long_pnl': 0, 'short_pnl': 0},
        'trending_down': {'agent_long': 0, 'agent_short': 0, 'long_pnl': 0, 'short_pnl': 0},
        'ranging': {'agent_long': 0, 'agent_short': 0, 'long_pnl': 0, 'short_pnl': 0},
    }
    
    print(f"\n{'日期':<12} {'日涨跌%':<10} {'市场状态':<12} {'Agent多':<8} {'Agent空':<8} {'多P&L':<12} {'空P&L':<12}")
    print("-" * 85)
    
    for date in sorted(daily_data.keys())[:30]:
        try:
            dt = datetime.strptime(date, '%Y-%m-%d')
            start_ts = int(dt.timestamp() * 1000)
            end_ts = int((dt + timedelta(days=1)).timestamp() * 1000)
            
            klines = fetch_klines("ETHUSDT", "1d", start_ts, end_ts)
            if not klines:
                continue
            
            day_open = float(klines[0][1])
            day_close = float(klines[0][4])
            day_high = float(klines[0][2])
            day_low = float(klines[0][3])
            
            day_change = (day_close - day_open) / day_open * 100
            day_range = (day_high - day_low) / day_low * 100
            
            if day_change > 2:
                regime = 'trending_up'
            elif day_change < -2:
                regime = 'trending_down'
            else:
                regime = 'ranging'
            
            data = daily_data[date]
            long_pnl = sum(t.get('realized_pnl', 0) for t in data['trades'] if t.get('side') == 'long')
            short_pnl = sum(t.get('realized_pnl', 0) for t in data['trades'] if t.get('side') == 'short')
            
            regime_results[regime]['agent_long'] += data['long_count']
            regime_results[regime]['agent_short'] += data['short_count']
            regime_results[regime]['long_pnl'] += long_pnl
            regime_results[regime]['short_pnl'] += short_pnl
            
            print(f"{date:<12} {day_change:<9.2f}% {regime:<12} {data['long_count']:<8} {data['short_count']:<8} ${long_pnl:<11.2f} ${short_pnl:<11.2f}")
            
        except Exception as e:
            continue
    
    print(f"\n" + "=" * 85)
    print("按市场状态汇总")
    print("=" * 85)
    
    print(f"\n{'市场状态':<15} {'Agent多':<10} {'Agent空':<10} {'多P&L':<15} {'空P&L':<15} {'应该做':<10}")
    print("-" * 80)
    
    for regime, data in regime_results.items():
        should_do = "多" if regime == 'trending_up' else ("空" if regime == 'trending_down' else "少做")
        print(f"{regime:<15} {data['agent_long']:<10} {data['agent_short']:<10} ${data['long_pnl']:<14.2f} ${data['short_pnl']:<14.2f} {should_do:<10}")


def analyze_intraday_pattern(positions):
    """分析日内交易模式"""
    print("\n" + "=" * 100)
    print("日内交易模式分析")
    print("=" * 100)
    
    sample_dates = ['2025-02-09', '2025-02-24', '2025-01-28', '2025-03-02']
    
    for date in sample_dates:
        print(f"\n{'='*50}")
        print(f"日期: {date}")
        print(f"{'='*50}")
        
        try:
            dt = datetime.strptime(date, '%Y-%m-%d')
            start_ts = int(dt.timestamp() * 1000)
            end_ts = int((dt + timedelta(days=1)).timestamp() * 1000)
            
            klines = fetch_klines("ETHUSDT", "15m", start_ts, end_ts)
            if not klines:
                continue
            
            day_trades = [p for p in positions if p.get('entry_time', '').startswith(date)]
            
            print(f"\n15分钟K线走势 (部分):")
            print(f"{'时间':<8} {'开盘':<10} {'最高':<10} {'最低':<10} {'收盘':<10} {'涨跌%':<8}")
            print("-" * 60)
            
            for k in klines[::4][:12]:
                ts = datetime.fromtimestamp(k[0]/1000)
                time_str = ts.strftime('%H:%M')
                open_p = float(k[1])
                high_p = float(k[2])
                low_p = float(k[3])
                close_p = float(k[4])
                change = (close_p - open_p) / open_p * 100
                print(f"{time_str:<8} ${open_p:<9.0f} ${high_p:<9.0f} ${low_p:<9.0f} ${close_p:<9.0f} {change:<7.2f}%")
            
            print(f"\n当日交易统计:")
            longs = [t for t in day_trades if t.get('side') == 'long']
            shorts = [t for t in day_trades if t.get('side') == 'short']
            
            long_wins = len([t for t in longs if t.get('is_win')])
            short_wins = len([t for t in shorts if t.get('is_win')])
            
            long_pnl = sum(t.get('realized_pnl', 0) for t in longs)
            short_pnl = sum(t.get('realized_pnl', 0) for t in shorts)
            
            print(f"  做多: {len(longs)} 笔, 胜率 {long_wins/len(longs)*100:.1f}%, P&L ${long_pnl:.2f}" if longs else "  做多: 0 笔")
            print(f"  做空: {len(shorts)} 笔, 胜率 {short_wins/len(shorts)*100:.1f}%, P&L ${short_pnl:.2f}" if shorts else "  做空: 0 笔")
            
            day_open = float(klines[0][1])
            day_close = float(klines[-1][4])
            day_change = (day_close - day_open) / day_open * 100
            print(f"\n  日K线: 开盘 ${day_open:.0f}, 收盘 ${day_close:.0f}, 涨跌 {day_change:.2f}%")
            
        except Exception as e:
            print(f"分析失败: {e}")
            continue


def analyze_random_walk_test(positions):
    """随机游走测试：如果随机选择方向，结果会怎样"""
    print("\n" + "=" * 100)
    print("随机游走对比测试")
    print("=" * 100)
    
    actual_pnl = sum(p.get('realized_pnl', 0) for p in positions)
    actual_wins = len([p for p in positions if p.get('is_win', False)])
    actual_winrate = actual_wins / len(positions) * 100
    
    print(f"\n实际结果:")
    print(f"  总交易: {len(positions)}")
    print(f"  胜率: {actual_winrate:.1f}%")
    print(f"  总P&L: ${actual_pnl:.2f}")
    
    reversed_pnl = 0
    reversed_wins = 0
    
    for p in positions:
        side = p.get('side', '')
        entry_price = p.get('entry_price', 0)
        exit_price = p.get('exit_price', 0)
        sl_price = p.get('sl_price', 0)
        tp_price = p.get('tp_price', 0)
        qty = p.get('qty', 0)
        
        if side == 'long':
            reversed_side_pnl = (entry_price - exit_price) * qty
        else:
            reversed_side_pnl = (exit_price - entry_price) * qty
        
        reversed_pnl += reversed_side_pnl
        if reversed_side_pnl > 0:
            reversed_wins += 1
    
    reversed_winrate = reversed_wins / len(positions) * 100
    
    print(f"\n如果方向完全相反:")
    print(f"  胜率: {reversed_winrate:.1f}%")
    print(f"  总P&L: ${reversed_pnl:.2f}")
    
    print(f"\n对比:")
    print(f"  实际 vs 反向: {actual_winrate:.1f}% vs {reversed_winrate:.1f}%")
    print(f"  P&L差异: ${actual_pnl - reversed_pnl:.2f}")


def main():
    filepath = "/Users/bytedance/Desktop/crypto_agentx/analysis/all_positions.jsonl"
    positions = load_positions(filepath)
    
    print(f"加载了 {len(positions)} 条交易记录\n")
    
    analyze_direction_vs_future_price(positions)
    analyze_entry_timing(positions)
    analyze_sl_tp_distance_effectiveness(positions)
    analyze_market_regime_detection(positions)
    analyze_intraday_pattern(positions)
    analyze_random_walk_test(positions)


if __name__ == "__main__":
    main()
