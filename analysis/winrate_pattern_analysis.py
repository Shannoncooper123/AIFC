#!/usr/bin/env python3
"""
胜率模式分析工具
- 分析不同特征维度与胜率的关系
- 自动发现高/低胜率规则
- 为 Agent 自我学习提供数据支撑
"""
import json
import sys
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import statistics

DATA_FILE = '/Users/bytedance/Desktop/crypto_agentx/analysis/all_positions.jsonl'


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


def calc_winrate(trades: List[Dict]) -> Tuple[float, int, int]:
    """计算胜率"""
    if not trades:
        return 0.0, 0, 0
    wins = len([t for t in trades if t.get('is_win')])
    return wins / len(trades) * 100, wins, len(trades)


def calc_avg_pnl(trades: List[Dict]) -> float:
    """计算平均盈亏"""
    if not trades:
        return 0.0
    return sum(t.get('realized_pnl', 0) for t in trades) / len(trades)


def calc_total_pnl(trades: List[Dict]) -> float:
    """计算总盈亏"""
    return sum(t.get('realized_pnl', 0) for t in trades)


def print_section(title: str):
    """打印分节标题"""
    print('\n' + '=' * 80)
    print(f'  {title}')
    print('=' * 80)


def print_subsection(title: str):
    """打印子节标题"""
    print(f'\n--- {title} ---')


def analyze_basic_stats(positions: List[Dict]) -> Dict:
    """基础统计"""
    print_section('基础统计')
    
    total = len(positions)
    wins = len([p for p in positions if p.get('is_win')])
    winrate = wins / total * 100
    
    long_trades = [p for p in positions if p.get('side') == 'long']
    short_trades = [p for p in positions if p.get('side') == 'short']
    
    print(f'\n  总交易数: {total}')
    print(f'  总胜率: {winrate:.1f}% ({wins}/{total})')
    print(f'  总P&L: ${calc_total_pnl(positions):.2f}')
    
    print_subsection('按方向')
    for name, trades in [('做多', long_trades), ('做空', short_trades)]:
        wr, w, t = calc_winrate(trades)
        pnl = calc_total_pnl(trades)
        print(f'  {name}: {t} 笔, 胜率 {wr:.1f}% ({w}/{t}), P&L ${pnl:.2f}')
    
    return {
        'total': total,
        'winrate': winrate,
        'long_count': len(long_trades),
        'short_count': len(short_trades),
    }


def analyze_rr_ratio_impact(positions: List[Dict]) -> Dict:
    """分析 R:R 盈亏比对胜率的影响"""
    print_section('R:R 盈亏比 vs 胜率分析')
    
    # 按 R:R 分组
    rr_buckets = [
        (0, 0.8, 'R:R < 0.8 (低)'),
        (0.8, 1.0, 'R:R 0.8-1.0'),
        (1.0, 1.2, 'R:R 1.0-1.2'),
        (1.2, 1.5, 'R:R 1.2-1.5'),
        (1.5, 2.0, 'R:R 1.5-2.0'),
        (2.0, 2.5, 'R:R 2.0-2.5'),
        (2.5, 3.0, 'R:R 2.5-3.0'),
        (3.0, float('inf'), 'R:R > 3.0 (高)'),
    ]
    
    # 使用 tp_distance_percent / sl_distance_percent 计算 R:R
    results = []
    
    print_subsection('R:R 分布与胜率')
    print(f'  {"R:R 范围":20s} {"数量":>8s} {"胜率":>8s} {"平均PnL":>10s} {"总PnL":>12s}')
    print(f'  {"-"*20} {"-"*8} {"-"*8} {"-"*10} {"-"*12}')
    
    for min_rr, max_rr, label in rr_buckets:
        subset = []
        for p in positions:
            tp_dist = p.get('tp_distance_percent', 0)
            sl_dist = p.get('sl_distance_percent', 0)
            if sl_dist > 0:
                rr = tp_dist / sl_dist
                if min_rr <= rr < max_rr:
                    subset.append(p)
        
        if len(subset) >= 10:  # 至少10个样本
            wr, wins, total = calc_winrate(subset)
            avg_pnl = calc_avg_pnl(subset)
            total_pnl = calc_total_pnl(subset)
            pct = len(subset) / len(positions) * 100
            
            print(f'  {label:20s} {total:>7d}  {wr:>6.1f}%  ${avg_pnl:>8.2f}  ${total_pnl:>10.2f}')
            
            results.append({
                'range': label,
                'min_rr': min_rr,
                'max_rr': max_rr,
                'count': total,
                'winrate': wr,
                'avg_pnl': avg_pnl,
                'total_pnl': total_pnl,
            })
    
    # 找出最优 R:R 范围
    print_subsection('洞察')
    if results:
        best_wr = max(results, key=lambda x: x['winrate'])
        best_pnl = max(results, key=lambda x: x['avg_pnl'])
        worst_wr = min(results, key=lambda x: x['winrate'])
        
        print(f'  ✅ 最高胜率: {best_wr["range"]} ({best_wr["winrate"]:.1f}%)')
        print(f'  ✅ 最高平均PnL: {best_pnl["range"]} (${best_pnl["avg_pnl"]:.2f})')
        print(f'  ❌ 最低胜率: {worst_wr["range"]} ({worst_wr["winrate"]:.1f}%)')
    
    return {'rr_analysis': results}


def analyze_entry_distance_impact(positions: List[Dict]) -> Dict:
    """分析挂单距离对胜率的影响"""
    print_section('挂单距离 vs 胜率分析')
    
    # 计算挂单距离 = |limit_price - entry_price| / entry_price * 100
    # 这里我们用 order_created_time 到 entry_time 的时间差来推断
    
    # 使用 sl_distance_percent 作为代理指标
    distance_buckets = [
        (0, 0.5, '极近 (< 0.5%)'),
        (0.5, 0.8, '较近 (0.5-0.8%)'),
        (0.8, 1.0, '适中 (0.8-1.0%)'),
        (1.0, 1.5, '较远 (1.0-1.5%)'),
        (1.5, 2.0, '远 (1.5-2.0%)'),
        (2.0, float('inf'), '很远 (> 2.0%)'),
    ]
    
    results = []
    
    print_subsection('止损距离分布与胜率')
    print(f'  {"止损距离":20s} {"数量":>8s} {"胜率":>8s} {"平均PnL":>10s} {"总PnL":>12s}')
    print(f'  {"-"*20} {"-"*8} {"-"*8} {"-"*10} {"-"*12}')
    
    for min_dist, max_dist, label in distance_buckets:
        subset = [p for p in positions if min_dist <= p.get('sl_distance_percent', 0) < max_dist]
        
        if len(subset) >= 10:
            wr, wins, total = calc_winrate(subset)
            avg_pnl = calc_avg_pnl(subset)
            total_pnl = calc_total_pnl(subset)
            
            print(f'  {label:20s} {total:>7d}  {wr:>6.1f}%  ${avg_pnl:>8.2f}  ${total_pnl:>10.2f}')
            
            results.append({
                'range': label,
                'count': total,
                'winrate': wr,
                'avg_pnl': avg_pnl,
            })
    
    print_subsection('止盈距离分布与胜率')
    print(f'  {"止盈距离":20s} {"数量":>8s} {"胜率":>8s} {"平均PnL":>10s} {"总PnL":>12s}')
    print(f'  {"-"*20} {"-"*8} {"-"*8} {"-"*10} {"-"*12}')
    
    tp_buckets = [
        (0, 1.0, '近 (< 1.0%)'),
        (1.0, 1.5, '适中 (1.0-1.5%)'),
        (1.5, 2.0, '较远 (1.5-2.0%)'),
        (2.0, 3.0, '远 (2.0-3.0%)'),
        (3.0, float('inf'), '很远 (> 3.0%)'),
    ]
    
    for min_dist, max_dist, label in tp_buckets:
        subset = [p for p in positions if min_dist <= p.get('tp_distance_percent', 0) < max_dist]
        
        if len(subset) >= 10:
            wr, wins, total = calc_winrate(subset)
            avg_pnl = calc_avg_pnl(subset)
            total_pnl = calc_total_pnl(subset)
            
            print(f'  {label:20s} {total:>7d}  {wr:>6.1f}%  ${avg_pnl:>8.2f}  ${total_pnl:>10.2f}')
    
    print_subsection('洞察')
    if results:
        best = max(results, key=lambda x: x['winrate'])
        worst = min(results, key=lambda x: x['winrate'])
        print(f'  ✅ 最高胜率止损距离: {best["range"]} ({best["winrate"]:.1f}%)')
        print(f'  ❌ 最低胜率止损距离: {worst["range"]} ({worst["winrate"]:.1f}%)')
    
    return {'distance_analysis': results}


def analyze_holding_time_impact(positions: List[Dict]) -> Dict:
    """分析持仓时间对胜率的影响"""
    print_section('持仓时间 vs 胜率分析')
    
    time_buckets = [
        (0, 15, '极短 (< 15分钟)'),
        (15, 30, '短 (15-30分钟)'),
        (30, 60, '中短 (30-60分钟)'),
        (60, 120, '中 (1-2小时)'),
        (120, 240, '中长 (2-4小时)'),
        (240, 480, '长 (4-8小时)'),
        (480, float('inf'), '很长 (> 8小时)'),
    ]
    
    results = []
    
    # 计算持仓时间
    for p in positions:
        entry_time = parse_datetime(p.get('entry_time', ''))
        exit_time = parse_datetime(p.get('exit_time', ''))
        if entry_time and exit_time:
            p['holding_minutes'] = (exit_time - entry_time).total_seconds() / 60
    
    print_subsection('持仓时间分布与胜率')
    print(f'  {"持仓时间":20s} {"数量":>8s} {"胜率":>8s} {"平均PnL":>10s} {"总PnL":>12s}')
    print(f'  {"-"*20} {"-"*8} {"-"*8} {"-"*10} {"-"*12}')
    
    for min_time, max_time, label in time_buckets:
        subset = [p for p in positions if min_time <= p.get('holding_minutes', 0) < max_time]
        
        if len(subset) >= 10:
            wr, wins, total = calc_winrate(subset)
            avg_pnl = calc_avg_pnl(subset)
            total_pnl = calc_total_pnl(subset)
            
            print(f'  {label:20s} {total:>7d}  {wr:>6.1f}%  ${avg_pnl:>8.2f}  ${total_pnl:>10.2f}')
            
            results.append({
                'range': label,
                'count': total,
                'winrate': wr,
                'avg_pnl': avg_pnl,
            })
    
    # 分析止盈vs止损的持仓时间
    print_subsection('止盈 vs 止损 持仓时间')
    
    tp_trades = [p for p in positions if p.get('exit_type') == 'tp' and p.get('holding_minutes')]
    sl_trades = [p for p in positions if p.get('exit_type') == 'sl' and p.get('holding_minutes')]
    
    if tp_trades:
        tp_times = [p['holding_minutes'] for p in tp_trades]
        print(f'  止盈交易: 平均 {statistics.mean(tp_times):.1f} 分钟, 中位数 {statistics.median(tp_times):.1f} 分钟')
    
    if sl_trades:
        sl_times = [p['holding_minutes'] for p in sl_trades]
        print(f'  止损交易: 平均 {statistics.mean(sl_times):.1f} 分钟, 中位数 {statistics.median(sl_times):.1f} 分钟')
    
    print_subsection('洞察')
    if results:
        best = max(results, key=lambda x: x['winrate'])
        worst = min(results, key=lambda x: x['winrate'])
        print(f'  ✅ 最高胜率持仓时间: {best["range"]} ({best["winrate"]:.1f}%)')
        print(f'  ❌ 最低胜率持仓时间: {worst["range"]} ({worst["winrate"]:.1f}%)')
    
    return {'holding_time_analysis': results}


def analyze_time_of_day_impact(positions: List[Dict]) -> Dict:
    """分析开仓时间（小时）对胜率的影响"""
    print_section('开仓时间 (UTC小时) vs 胜率分析')
    
    # 按小时分组
    hourly_stats = defaultdict(list)
    
    for p in positions:
        entry_time = parse_datetime(p.get('entry_time', ''))
        if entry_time:
            hour = entry_time.hour
            hourly_stats[hour].append(p)
    
    results = []
    
    print_subsection('按小时统计')
    print(f'  {"小时(UTC)":>12s} {"数量":>8s} {"胜率":>8s} {"平均PnL":>10s} {"总PnL":>12s}')
    print(f'  {"-"*12} {"-"*8} {"-"*8} {"-"*10} {"-"*12}')
    
    for hour in sorted(hourly_stats.keys()):
        trades = hourly_stats[hour]
        if len(trades) >= 10:
            wr, wins, total = calc_winrate(trades)
            avg_pnl = calc_avg_pnl(trades)
            total_pnl = calc_total_pnl(trades)
            
            print(f'  {hour:>10d}:00 {total:>7d}  {wr:>6.1f}%  ${avg_pnl:>8.2f}  ${total_pnl:>10.2f}')
            
            results.append({
                'hour': hour,
                'count': total,
                'winrate': wr,
                'avg_pnl': avg_pnl,
                'total_pnl': total_pnl,
            })
    
    # 按时段分组
    print_subsection('按交易时段统计')
    
    session_ranges = [
        (0, 8, '亚盘 (0-8 UTC)'),
        (8, 14, '欧盘 (8-14 UTC)'),
        (14, 22, '美盘 (14-22 UTC)'),
        (22, 24, '收盘前 (22-24 UTC)'),
    ]
    
    for start_hour, end_hour, label in session_ranges:
        subset = []
        for hour in range(start_hour, end_hour):
            subset.extend(hourly_stats.get(hour, []))
        
        if len(subset) >= 10:
            wr, wins, total = calc_winrate(subset)
            avg_pnl = calc_avg_pnl(subset)
            total_pnl = calc_total_pnl(subset)
            
            print(f'  {label:25s} {total:>7d}  {wr:>6.1f}%  ${avg_pnl:>8.2f}  ${total_pnl:>10.2f}')
    
    print_subsection('洞察')
    if results:
        best_hour = max(results, key=lambda x: x['winrate'])
        worst_hour = min(results, key=lambda x: x['winrate'])
        best_pnl_hour = max(results, key=lambda x: x['avg_pnl'])
        
        print(f'  ✅ 最高胜率时段: {best_hour["hour"]}:00 UTC ({best_hour["winrate"]:.1f}%)')
        print(f'  ✅ 最高平均PnL时段: {best_pnl_hour["hour"]}:00 UTC (${best_pnl_hour["avg_pnl"]:.2f})')
        print(f'  ❌ 最低胜率时段: {worst_hour["hour"]}:00 UTC ({worst_hour["winrate"]:.1f}%)')
    
    return {'hourly_analysis': results}


def analyze_r_multiple_distribution(positions: List[Dict]) -> Dict:
    """分析实际 R 倍数分布"""
    print_section('实际 R 倍数分布分析')
    
    r_values = []
    for p in positions:
        r = p.get('r_multiple')
        if r is not None:
            r_values.append({
                'r': r,
                'side': p.get('side', ''),
                'is_win': p.get('is_win', False),
                'exit_type': p.get('exit_type', ''),
            })
    
    if not r_values:
        print('  无有效 R 倍数数据')
        return {}
    
    print_subsection('整体 R 倍数统计')
    all_r = [v['r'] for v in r_values]
    print(f'  样本数: {len(all_r)}')
    print(f'  平均 R: {statistics.mean(all_r):.3f}')
    print(f'  中位数 R: {statistics.median(all_r):.3f}')
    print(f'  最小 R: {min(all_r):.3f}')
    print(f'  最大 R: {max(all_r):.3f}')
    
    # 分布
    r_buckets = [
        (-float('inf'), -2, 'R < -2 (大亏)'),
        (-2, -1.5, 'R -2 ~ -1.5'),
        (-1.5, -1, 'R -1.5 ~ -1'),
        (-1, -0.5, 'R -1 ~ -0.5'),
        (-0.5, 0, 'R -0.5 ~ 0'),
        (0, 0.5, 'R 0 ~ 0.5'),
        (0.5, 1, 'R 0.5 ~ 1'),
        (1, 1.5, 'R 1 ~ 1.5'),
        (1.5, 2, 'R 1.5 ~ 2'),
        (2, float('inf'), 'R > 2 (大赚)'),
    ]
    
    print_subsection('R 倍数分布')
    print(f'  {"R 范围":20s} {"数量":>8s} {"占比":>8s} {"累计":>8s}')
    print(f'  {"-"*20} {"-"*8} {"-"*8} {"-"*8}')
    
    cumulative = 0
    for min_r, max_r, label in r_buckets:
        count = len([v for v in r_values if min_r <= v['r'] < max_r])
        if count > 0:
            pct = count / len(r_values) * 100
            cumulative += pct
            bar = '█' * int(pct / 2)
            print(f'  {label:20s} {count:>7d}  {pct:>6.1f}%  {cumulative:>6.1f}% {bar}')
    
    # 按方向
    print_subsection('按方向统计')
    for side_name, side_key in [('做多', 'long'), ('做空', 'short')]:
        side_r = [v['r'] for v in r_values if v['side'] == side_key]
        if side_r:
            print(f'  {side_name}: 平均 R = {statistics.mean(side_r):.3f}, 中位数 = {statistics.median(side_r):.3f}')
    
    print_subsection('洞察')
    positive_r = len([v for v in r_values if v['r'] > 0])
    negative_r = len([v for v in r_values if v['r'] < 0])
    print(f'  盈利交易 (R > 0): {positive_r} ({positive_r/len(r_values)*100:.1f}%)')
    print(f'  亏损交易 (R < 0): {negative_r} ({negative_r/len(r_values)*100:.1f}%)')
    
    # 期望值分析
    avg_win_r = statistics.mean([v['r'] for v in r_values if v['r'] > 0]) if positive_r > 0 else 0
    avg_loss_r = statistics.mean([v['r'] for v in r_values if v['r'] < 0]) if negative_r > 0 else 0
    
    print(f'\n  平均盈利 R: {avg_win_r:.3f}')
    print(f'  平均亏损 R: {avg_loss_r:.3f}')
    
    if positive_r > 0 and negative_r > 0:
        win_rate = positive_r / len(r_values)
        expected_r = win_rate * avg_win_r + (1 - win_rate) * avg_loss_r
        print(f'  期望 R: {expected_r:.4f} (正值表示长期盈利)')
    
    return {
        'r_distribution': r_values,
        'avg_r': statistics.mean(all_r),
    }


def analyze_combined_patterns(positions: List[Dict]) -> Dict:
    """组合特征模式分析 - 找出高/低胜率的特征组合"""
    print_section('组合特征模式分析')
    
    # 定义特征提取函数
    def get_rr_category(p: Dict) -> str:
        tp_dist = p.get('tp_distance_percent', 0)
        sl_dist = p.get('sl_distance_percent', 0)
        if sl_dist > 0:
            rr = tp_dist / sl_dist
            if rr < 1.0:
                return 'rr_low'
            elif rr < 1.5:
                return 'rr_mid'
            else:
                return 'rr_high'
        return 'rr_unknown'
    
    def get_sl_category(p: Dict) -> str:
        sl_dist = p.get('sl_distance_percent', 0)
        if sl_dist < 0.8:
            return 'sl_tight'
        elif sl_dist < 1.2:
            return 'sl_normal'
        else:
            return 'sl_wide'
    
    def get_holding_category(p: Dict) -> str:
        minutes = p.get('holding_minutes', 0)
        if minutes < 30:
            return 'hold_short'
        elif minutes < 120:
            return 'hold_mid'
        else:
            return 'hold_long'
    
    # 生成组合模式
    pattern_stats = defaultdict(list)
    
    for p in positions:
        side = p.get('side', 'unknown')
        rr_cat = get_rr_category(p)
        sl_cat = get_sl_category(p)
        
        # 方向 + R:R 组合
        pattern_stats[f'{side}_{rr_cat}'].append(p)
        
        # 方向 + 止损距离 组合
        pattern_stats[f'{side}_{sl_cat}'].append(p)
        
        # R:R + 止损距离 组合
        pattern_stats[f'{rr_cat}_{sl_cat}'].append(p)
        
        # 三要素组合
        pattern_stats[f'{side}_{rr_cat}_{sl_cat}'].append(p)
    
    # 输出高胜率和低胜率模式
    print_subsection('模式胜率排名')
    
    results = []
    for pattern, trades in pattern_stats.items():
        if len(trades) >= 20:  # 至少20个样本
            wr, wins, total = calc_winrate(trades)
            avg_pnl = calc_avg_pnl(trades)
            results.append({
                'pattern': pattern,
                'count': total,
                'winrate': wr,
                'avg_pnl': avg_pnl,
            })
    
    # 按胜率排序
    results.sort(key=lambda x: x['winrate'], reverse=True)
    
    print(f'\n  {"模式":35s} {"数量":>8s} {"胜率":>8s} {"平均PnL":>10s}')
    print(f'  {"-"*35} {"-"*8} {"-"*8} {"-"*10}')
    
    print('\n  【高胜率模式 TOP 10】')
    for r in results[:10]:
        emoji = '🔥' if r['winrate'] > 50 else ''
        print(f'  {r["pattern"]:35s} {r["count"]:>7d}  {r["winrate"]:>6.1f}%  ${r["avg_pnl"]:>8.2f} {emoji}')
    
    print('\n  【低胜率模式 BOTTOM 10】')
    for r in results[-10:]:
        emoji = '⚠️' if r['winrate'] < 40 else ''
        print(f'  {r["pattern"]:35s} {r["count"]:>7d}  {r["winrate"]:>6.1f}%  ${r["avg_pnl"]:>8.2f} {emoji}')
    
    return {'pattern_analysis': results}


def generate_learning_rules(positions: List[Dict]) -> List[Dict]:
    """生成可用于 Agent 学习的规则"""
    print_section('自动生成学习规则')
    
    rules = []
    
    # 1. 按 R:R 分析
    print_subsection('R:R 相关规则')
    for min_rr, max_rr, label in [(0, 1.0, 'R:R < 1.0'), (1.0, 1.5, 'R:R 1.0-1.5'), (1.5, 2.0, 'R:R 1.5-2.0'), (2.0, 10, 'R:R > 2.0')]:
        subset = []
        for p in positions:
            tp_dist = p.get('tp_distance_percent', 0)
            sl_dist = p.get('sl_distance_percent', 0)
            if sl_dist > 0:
                rr = tp_dist / sl_dist
                if min_rr <= rr < max_rr:
                    subset.append(p)
        
        if len(subset) >= 30:
            wr, _, total = calc_winrate(subset)
            avg_pnl = calc_avg_pnl(subset)
            
            rule_type = 'positive' if wr > 50 else 'negative' if wr < 40 else 'neutral'
            rule = {
                'feature': 'rr_ratio',
                'condition': label,
                'winrate': wr,
                'sample_count': total,
                'avg_pnl': avg_pnl,
                'type': rule_type,
            }
            rules.append(rule)
            
            if rule_type == 'positive':
                print(f'  ✅ {label}: 胜率 {wr:.1f}%, 样本 {total}, 建议优先考虑')
            elif rule_type == 'negative':
                print(f'  ❌ {label}: 胜率 {wr:.1f}%, 样本 {total}, 建议避免')
    
    # 2. 按止损距离分析
    print_subsection('止损距离相关规则')
    for min_sl, max_sl, label in [(0, 0.8, '止损 < 0.8%'), (0.8, 1.2, '止损 0.8-1.2%'), (1.2, 2.0, '止损 1.2-2.0%'), (2.0, 10, '止损 > 2.0%')]:
        subset = [p for p in positions if min_sl <= p.get('sl_distance_percent', 0) < max_sl]
        
        if len(subset) >= 30:
            wr, _, total = calc_winrate(subset)
            avg_pnl = calc_avg_pnl(subset)
            
            rule_type = 'positive' if wr > 50 else 'negative' if wr < 40 else 'neutral'
            rule = {
                'feature': 'sl_distance',
                'condition': label,
                'winrate': wr,
                'sample_count': total,
                'avg_pnl': avg_pnl,
                'type': rule_type,
            }
            rules.append(rule)
            
            if rule_type == 'positive':
                print(f'  ✅ {label}: 胜率 {wr:.1f}%, 样本 {total}')
            elif rule_type == 'negative':
                print(f'  ❌ {label}: 胜率 {wr:.1f}%, 样本 {total}')
    
    # 3. 按方向分析
    print_subsection('方向相关规则')
    for side_name, side_key in [('做多', 'long'), ('做空', 'short')]:
        subset = [p for p in positions if p.get('side') == side_key]
        if len(subset) >= 30:
            wr, _, total = calc_winrate(subset)
            avg_pnl = calc_avg_pnl(subset)
            
            rule_type = 'positive' if wr > 50 else 'negative' if wr < 40 else 'neutral'
            rule = {
                'feature': 'direction',
                'condition': side_name,
                'winrate': wr,
                'sample_count': total,
                'avg_pnl': avg_pnl,
                'type': rule_type,
            }
            rules.append(rule)
            
            emoji = '✅' if rule_type == 'positive' else '❌' if rule_type == 'negative' else '➖'
            print(f'  {emoji} {side_name}: 胜率 {wr:.1f}%, 样本 {total}')
    
    # 输出总结
    print_subsection('规则总结')
    positive_rules = [r for r in rules if r['type'] == 'positive']
    negative_rules = [r for r in rules if r['type'] == 'negative']
    
    print(f'\n  发现 {len(positive_rules)} 条高胜率规则:')
    for r in positive_rules:
        print(f'    - {r["feature"]}: {r["condition"]} (胜率 {r["winrate"]:.1f}%)')
    
    print(f'\n  发现 {len(negative_rules)} 条低胜率规则:')
    for r in negative_rules:
        print(f'    - {r["feature"]}: {r["condition"]} (胜率 {r["winrate"]:.1f}%)')
    
    return rules


def main():
    print('=' * 80)
    print('  胜率模式深度分析')
    print('=' * 80)
    
    # 加载数据
    positions = load_positions(DATA_FILE)
    print(f'\n加载交易记录: {len(positions)} 条')
    
    # 运行各项分析
    analyze_basic_stats(positions)
    analyze_rr_ratio_impact(positions)
    analyze_entry_distance_impact(positions)
    analyze_holding_time_impact(positions)
    analyze_time_of_day_impact(positions)
    analyze_r_multiple_distribution(positions)
    analyze_combined_patterns(positions)
    
    # 生成学习规则
    rules = generate_learning_rules(positions)
    
    print('\n' + '=' * 80)
    print('  分析完成')
    print('=' * 80)


if __name__ == '__main__':
    main()
