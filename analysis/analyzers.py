#!/usr/bin/env python3
"""
分析器模块
- 各种统计分析函数
- 输出文本格式的分析结果
"""
from collections import defaultdict
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from data_loader import parse_datetime


def analyze_order_to_entry_timing(positions: List[Dict]) -> Dict:
    """
    分析下单到成交的时间分布
    """
    print('\n' + '='*80)
    print('限价单等待成交时间分析 (下单 → 持仓)')
    print('='*80)
    
    order_to_entry = []
    for p in positions:
        d = p.get('order_to_entry_minutes')
        if d is not None and d >= 0:
            order_to_entry.append({
                'duration': d,
                'side': p.get('side', ''),
                'is_win': p.get('is_win', False),
                'pnl': p.get('realized_pnl', 0)
            })
    
    if not order_to_entry:
        print('  无有效数据')
        return {}
    
    durations = [d['duration'] for d in order_to_entry]
    avg_duration = sum(durations) / len(durations)
    sorted_durations = sorted(durations)
    median_duration = sorted_durations[len(sorted_durations) // 2]
    
    print(f'\n--- 整体统计 ---')
    print(f'  总订单数: {len(order_to_entry)}')
    print(f'  平均等待: {avg_duration:.1f} 分钟 ({avg_duration/60:.2f} 小时)')
    print(f'  中位数: {median_duration:.1f} 分钟')
    print(f'  最短等待: {min(durations):.1f} 分钟')
    print(f'  最长等待: {max(durations):.1f} 分钟 ({max(durations)/60:.2f} 小时)')
    
    duration_buckets = [
        (0, 5, '即时成交 (≤5分钟)'),
        (5, 15, '快速成交 (5-15分钟)'),
        (15, 30, '正常成交 (15-30分钟)'),
        (30, 60, '较慢成交 (30-60分钟)'),
        (60, 120, '慢速成交 (1-2小时)'),
        (120, 240, '很慢成交 (2-4小时)'),
        (240, float('inf'), '超长等待 (>4小时)')
    ]
    
    print(f'\n--- 等待时间分布 ---')
    for min_m, max_m, label in duration_buckets:
        subset = [d for d in order_to_entry if min_m <= d['duration'] < max_m]
        if subset:
            count = len(subset)
            pct = count / len(order_to_entry) * 100
            wins = len([d for d in subset if d['is_win']])
            wr = wins / count * 100
            pnl = sum(d['pnl'] for d in subset)
            bar = '█' * int(pct / 2)
            print(f'  {label:25s}: {count:4d} ({pct:5.1f}%) WR {wr:5.1f}% P&L ${pnl:>9.2f} {bar}')
    
    print(f'\n--- 按方向分析 ---')
    for side_name, side_key in [('做多', 'long'), ('做空', 'short')]:
        side_data = [d for d in order_to_entry if d['side'] == side_key]
        if side_data:
            side_durations = [d['duration'] for d in side_data]
            side_avg = sum(side_durations) / len(side_durations)
            side_sorted = sorted(side_durations)
            side_median = side_sorted[len(side_sorted) // 2]
            print(f'\n  {side_name}:')
            print(f'    订单数: {len(side_data)}')
            print(f'    平均等待: {side_avg:.1f} 分钟')
            print(f'    中位数: {side_median:.1f} 分钟')
    
    instant_fill = [d for d in order_to_entry if d['duration'] <= 5]
    if instant_fill:
        print(f'\n--- 即时成交分析 (≤5分钟) ---')
        print(f'  数量: {len(instant_fill)} ({len(instant_fill)/len(order_to_entry)*100:.1f}%)')
        wins = len([d for d in instant_fill if d['is_win']])
        print(f'  胜率: {wins/len(instant_fill)*100:.1f}%')
        print(f'  总P&L: ${sum(d["pnl"] for d in instant_fill):.2f}')
    
    return {
        'total': len(order_to_entry),
        'avg_minutes': avg_duration,
        'median_minutes': median_duration,
        'min_minutes': min(durations),
        'max_minutes': max(durations)
    }


def analyze_entry_to_exit_timing(positions: List[Dict]) -> Dict:
    """
    分析持仓到平仓的时间分布（按止盈/止损分类）
    """
    print('\n' + '='*80)
    print('持仓到平仓时间分析 (持仓 → 止盈/止损)')
    print('='*80)
    
    tp_data = []
    sl_data = []
    
    for p in positions:
        d = p.get('entry_to_exit_minutes')
        exit_type = p.get('exit_type', '')
        if d is not None and d > 0:
            item = {
                'duration': d,
                'side': p.get('side', ''),
                'pnl': p.get('realized_pnl', 0)
            }
            if exit_type == 'tp':
                tp_data.append(item)
            elif exit_type == 'sl':
                sl_data.append(item)
    
    if not tp_data and not sl_data:
        print('  无有效数据')
        return {}
    
    print(f'\n--- 止盈 vs 止损 对比 ---')
    
    if tp_data:
        tp_durations = [d['duration'] for d in tp_data]
        tp_avg = sum(tp_durations) / len(tp_durations)
        tp_sorted = sorted(tp_durations)
        tp_median = tp_sorted[len(tp_sorted) // 2]
        print(f'\n  止盈交易 ({len(tp_data)} 笔):')
        print(f'    平均持仓: {tp_avg:.1f} 分钟 ({tp_avg/60:.2f} 小时)')
        print(f'    中位数: {tp_median:.1f} 分钟')
        print(f'    最短: {min(tp_durations):.1f} 分钟')
        print(f'    最长: {max(tp_durations):.1f} 分钟')
    
    if sl_data:
        sl_durations = [d['duration'] for d in sl_data]
        sl_avg = sum(sl_durations) / len(sl_durations)
        sl_sorted = sorted(sl_durations)
        sl_median = sl_sorted[len(sl_sorted) // 2]
        print(f'\n  止损交易 ({len(sl_data)} 笔):')
        print(f'    平均持仓: {sl_avg:.1f} 分钟 ({sl_avg/60:.2f} 小时)')
        print(f'    中位数: {sl_median:.1f} 分钟')
        print(f'    最短: {min(sl_durations):.1f} 分钟')
        print(f'    最长: {max(sl_durations):.1f} 分钟')
    
    if tp_data and sl_data:
        print(f'\n--- 时间差异分析 ---')
        tp_avg = sum(d['duration'] for d in tp_data) / len(tp_data)
        sl_avg = sum(d['duration'] for d in sl_data) / len(sl_data)
        diff = tp_avg - sl_avg
        print(f'  止盈平均 - 止损平均 = {diff:.1f} 分钟')
        if diff > 0:
            print(f'  结论: 止盈交易平均持仓时间更长')
        else:
            print(f'  结论: 止损交易平均持仓时间更长')
    
    duration_buckets = [
        (0, 15, '0-15分钟'),
        (15, 30, '15-30分钟'),
        (30, 60, '30-60分钟'),
        (60, 120, '1-2小时'),
        (120, 240, '2-4小时'),
        (240, float('inf'), '4小时+')
    ]
    
    print(f'\n--- 止盈交易时间分布 ---')
    for min_m, max_m, label in duration_buckets:
        subset = [d for d in tp_data if min_m <= d['duration'] < max_m]
        if subset:
            count = len(subset)
            pct = count / len(tp_data) * 100 if tp_data else 0
            pnl = sum(d['pnl'] for d in subset)
            bar = '█' * int(pct / 2)
            print(f'  {label:15s}: {count:4d} ({pct:5.1f}%) P&L ${pnl:>9.2f} {bar}')
    
    print(f'\n--- 止损交易时间分布 ---')
    for min_m, max_m, label in duration_buckets:
        subset = [d for d in sl_data if min_m <= d['duration'] < max_m]
        if subset:
            count = len(subset)
            pct = count / len(sl_data) * 100 if sl_data else 0
            pnl = sum(d['pnl'] for d in subset)
            bar = '█' * int(pct / 2)
            print(f'  {label:15s}: {count:4d} ({pct:5.1f}%) P&L ${pnl:>9.2f} {bar}')
    
    print(f'\n--- 按方向细分 ---')
    for side_name, side_key in [('做多', 'long'), ('做空', 'short')]:
        side_tp = [d for d in tp_data if d['side'] == side_key]
        side_sl = [d for d in sl_data if d['side'] == side_key]
        
        print(f'\n  {side_name}:')
        if side_tp:
            avg = sum(d['duration'] for d in side_tp) / len(side_tp)
            print(f'    止盈: {len(side_tp)} 笔, 平均 {avg:.1f} 分钟')
        if side_sl:
            avg = sum(d['duration'] for d in side_sl) / len(side_sl)
            print(f'    止损: {len(side_sl)} 笔, 平均 {avg:.1f} 分钟')
    
    return {
        'tp_count': len(tp_data),
        'sl_count': len(sl_data),
        'tp_avg_minutes': sum(d['duration'] for d in tp_data) / len(tp_data) if tp_data else 0,
        'sl_avg_minutes': sum(d['duration'] for d in sl_data) / len(sl_data) if sl_data else 0
    }


def analyze_complete_lifecycle(positions: List[Dict]) -> Dict:
    """
    分析完整交易生命周期
    """
    print('\n' + '='*80)
    print('完整交易生命周期分析 (下单 → 持仓 → 平仓)')
    print('='*80)
    
    valid_data = []
    for p in positions:
        order_to_entry = p.get('order_to_entry_minutes')
        entry_to_exit = p.get('entry_to_exit_minutes')
        if order_to_entry is not None and entry_to_exit is not None:
            valid_data.append({
                'order_to_entry': order_to_entry,
                'entry_to_exit': entry_to_exit,
                'total': order_to_entry + entry_to_exit,
                'side': p.get('side', ''),
                'is_win': p.get('is_win', False),
                'exit_type': p.get('exit_type', ''),
                'pnl': p.get('realized_pnl', 0)
            })
    
    if not valid_data:
        print('  无有效数据')
        return {}
    
    order_to_entry = [d['order_to_entry'] for d in valid_data]
    entry_to_exit = [d['entry_to_exit'] for d in valid_data]
    total = [d['total'] for d in valid_data]
    
    print(f'\n--- 整体统计 ---')
    print(f'  有效交易数: {len(valid_data)}')
    print(f'\n  下单→持仓:')
    print(f'    平均: {sum(order_to_entry)/len(order_to_entry):.1f} 分钟')
    print(f'    中位数: {sorted(order_to_entry)[len(order_to_entry)//2]:.1f} 分钟')
    print(f'\n  持仓→平仓:')
    print(f'    平均: {sum(entry_to_exit)/len(entry_to_exit):.1f} 分钟')
    print(f'    中位数: {sorted(entry_to_exit)[len(entry_to_exit)//2]:.1f} 分钟')
    print(f'\n  总时长:')
    print(f'    平均: {sum(total)/len(total):.1f} 分钟 ({sum(total)/len(total)/60:.2f} 小时)')
    print(f'    中位数: {sorted(total)[len(total)//2]:.1f} 分钟')
    print(f'    最短: {min(total):.1f} 分钟')
    print(f'    最长: {max(total):.1f} 分钟 ({max(total)/60:.2f} 小时)')
    
    print(f'\n--- 盈亏对比 ---')
    win_data = [d for d in valid_data if d['is_win']]
    loss_data = [d for d in valid_data if not d['is_win']]
    
    if win_data:
        print(f'\n  盈利交易 ({len(win_data)} 笔):')
        print(f'    等待成交: {sum(d["order_to_entry"] for d in win_data)/len(win_data):.1f} 分钟')
        print(f'    持仓时间: {sum(d["entry_to_exit"] for d in win_data)/len(win_data):.1f} 分钟')
        print(f'    总时长: {sum(d["total"] for d in win_data)/len(win_data):.1f} 分钟')
    
    if loss_data:
        print(f'\n  亏损交易 ({len(loss_data)} 笔):')
        print(f'    等待成交: {sum(d["order_to_entry"] for d in loss_data)/len(loss_data):.1f} 分钟')
        print(f'    持仓时间: {sum(d["entry_to_exit"] for d in loss_data)/len(loss_data):.1f} 分钟')
        print(f'    总时长: {sum(d["total"] for d in loss_data)/len(loss_data):.1f} 分钟')
    
    print(f'\n--- 按方向对比 ---')
    for side_name, side_key in [('做多', 'long'), ('做空', 'short')]:
        side_data = [d for d in valid_data if d['side'] == side_key]
        if side_data:
            print(f'\n  {side_name} ({len(side_data)} 笔):')
            print(f'    等待成交: {sum(d["order_to_entry"] for d in side_data)/len(side_data):.1f} 分钟')
            print(f'    持仓时间: {sum(d["entry_to_exit"] for d in side_data)/len(side_data):.1f} 分钟')
            print(f'    总时长: {sum(d["total"] for d in side_data)/len(side_data):.1f} 分钟')
    
    lifecycle_buckets = [
        (0, 30, '0-30分钟'),
        (30, 60, '30-60分钟'),
        (60, 120, '1-2小时'),
        (120, 240, '2-4小时'),
        (240, 480, '4-8小时'),
        (480, float('inf'), '8小时+')
    ]
    
    print(f'\n--- 总时长分布 ---')
    for min_m, max_m, label in lifecycle_buckets:
        subset = [d for d in valid_data if min_m <= d['total'] < max_m]
        if subset:
            count = len(subset)
            pct = count / len(valid_data) * 100
            wins = len([d for d in subset if d['is_win']])
            wr = wins / count * 100
            pnl = sum(d['pnl'] for d in subset)
            bar = '█' * int(pct / 2)
            print(f'  {label:15s}: {count:4d} ({pct:5.1f}%) WR {wr:5.1f}% P&L ${pnl:>9.2f} {bar}')
    
    return {
        'total_trades': len(valid_data),
        'avg_order_to_entry': sum(order_to_entry) / len(order_to_entry),
        'avg_entry_to_exit': sum(entry_to_exit) / len(entry_to_exit),
        'avg_total': sum(total) / len(total)
    }


def analyze_concurrent_margin(positions: List[Dict]) -> Dict:
    """
    分析并发持仓保证金需求
    """
    print('\n' + '='*80)
    print('并发持仓保证金分析')
    print('='*80)
    
    events = []
    for p in positions:
        entry_dt = parse_datetime(p.get('entry_time', ''))
        exit_dt = parse_datetime(p.get('exit_time', ''))
        margin = p.get('margin_usdt', 500)
        
        if entry_dt and exit_dt:
            events.append((entry_dt, 'open', margin, p.get('trade_id', '')))
            events.append((exit_dt, 'close', margin, p.get('trade_id', '')))
    
    if not events:
        print('  无有效数据')
        return {}
    
    events.sort(key=lambda x: (x[0], 0 if x[1] == 'open' else 1))
    
    current_margin = 0
    current_positions = 0
    max_margin = 0
    max_positions = 0
    max_margin_time = None
    max_positions_time = None
    
    margin_history = []
    
    for event_time, event_type, margin, trade_id in events:
        if event_type == 'open':
            current_margin += margin
            current_positions += 1
        else:
            current_margin -= margin
            current_positions -= 1
        
        margin_history.append((event_time, current_margin, current_positions))
        
        if current_margin > max_margin:
            max_margin = current_margin
            max_margin_time = event_time
        
        if current_positions > max_positions:
            max_positions = current_positions
            max_positions_time = event_time
    
    print(f'\n--- 峰值统计 ---')
    print(f'  最大并发持仓数: {max_positions} 个')
    if max_positions_time:
        print(f'  发生时间: {max_positions_time.strftime("%Y-%m-%d %H:%M")}')
    print(f'  最大保证金需求: ${max_margin:.2f} USDT')
    if max_margin_time:
        print(f'  发生时间: {max_margin_time.strftime("%Y-%m-%d %H:%M")}')
    
    margin_values = [m for _, m, _ in margin_history if m > 0]
    if margin_values:
        avg_margin = sum(margin_values) / len(margin_values)
        print(f'\n--- 平均统计 ---')
        print(f'  平均占用保证金: ${avg_margin:.2f} USDT')
    
    margin_buckets = {
        '0-500': 0, '500-1000': 0, '1000-2000': 0, 
        '2000-3000': 0, '3000-5000': 0, '5000+': 0
    }
    
    for _, margin, _ in margin_history:
        if margin <= 500:
            margin_buckets['0-500'] += 1
        elif margin <= 1000:
            margin_buckets['500-1000'] += 1
        elif margin <= 2000:
            margin_buckets['1000-2000'] += 1
        elif margin <= 3000:
            margin_buckets['2000-3000'] += 1
        elif margin <= 5000:
            margin_buckets['3000-5000'] += 1
        else:
            margin_buckets['5000+'] += 1
    
    total_events = len(margin_history)
    print(f'\n--- 保证金占用分布 ---')
    for bucket, count in margin_buckets.items():
        if count > 0:
            pct = count / total_events * 100
            bar = '█' * int(pct / 2)
            print(f'  ${bucket:>10s}: {count:5d} ({pct:5.1f}%) {bar}')
    
    position_buckets = defaultdict(int)
    for _, _, pos_count in margin_history:
        position_buckets[pos_count] += 1
    
    print(f'\n--- 并发持仓数分布 ---')
    for pos_count in sorted(position_buckets.keys()):
        count = position_buckets[pos_count]
        pct = count / total_events * 100
        bar = '█' * int(pct / 2)
        print(f'  {pos_count:2d} 个持仓: {count:5d} ({pct:5.1f}%) {bar}')
    
    return {
        'max_margin': max_margin,
        'max_positions': max_positions,
        'avg_margin': avg_margin if margin_values else 0
    }


def analyze_holding_duration(positions: List[Dict]) -> Dict:
    """
    分析持仓时间分布
    """
    print('\n' + '='*80)
    print('持仓时间分布分析')
    print('='*80)
    
    durations = []
    for p in positions:
        d = p.get('entry_to_exit_minutes')
        if d is not None and d > 0:
            durations.append({
                'duration': d,
                'side': p.get('side', ''),
                'is_win': p.get('is_win', False),
                'pnl': p.get('realized_pnl', 0),
                'holding_bars': p.get('holding_bars', 0)
            })
    
    if not durations:
        print('  无有效数据')
        return {}
    
    all_durations = [d['duration'] for d in durations]
    avg_duration = sum(all_durations) / len(all_durations)
    sorted_durations = sorted(all_durations)
    median_duration = sorted_durations[len(sorted_durations) // 2]
    
    print(f'\n--- 整体统计 ---')
    print(f'  总交易数: {len(durations)}')
    print(f'  平均持仓: {avg_duration:.1f} 分钟 ({avg_duration/60:.2f} 小时)')
    print(f'  中位数: {median_duration:.1f} 分钟')
    print(f'  最短: {min(all_durations):.1f} 分钟')
    print(f'  最长: {max(all_durations):.1f} 分钟 ({max(all_durations)/60:.2f} 小时)')
    
    duration_buckets = [
        (0, 15, '0-15分钟 (极短)'),
        (15, 30, '15-30分钟'),
        (30, 60, '30-60分钟'),
        (60, 120, '1-2小时'),
        (120, 240, '2-4小时'),
        (240, 480, '4-8小时'),
        (480, 1440, '8-24小时'),
        (1440, float('inf'), '24小时+')
    ]
    
    print(f'\n--- 持仓时间分布 ---')
    for min_m, max_m, label in duration_buckets:
        subset = [d for d in durations if min_m <= d['duration'] < max_m]
        if subset:
            count = len(subset)
            pct = count / len(durations) * 100
            wins = len([d for d in subset if d['is_win']])
            wr = wins / count * 100
            pnl = sum(d['pnl'] for d in subset)
            bar = '█' * int(pct / 2)
            print(f'  {label:18s}: {count:4d} ({pct:5.1f}%) WR {wr:5.1f}% P&L ${pnl:>9.2f} {bar}')
    
    short_trades = [d for d in durations if d['duration'] < 15]
    if short_trades:
        print(f'\n--- 极短持仓分析 (<15分钟) ---')
        print(f'  数量: {len(short_trades)} ({len(short_trades)/len(durations)*100:.1f}%)')
        wins = len([d for d in short_trades if d['is_win']])
        print(f'  胜率: {wins/len(short_trades)*100:.1f}%')
        print(f'  总P&L: ${sum(d["pnl"] for d in short_trades):.2f}')
        
        long_short = [d for d in short_trades if d['side'] == 'long']
        short_short = [d for d in short_trades if d['side'] == 'short']
        
        if long_short:
            wr = len([d for d in long_short if d['is_win']]) / len(long_short) * 100
            pnl = sum(d['pnl'] for d in long_short)
            print(f'  做多: {len(long_short)} 笔, WR {wr:.1f}%, P&L ${pnl:.2f}')
        
        if short_short:
            wr = len([d for d in short_short if d['is_win']]) / len(short_short) * 100
            pnl = sum(d['pnl'] for d in short_short)
            print(f'  做空: {len(short_short)} 笔, WR {wr:.1f}%, P&L ${pnl:.2f}')
    
    print(f'\n--- 按方向分析 ---')
    for side_name, side_key in [('做多', 'long'), ('做空', 'short')]:
        side_data = [d for d in durations if d['side'] == side_key]
        if side_data:
            side_durations = [d['duration'] for d in side_data]
            side_avg = sum(side_durations) / len(side_durations)
            side_sorted = sorted(side_durations)
            side_median = side_sorted[len(side_sorted) // 2]
            print(f'\n  {side_name}:')
            print(f'    平均持仓: {side_avg:.1f} 分钟 ({side_avg/60:.2f} 小时)')
            print(f'    中位数: {side_median:.1f} 分钟')
    
    print(f'\n--- 盈亏与持仓时间关系 ---')
    win_durations = [d['duration'] for d in durations if d['is_win']]
    loss_durations = [d['duration'] for d in durations if not d['is_win']]
    
    if win_durations:
        print(f'  盈利交易平均持仓: {sum(win_durations)/len(win_durations):.1f} 分钟')
    if loss_durations:
        print(f'  亏损交易平均持仓: {sum(loss_durations)/len(loss_durations):.1f} 分钟')
    
    return {
        'total': len(durations),
        'avg_minutes': avg_duration,
        'median_minutes': median_duration
    }
