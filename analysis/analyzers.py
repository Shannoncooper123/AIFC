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


def analyze_hedged_positions(positions: List[Dict]) -> Dict:
    """
    分析双向持仓（对冲）情况
    
    当开仓时存在相反方向的持仓，视为"对冲持仓"
    统计对冲vs非对冲持仓的胜率和盈亏差异
    """
    print('\n' + '='*80)
    print('双向持仓（对冲）分析')
    print('='*80)
    
    events = []
    for p in positions:
        entry_dt = parse_datetime(p.get('entry_time', ''))
        exit_dt = parse_datetime(p.get('exit_time', ''))
        side = p.get('side', '')
        
        if entry_dt and exit_dt and side:
            events.append({
                'time': entry_dt,
                'type': 'entry',
                'side': side,
                'trade_id': p.get('trade_id', ''),
                'position': p
            })
            events.append({
                'time': exit_dt,
                'type': 'exit',
                'side': side,
                'trade_id': p.get('trade_id', ''),
                'position': p
            })
    
    if not events:
        print('  无有效数据')
        return {}
    
    events.sort(key=lambda x: (x['time'], 0 if x['type'] == 'entry' else 1))
    
    active_longs = set()
    active_shorts = set()
    
    hedged_trades = []
    non_hedged_trades = []
    
    for event in events:
        trade_id = event['trade_id']
        side = event['side']
        event_type = event['type']
        position = event['position']
        
        if event_type == 'entry':
            if side == 'long':
                has_opposite = len(active_shorts) > 0
                active_longs.add(trade_id)
            else:
                has_opposite = len(active_longs) > 0
                active_shorts.add(trade_id)
            
            trade_info = {
                'trade_id': trade_id,
                'side': side,
                'is_win': position.get('is_win', False),
                'pnl': position.get('realized_pnl', 0),
                'exit_type': position.get('exit_type', ''),
                'entry_time': event['time'],
                'opposite_count': len(active_shorts) if side == 'long' else len(active_longs),
                'same_count': len(active_longs) if side == 'long' else len(active_shorts)
            }
            
            if has_opposite:
                hedged_trades.append(trade_info)
            else:
                non_hedged_trades.append(trade_info)
        
        else:
            if side == 'long':
                active_longs.discard(trade_id)
            else:
                active_shorts.discard(trade_id)
    
    total_trades = len(hedged_trades) + len(non_hedged_trades)
    
    print(f'\n--- 整体统计 ---')
    print(f'  总交易数: {total_trades}')
    print(f'  对冲持仓: {len(hedged_trades)} ({len(hedged_trades)/total_trades*100:.1f}%)')
    print(f'  非对冲持仓: {len(non_hedged_trades)} ({len(non_hedged_trades)/total_trades*100:.1f}%)')
    
    print(f'\n--- 对冲 vs 非对冲 对比 ---')
    print(f'\n  {"指标":15s} {"对冲持仓":>15s} {"非对冲持仓":>15s} {"差异":>12s}')
    print(f'  {"-"*15} {"-"*15} {"-"*15} {"-"*12}')
    
    if hedged_trades:
        h_wins = len([t for t in hedged_trades if t['is_win']])
        h_wr = h_wins / len(hedged_trades) * 100
        h_pnl = sum(t['pnl'] for t in hedged_trades)
        h_avg_pnl = h_pnl / len(hedged_trades)
    else:
        h_wr, h_pnl, h_avg_pnl = 0, 0, 0
    
    if non_hedged_trades:
        nh_wins = len([t for t in non_hedged_trades if t['is_win']])
        nh_wr = nh_wins / len(non_hedged_trades) * 100
        nh_pnl = sum(t['pnl'] for t in non_hedged_trades)
        nh_avg_pnl = nh_pnl / len(non_hedged_trades)
    else:
        nh_wr, nh_pnl, nh_avg_pnl = 0, 0, 0
    
    print(f'  {"交易数":15s} {len(hedged_trades):>15d} {len(non_hedged_trades):>15d} {len(hedged_trades)-len(non_hedged_trades):>+12d}')
    print(f'  {"胜率":15s} {h_wr:>14.1f}% {nh_wr:>14.1f}% {h_wr-nh_wr:>+11.1f}%')
    print(f'  {"总P&L":15s} ${h_pnl:>13.2f} ${nh_pnl:>13.2f} ${h_pnl-nh_pnl:>+11.2f}')
    print(f'  {"平均P&L":15s} ${h_avg_pnl:>13.2f} ${nh_avg_pnl:>13.2f} ${h_avg_pnl-nh_avg_pnl:>+11.2f}')
    
    print(f'\n--- 对冲持仓按方向分析 ---')
    for side_name, side_key in [('做多', 'long'), ('做空', 'short')]:
        h_side = [t for t in hedged_trades if t['side'] == side_key]
        nh_side = [t for t in non_hedged_trades if t['side'] == side_key]
        
        if h_side or nh_side:
            print(f'\n  {side_name}:')
            
            if h_side:
                h_wins = len([t for t in h_side if t['is_win']])
                h_wr = h_wins / len(h_side) * 100
                h_pnl = sum(t['pnl'] for t in h_side)
                print(f'    对冲: {len(h_side):4d} 笔, WR {h_wr:5.1f}%, P&L ${h_pnl:>9.2f}')
            
            if nh_side:
                nh_wins = len([t for t in nh_side if t['is_win']])
                nh_wr = nh_wins / len(nh_side) * 100
                nh_pnl = sum(t['pnl'] for t in nh_side)
                print(f'    非对冲: {len(nh_side):4d} 笔, WR {nh_wr:5.1f}%, P&L ${nh_pnl:>9.2f}')
    
    print(f'\n--- 止盈/止损分布对比 ---')
    for exit_name, exit_key in [('止盈', 'tp'), ('止损', 'sl')]:
        h_exit = [t for t in hedged_trades if t['exit_type'] == exit_key]
        nh_exit = [t for t in non_hedged_trades if t['exit_type'] == exit_key]
        
        h_pct = len(h_exit) / len(hedged_trades) * 100 if hedged_trades else 0
        nh_pct = len(nh_exit) / len(non_hedged_trades) * 100 if non_hedged_trades else 0
        
        print(f'  {exit_name}: 对冲 {len(h_exit):4d} ({h_pct:5.1f}%) vs 非对冲 {len(nh_exit):4d} ({nh_pct:5.1f}%)')
    
    opposite_count_buckets = [
        (1, 1, '1个对手仓'),
        (2, 2, '2个对手仓'),
        (3, 3, '3个对手仓'),
        (4, float('inf'), '4个以上对手仓')
    ]
    
    print(f'\n--- 对冲持仓：对手仓数量分布 ---')
    for min_c, max_c, label in opposite_count_buckets:
        subset = [t for t in hedged_trades if min_c <= t['opposite_count'] <= max_c]
        if subset:
            count = len(subset)
            pct = count / len(hedged_trades) * 100
            wins = len([t for t in subset if t['is_win']])
            wr = wins / count * 100
            pnl = sum(t['pnl'] for t in subset)
            bar = '█' * int(pct / 2)
            print(f'  {label:15s}: {count:4d} ({pct:5.1f}%) WR {wr:5.1f}% P&L ${pnl:>9.2f} {bar}')
    
    print(f'\n--- 结论 ---')
    if hedged_trades and non_hedged_trades:
        h_wr_all = len([t for t in hedged_trades if t['is_win']]) / len(hedged_trades) * 100
        nh_wr_all = len([t for t in non_hedged_trades if t['is_win']]) / len(non_hedged_trades) * 100
        
        h_pnl_all = sum(t['pnl'] for t in hedged_trades)
        nh_pnl_all = sum(t['pnl'] for t in non_hedged_trades)
        
        if h_wr_all > nh_wr_all:
            print(f'  对冲持仓胜率更高 (+{h_wr_all - nh_wr_all:.1f}%)')
        else:
            print(f'  非对冲持仓胜率更高 (+{nh_wr_all - h_wr_all:.1f}%)')
        
        if h_pnl_all > nh_pnl_all:
            print(f'  对冲持仓P&L更好 (+${h_pnl_all - nh_pnl_all:.2f})')
        else:
            print(f'  非对冲持仓P&L更好 (+${nh_pnl_all - h_pnl_all:.2f})')
    
    return {
        'hedged_count': len(hedged_trades),
        'non_hedged_count': len(non_hedged_trades),
        'hedged_win_rate': len([t for t in hedged_trades if t['is_win']]) / len(hedged_trades) * 100 if hedged_trades else 0,
        'non_hedged_win_rate': len([t for t in non_hedged_trades if t['is_win']]) / len(non_hedged_trades) * 100 if non_hedged_trades else 0,
        'hedged_pnl': sum(t['pnl'] for t in hedged_trades),
        'non_hedged_pnl': sum(t['pnl'] for t in non_hedged_trades)
    }


def analyze_consecutive_direction_changes(positions: List[Dict]) -> Dict:
    """
    分析连续15分钟K线开仓方向变化模式
    
    查找三个连续15分钟周期内开仓方向交替变化的情况：
    - 做空 -> 做多 -> 做空 (SLS)
    - 做多 -> 做空 -> 做多 (LSL)
    
    "连续"指的是三个相邻的15分钟K线周期都有开仓
    """
    print('\n' + '='*80)
    print('连续15分钟开仓方向变化分析')
    print('='*80)
    
    interval_positions = defaultdict(list)
    
    for p in positions:
        order_time = parse_datetime(p.get('order_created_time', ''))
        if not order_time:
            order_time = parse_datetime(p.get('entry_time', ''))
        
        if not order_time:
            continue
        
        ts = order_time.timestamp()
        interval_start = int(ts // (15 * 60)) * (15 * 60)
        
        interval_positions[interval_start].append({
            'side': p.get('side', ''),
            'time': order_time,
            'symbol': p.get('symbol', ''),
            'trade_id': p.get('trade_id', ''),
            'is_win': p.get('is_win', False),
            'pnl': p.get('realized_pnl', 0),
            'position': p
        })
    
    if not interval_positions:
        print('  无有效数据')
        return {}
    
    sorted_intervals = sorted(interval_positions.keys())
    
    print(f'\n--- 基础统计 ---')
    print(f'  总开仓记录数: {len(positions)}')
    print(f'  有开仓的15分钟周期数: {len(sorted_intervals)}')
    print(f'  时间范围: {datetime.fromtimestamp(sorted_intervals[0]).strftime("%Y-%m-%d %H:%M")} ~ '
          f'{datetime.fromtimestamp(sorted_intervals[-1]).strftime("%Y-%m-%d %H:%M")}')
    
    def get_dominant_side(positions_in_interval):
        """获取该周期内的主导方向（按数量多少）"""
        longs = len([p for p in positions_in_interval if p['side'] == 'long'])
        shorts = len([p for p in positions_in_interval if p['side'] == 'short'])
        if longs > shorts:
            return 'long'
        elif shorts > longs:
            return 'short'
        else:
            return positions_in_interval[0]['side'] if positions_in_interval else None
    
    def get_all_sides(positions_in_interval):
        """获取该周期内所有不同的方向"""
        sides = set(p['side'] for p in positions_in_interval if p['side'])
        return sides
    
    consecutive_patterns = []
    alternating_patterns = {
        'SLS': [],
        'LSL': [],
    }
    
    interval_15m = 15 * 60
    
    for i in range(len(sorted_intervals) - 2):
        t1, t2, t3 = sorted_intervals[i], sorted_intervals[i+1], sorted_intervals[i+2]
        
        if t2 - t1 == interval_15m and t3 - t2 == interval_15m:
            p1 = interval_positions[t1]
            p2 = interval_positions[t2]
            p3 = interval_positions[t3]
            
            s1 = get_dominant_side(p1)
            s2 = get_dominant_side(p2)
            s3 = get_dominant_side(p3)
            
            if s1 and s2 and s3:
                pattern_info = {
                    't1': t1, 't2': t2, 't3': t3,
                    's1': s1, 's2': s2, 's3': s3,
                    'p1': p1, 'p2': p2, 'p3': p3,
                    'count1': len(p1), 'count2': len(p2), 'count3': len(p3),
                    'pnl1': sum(x['pnl'] for x in p1),
                    'pnl2': sum(x['pnl'] for x in p2),
                    'pnl3': sum(x['pnl'] for x in p3),
                }
                
                consecutive_patterns.append(pattern_info)
                
                if s1 == 'short' and s2 == 'long' and s3 == 'short':
                    alternating_patterns['SLS'].append(pattern_info)
                elif s1 == 'long' and s2 == 'short' and s3 == 'long':
                    alternating_patterns['LSL'].append(pattern_info)
    
    print(f'\n--- 连续三个15分钟周期统计 ---')
    print(f'  找到连续三个15分钟周期的窗口数: {len(consecutive_patterns)}')
    
    total_alternating = len(alternating_patterns['SLS']) + len(alternating_patterns['LSL'])
    print(f'\n--- 方向交替变化统计 ---')
    print(f'  总交替变化窗口数: {total_alternating}')
    if consecutive_patterns:
        print(f'  占所有连续窗口比例: {total_alternating/len(consecutive_patterns)*100:.1f}%')
    
    print(f'\n  做空→做多→做空 (SLS): {len(alternating_patterns["SLS"])} 次')
    print(f'  做多→做空→做多 (LSL): {len(alternating_patterns["LSL"])} 次')
    
    if alternating_patterns['SLS']:
        sls = alternating_patterns['SLS']
        total_pnl = sum(p['pnl1'] + p['pnl2'] + p['pnl3'] for p in sls)
        total_trades = sum(p['count1'] + p['count2'] + p['count3'] for p in sls)
        print(f'\n  SLS 模式详情:')
        print(f'    涉及交易笔数: {total_trades}')
        print(f'    总P&L: ${total_pnl:.2f}')
        print(f'    平均每窗口P&L: ${total_pnl/len(sls):.2f}')
    
    if alternating_patterns['LSL']:
        lsl = alternating_patterns['LSL']
        total_pnl = sum(p['pnl1'] + p['pnl2'] + p['pnl3'] for p in lsl)
        total_trades = sum(p['count1'] + p['count2'] + p['count3'] for p in lsl)
        print(f'\n  LSL 模式详情:')
        print(f'    涉及交易笔数: {total_trades}')
        print(f'    总P&L: ${total_pnl:.2f}')
        print(f'    平均每窗口P&L: ${total_pnl/len(lsl):.2f}')
    
    all_patterns = {
        'LLL': 0, 'LLS': 0, 'LSL': 0, 'LSS': 0,
        'SLL': 0, 'SLS': 0, 'SSL': 0, 'SSS': 0
    }
    
    for p in consecutive_patterns:
        pattern_key = ('L' if p['s1'] == 'long' else 'S') + \
                      ('L' if p['s2'] == 'long' else 'S') + \
                      ('L' if p['s3'] == 'long' else 'S')
        all_patterns[pattern_key] += 1
    
    print(f'\n--- 所有方向组合分布 ---')
    sorted_patterns = sorted(all_patterns.items(), key=lambda x: -x[1])
    for pattern, count in sorted_patterns:
        if count > 0:
            pct = count / len(consecutive_patterns) * 100 if consecutive_patterns else 0
            pattern_display = pattern.replace('L', '多').replace('S', '空')
            bar = '█' * int(pct / 2)
            print(f'  {pattern} ({pattern_display}): {count:4d} ({pct:5.1f}%) {bar}')
    
    print(f'\n--- 样例展示（前5个交替变化窗口）---')
    all_alternating = alternating_patterns['SLS'] + alternating_patterns['LSL']
    for i, p in enumerate(all_alternating[:5]):
        t1_str = datetime.fromtimestamp(p['t1']).strftime('%Y-%m-%d %H:%M')
        t2_str = datetime.fromtimestamp(p['t2']).strftime('%H:%M')
        t3_str = datetime.fromtimestamp(p['t3']).strftime('%H:%M')
        s1_cn = '多' if p['s1'] == 'long' else '空'
        s2_cn = '多' if p['s2'] == 'long' else '空'
        s3_cn = '多' if p['s3'] == 'long' else '空'
        print(f'  [{i+1}] {t1_str} ~ {t3_str}')
        print(f'      {s1_cn}({p["count1"]}笔,${p["pnl1"]:.0f}) → {s2_cn}({p["count2"]}笔,${p["pnl2"]:.0f}) → {s3_cn}({p["count3"]}笔,${p["pnl3"]:.0f})')
    
    middle_position_stats = {'win': 0, 'loss': 0, 'pnl': 0}
    for p in all_alternating:
        for pos in p['p2']:
            if pos['is_win']:
                middle_position_stats['win'] += 1
            else:
                middle_position_stats['loss'] += 1
            middle_position_stats['pnl'] += pos['pnl']
    
    total_middle = middle_position_stats['win'] + middle_position_stats['loss']
    if total_middle > 0:
        print(f'\n--- 中间反向开仓表现 ---')
        print(f'  交易数: {total_middle}')
        print(f'  胜率: {middle_position_stats["win"]/total_middle*100:.1f}%')
        print(f'  总P&L: ${middle_position_stats["pnl"]:.2f}')
        print(f'  平均P&L: ${middle_position_stats["pnl"]/total_middle:.2f}')
    
    return {
        'total_consecutive_windows': len(consecutive_patterns),
        'sls_count': len(alternating_patterns['SLS']),
        'lsl_count': len(alternating_patterns['LSL']),
        'total_alternating': total_alternating,
        'pattern_distribution': all_patterns,
        'middle_position_stats': middle_position_stats
    }


def analyze_fee_usage(positions: List[Dict], fee_rate: float = 0.00045) -> Dict:
    print('\n' + '='*80)
    print('手续费使用情况统计')
    print('='*80)

    fee_records = []
    for p in positions:
        entry_notional = p.get('entry_notional_usdt')
        exit_notional = p.get('exit_notional_usdt')
        if entry_notional is None or exit_notional is None:
            qty = p.get('qty')
            entry_price = p.get('entry_price')
            exit_price = p.get('exit_price')
            notional_usdt = p.get('notional_usdt')
            if entry_notional is None:
                if qty is not None and entry_price is not None:
                    entry_notional = float(qty) * float(entry_price)
                elif notional_usdt is not None:
                    entry_notional = float(notional_usdt)
            if exit_notional is None:
                if qty is not None and exit_price is not None:
                    exit_notional = float(qty) * float(exit_price)
                else:
                    exit_notional = entry_notional

        if entry_notional is None or exit_notional is None:
            continue

        fee = (float(entry_notional) + float(exit_notional)) * fee_rate
        fee_records.append({
            'fee': fee,
            'side': p.get('side', ''),
            'is_win': p.get('is_win', False),
            'entry_notional': float(entry_notional),
            'exit_notional': float(exit_notional)
        })

    if not fee_records:
        print('  无有效数据')
        return {}

    fees = [d['fee'] for d in fee_records]
    total_fee = sum(fees)
    sorted_fees = sorted(fees)
    median_fee = sorted_fees[len(sorted_fees) // 2]
    total_entry_notional = sum(d['entry_notional'] for d in fee_records)
    total_exit_notional = sum(d['exit_notional'] for d in fee_records)
    total_notional = total_entry_notional + total_exit_notional

    print(f'\n--- 整体统计 ---')
    print(f'  交易数: {len(fee_records)}')
    print(f'  总手续费: ${total_fee:.2f}')
    print(f'  平均单笔: ${total_fee/len(fee_records):.4f}')
    print(f'  中位数: ${median_fee:.4f}')
    print(f'  最小值: ${min(fees):.4f}')
    print(f'  最大值: ${max(fees):.4f}')
    print(f'  开仓名义总额: ${total_entry_notional:.2f}')
    print(f'  平仓名义总额: ${total_exit_notional:.2f}')
    print(f'  开平合计名义: ${total_notional:.2f}')

    print(f'\n--- 按方向统计 ---')
    for side_name, side_key in [('做多', 'long'), ('做空', 'short')]:
        side_data = [d for d in fee_records if d['side'] == side_key]
        if side_data:
            side_fees = [d['fee'] for d in side_data]
            side_entry = sum(d['entry_notional'] for d in side_data)
            side_exit = sum(d['exit_notional'] for d in side_data)
            print(f'\n  {side_name}:')
            print(f'    交易数: {len(side_data)}')
            print(f'    总手续费: ${sum(side_fees):.2f}')
            print(f'    平均单笔: ${sum(side_fees)/len(side_data):.4f}')
            print(f'    开仓名义总额: ${side_entry:.2f}')
            print(f'    平仓名义总额: ${side_exit:.2f}')

    return {
        'total_fee': total_fee,
        'avg_fee': total_fee / len(fee_records),
        'median_fee': median_fee,
        'min_fee': min(fees),
        'max_fee': max(fees),
        'total_entry_notional': total_entry_notional,
        'total_exit_notional': total_exit_notional
    }
