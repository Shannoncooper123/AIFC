#!/usr/bin/env python3
"""
可视化模块
- 使用matplotlib绑制各种分析图表
- 支持保存图片和显示
"""
import os
from collections import defaultdict
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import MaxNLocator
import numpy as np

plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

OUTPUT_DIR = '/Users/bytedance/Desktop/crypto_agentx/analysis/charts'


def ensure_output_dir():
    """确保输出目录存在"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def plot_holding_duration_distribution(positions: List[Dict], save: bool = True, show: bool = False) -> str:
    """
    绑制持仓时间分布图
    """
    ensure_output_dir()
    
    durations = []
    for p in positions:
        d = p.get('entry_to_exit_minutes')
        if d is not None and d > 0:
            durations.append(d)
    
    if not durations:
        print('无有效持仓时间数据')
        return ''
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle('持仓时间分布分析', fontsize=16, fontweight='bold')
    
    ax1 = axes[0, 0]
    bins = [0, 15, 30, 60, 120, 240, 480, 1440, max(durations) + 1]
    labels = ['0-15m', '15-30m', '30-60m', '1-2h', '2-4h', '4-8h', '8-24h', '24h+']
    counts, _ = np.histogram(durations, bins=bins)
    colors = plt.cm.Blues(np.linspace(0.3, 0.9, len(labels)))
    bars = ax1.bar(labels, counts, color=colors, edgecolor='black', linewidth=0.5)
    ax1.set_xlabel('持仓时间区间')
    ax1.set_ylabel('交易数量')
    ax1.set_title('持仓时间分布直方图')
    for bar, count in zip(bars, counts):
        if count > 0:
            ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 5, 
                    f'{count}\n({count/len(durations)*100:.1f}%)', 
                    ha='center', va='bottom', fontsize=8)
    
    ax2 = axes[0, 1]
    long_durations = [p.get('entry_to_exit_minutes') for p in positions 
                      if p.get('side') == 'long' and p.get('entry_to_exit_minutes')]
    short_durations = [p.get('entry_to_exit_minutes') for p in positions 
                       if p.get('side') == 'short' and p.get('entry_to_exit_minutes')]
    
    if long_durations and short_durations:
        bp = ax2.boxplot([long_durations, short_durations], labels=['做多', '做空'], 
                        patch_artist=True, showfliers=False)
        bp['boxes'][0].set_facecolor('#3498db')
        bp['boxes'][1].set_facecolor('#e74c3c')
        ax2.set_ylabel('持仓时间 (分钟)')
        ax2.set_title('做多 vs 做空 持仓时间对比')
        
        long_median = np.median(long_durations)
        short_median = np.median(short_durations)
        ax2.text(1, long_median, f'中位数: {long_median:.0f}m', ha='left', va='bottom', fontsize=9)
        ax2.text(2, short_median, f'中位数: {short_median:.0f}m', ha='left', va='bottom', fontsize=9)
    
    ax3 = axes[1, 0]
    win_durations = [p.get('entry_to_exit_minutes') for p in positions 
                     if p.get('is_win') and p.get('entry_to_exit_minutes')]
    loss_durations = [p.get('entry_to_exit_minutes') for p in positions 
                      if not p.get('is_win') and p.get('entry_to_exit_minutes')]
    
    if win_durations and loss_durations:
        bp = ax3.boxplot([win_durations, loss_durations], labels=['盈利', '亏损'], 
                        patch_artist=True, showfliers=False)
        bp['boxes'][0].set_facecolor('#27ae60')
        bp['boxes'][1].set_facecolor('#c0392b')
        ax3.set_ylabel('持仓时间 (分钟)')
        ax3.set_title('盈利 vs 亏损 持仓时间对比')
    
    ax4 = axes[1, 1]
    duration_buckets = [
        (0, 15, '0-15m'),
        (15, 30, '15-30m'),
        (30, 60, '30-60m'),
        (60, 120, '1-2h'),
        (120, 240, '2-4h'),
        (240, float('inf'), '4h+')
    ]
    
    bucket_stats = []
    for min_m, max_m, label in duration_buckets:
        subset = [p for p in positions 
                  if p.get('entry_to_exit_minutes') is not None 
                  and min_m <= p.get('entry_to_exit_minutes') < max_m]
        if subset:
            wins = len([p for p in subset if p.get('is_win')])
            wr = wins / len(subset) * 100
            bucket_stats.append((label, wr, len(subset)))
    
    if bucket_stats:
        labels_wr = [s[0] for s in bucket_stats]
        win_rates = [s[1] for s in bucket_stats]
        counts_wr = [s[2] for s in bucket_stats]
        
        colors_wr = ['#27ae60' if wr >= 55 else '#f39c12' if wr >= 50 else '#c0392b' for wr in win_rates]
        bars = ax4.bar(labels_wr, win_rates, color=colors_wr, edgecolor='black', linewidth=0.5)
        ax4.axhline(y=50, color='gray', linestyle='--', alpha=0.7, label='50%基准线')
        ax4.set_xlabel('持仓时间区间')
        ax4.set_ylabel('胜率 (%)')
        ax4.set_title('各时间段胜率分布')
        ax4.set_ylim(0, 100)
        
        for bar, wr, count in zip(bars, win_rates, counts_wr):
            ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1, 
                    f'{wr:.1f}%\n(n={count})', ha='center', va='bottom', fontsize=8)
    
    plt.tight_layout()
    
    filepath = os.path.join(OUTPUT_DIR, 'holding_duration_distribution.png')
    if save:
        plt.savefig(filepath, dpi=150, bbox_inches='tight')
        print(f'图表已保存: {filepath}')
    
    if show:
        plt.show()
    else:
        plt.close()
    
    return filepath


def plot_concurrent_margin(positions: List[Dict], save: bool = True, show: bool = False) -> str:
    """
    绑制并发持仓保证金分析图
    """
    ensure_output_dir()
    
    from data_loader import parse_datetime
    
    events = []
    for p in positions:
        entry_dt = parse_datetime(p.get('entry_time', ''))
        exit_dt = parse_datetime(p.get('exit_time', ''))
        margin = p.get('margin_usdt', 500)
        
        if entry_dt and exit_dt:
            events.append((entry_dt, 'open', margin))
            events.append((exit_dt, 'close', margin))
    
    if not events:
        print('无有效事件数据')
        return ''
    
    events.sort(key=lambda x: (x[0], 0 if x[1] == 'open' else 1))
    
    timestamps = []
    margin_values = []
    position_counts = []
    current_margin = 0
    current_positions = 0
    
    for event_time, event_type, margin in events:
        if event_type == 'open':
            current_margin += margin
            current_positions += 1
        else:
            current_margin -= margin
            current_positions -= 1
        
        timestamps.append(event_time)
        margin_values.append(current_margin)
        position_counts.append(current_positions)
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle('并发持仓保证金分析', fontsize=16, fontweight='bold')
    
    ax1 = axes[0, 0]
    ax1.plot(timestamps, margin_values, color='#3498db', linewidth=0.8, alpha=0.8)
    ax1.fill_between(timestamps, margin_values, alpha=0.3, color='#3498db')
    ax1.set_xlabel('时间')
    ax1.set_ylabel('保证金 (USDT)')
    ax1.set_title('保证金占用时间序列')
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    ax1.xaxis.set_major_locator(mdates.DayLocator(interval=7))
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha='right')
    
    max_margin = max(margin_values)
    max_idx = margin_values.index(max_margin)
    ax1.annotate(f'峰值: ${max_margin:.0f}', 
                xy=(timestamps[max_idx], max_margin),
                xytext=(10, 10), textcoords='offset points',
                fontsize=9, color='red',
                arrowprops=dict(arrowstyle='->', color='red', lw=1))
    
    ax2 = axes[0, 1]
    ax2.plot(timestamps, position_counts, color='#e74c3c', linewidth=0.8, alpha=0.8)
    ax2.fill_between(timestamps, position_counts, alpha=0.3, color='#e74c3c')
    ax2.set_xlabel('时间')
    ax2.set_ylabel('持仓数量')
    ax2.set_title('并发持仓数时间序列')
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    ax2.xaxis.set_major_locator(mdates.DayLocator(interval=7))
    ax2.yaxis.set_major_locator(MaxNLocator(integer=True))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha='right')
    
    ax3 = axes[1, 0]
    margin_buckets = {
        '0-500': 0, '500-1k': 0, '1k-2k': 0, 
        '2k-3k': 0, '3k-5k': 0, '5k+': 0
    }
    for m in margin_values:
        if m <= 500:
            margin_buckets['0-500'] += 1
        elif m <= 1000:
            margin_buckets['500-1k'] += 1
        elif m <= 2000:
            margin_buckets['1k-2k'] += 1
        elif m <= 3000:
            margin_buckets['2k-3k'] += 1
        elif m <= 5000:
            margin_buckets['3k-5k'] += 1
        else:
            margin_buckets['5k+'] += 1
    
    labels = list(margin_buckets.keys())
    values = list(margin_buckets.values())
    colors = plt.cm.Oranges(np.linspace(0.3, 0.9, len(labels)))
    
    non_zero = [(l, v, c) for l, v, c in zip(labels, values, colors) if v > 0]
    if non_zero:
        labels_nz, values_nz, colors_nz = zip(*non_zero)
        wedges, texts, autotexts = ax3.pie(values_nz, labels=labels_nz, autopct='%1.1f%%',
                                           colors=colors_nz, startangle=90)
        ax3.set_title('保证金占用分布')
    
    ax4 = axes[1, 1]
    position_buckets = defaultdict(int)
    for pc in position_counts:
        position_buckets[pc] += 1
    
    pos_labels = sorted(position_buckets.keys())
    pos_values = [position_buckets[k] for k in pos_labels]
    colors_pos = plt.cm.Greens(np.linspace(0.3, 0.9, len(pos_labels)))
    
    bars = ax4.bar([str(x) for x in pos_labels], pos_values, color=colors_pos, edgecolor='black', linewidth=0.5)
    ax4.set_xlabel('并发持仓数')
    ax4.set_ylabel('出现次数')
    ax4.set_title('并发持仓数分布')
    
    for bar, val in zip(bars, pos_values):
        if val > 0:
            pct = val / len(position_counts) * 100
            ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 5, 
                    f'{pct:.1f}%', ha='center', va='bottom', fontsize=7)
    
    plt.tight_layout()
    
    filepath = os.path.join(OUTPUT_DIR, 'concurrent_margin_analysis.png')
    if save:
        plt.savefig(filepath, dpi=150, bbox_inches='tight')
        print(f'图表已保存: {filepath}')
    
    if show:
        plt.show()
    else:
        plt.close()
    
    return filepath


def plot_order_to_entry_distribution(positions: List[Dict], save: bool = True, show: bool = False) -> str:
    """
    绑制下单到成交时间分布图
    """
    ensure_output_dir()
    
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
        print('无有效下单到成交时间数据')
        return ''
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle('限价单等待成交时间分析 (下单 → 持仓)', fontsize=16, fontweight='bold')
    
    ax1 = axes[0, 0]
    durations = [d['duration'] for d in order_to_entry]
    
    bins = [0, 5, 15, 30, 60, 120, 240, 480, max(durations) + 1]
    labels = ['0-5m', '5-15m', '15-30m', '30-60m', '1-2h', '2-4h', '4-8h', '8h+']
    counts, _ = np.histogram(durations, bins=bins)
    colors = plt.cm.Purples(np.linspace(0.3, 0.9, len(labels)))
    
    bars = ax1.bar(labels, counts, color=colors, edgecolor='black', linewidth=0.5)
    ax1.set_xlabel('等待成交时间')
    ax1.set_ylabel('订单数量')
    ax1.set_title('限价单等待成交时间分布')
    
    for bar, count in zip(bars, counts):
        if count > 0:
            ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 5, 
                    f'{count}\n({count/len(durations)*100:.1f}%)', 
                    ha='center', va='bottom', fontsize=8)
    
    ax2 = axes[0, 1]
    long_wait = [d['duration'] for d in order_to_entry if d['side'] == 'long']
    short_wait = [d['duration'] for d in order_to_entry if d['side'] == 'short']
    
    if long_wait and short_wait:
        bp = ax2.boxplot([long_wait, short_wait], labels=['做多', '做空'], 
                        patch_artist=True, showfliers=False)
        bp['boxes'][0].set_facecolor('#3498db')
        bp['boxes'][1].set_facecolor('#e74c3c')
        ax2.set_ylabel('等待时间 (分钟)')
        ax2.set_title('做多 vs 做空 等待成交时间对比')
        
        long_median = np.median(long_wait)
        short_median = np.median(short_wait)
        ax2.text(1, long_median, f'中位数: {long_median:.0f}m', ha='left', va='bottom', fontsize=9)
        ax2.text(2, short_median, f'中位数: {short_median:.0f}m', ha='left', va='bottom', fontsize=9)
    
    ax3 = axes[1, 0]
    instant_fill = len([d for d in order_to_entry if d['duration'] <= 5])
    quick_fill = len([d for d in order_to_entry if 5 < d['duration'] <= 30])
    slow_fill = len([d for d in order_to_entry if d['duration'] > 30])
    
    fill_labels = ['即时成交\n(≤5分钟)', '快速成交\n(5-30分钟)', '慢速成交\n(>30分钟)']
    fill_values = [instant_fill, quick_fill, slow_fill]
    fill_colors = ['#27ae60', '#f39c12', '#c0392b']
    
    wedges, texts, autotexts = ax3.pie(fill_values, labels=fill_labels, autopct='%1.1f%%',
                                       colors=fill_colors, startangle=90,
                                       explode=(0.05, 0, 0))
    ax3.set_title('成交速度分类')
    
    ax4 = axes[1, 1]
    wait_buckets = [
        (0, 5, '≤5m'),
        (5, 15, '5-15m'),
        (15, 30, '15-30m'),
        (30, 60, '30-60m'),
        (60, float('inf'), '>1h')
    ]
    
    bucket_stats = []
    for min_m, max_m, label in wait_buckets:
        subset = [d for d in order_to_entry if min_m <= d['duration'] < max_m]
        if subset:
            wins = len([d for d in subset if d['is_win']])
            wr = wins / len(subset) * 100
            bucket_stats.append((label, wr, len(subset)))
    
    if bucket_stats:
        labels_wr = [s[0] for s in bucket_stats]
        win_rates = [s[1] for s in bucket_stats]
        counts_wr = [s[2] for s in bucket_stats]
        
        colors_wr = ['#27ae60' if wr >= 55 else '#f39c12' if wr >= 50 else '#c0392b' for wr in win_rates]
        bars = ax4.bar(labels_wr, win_rates, color=colors_wr, edgecolor='black', linewidth=0.5)
        ax4.axhline(y=50, color='gray', linestyle='--', alpha=0.7)
        ax4.set_xlabel('等待成交时间')
        ax4.set_ylabel('胜率 (%)')
        ax4.set_title('等待时间与胜率关系')
        ax4.set_ylim(0, 100)
        
        for bar, wr, count in zip(bars, win_rates, counts_wr):
            ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1, 
                    f'{wr:.1f}%\n(n={count})', ha='center', va='bottom', fontsize=8)
    
    plt.tight_layout()
    
    filepath = os.path.join(OUTPUT_DIR, 'order_to_entry_distribution.png')
    if save:
        plt.savefig(filepath, dpi=150, bbox_inches='tight')
        print(f'图表已保存: {filepath}')
    
    if show:
        plt.show()
    else:
        plt.close()
    
    return filepath


def plot_entry_to_exit_by_result(positions: List[Dict], save: bool = True, show: bool = False) -> str:
    """
    绑制持仓到平仓时间分析图（按止盈/止损分类）
    """
    ensure_output_dir()
    
    tp_durations = []
    sl_durations = []
    
    for p in positions:
        d = p.get('entry_to_exit_minutes')
        exit_type = p.get('exit_type', '')
        if d is not None and d > 0:
            if exit_type == 'tp':
                tp_durations.append({
                    'duration': d,
                    'side': p.get('side', ''),
                    'pnl': p.get('realized_pnl', 0)
                })
            elif exit_type == 'sl':
                sl_durations.append({
                    'duration': d,
                    'side': p.get('side', ''),
                    'pnl': p.get('realized_pnl', 0)
                })
    
    if not tp_durations and not sl_durations:
        print('无有效持仓时间数据')
        return ''
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle('持仓到平仓时间分析 (持仓 → 止盈/止损)', fontsize=16, fontweight='bold')
    
    ax1 = axes[0, 0]
    if tp_durations and sl_durations:
        tp_vals = [d['duration'] for d in tp_durations]
        sl_vals = [d['duration'] for d in sl_durations]
        
        bp = ax1.boxplot([tp_vals, sl_vals], labels=['止盈', '止损'], 
                        patch_artist=True, showfliers=False)
        bp['boxes'][0].set_facecolor('#27ae60')
        bp['boxes'][1].set_facecolor('#c0392b')
        ax1.set_ylabel('持仓时间 (分钟)')
        ax1.set_title('止盈 vs 止损 持仓时间对比')
        
        tp_median = np.median(tp_vals)
        sl_median = np.median(sl_vals)
        tp_avg = np.mean(tp_vals)
        sl_avg = np.mean(sl_vals)
        
        ax1.text(1.2, tp_median, f'中位数: {tp_median:.0f}m\n平均: {tp_avg:.0f}m', 
                fontsize=9, va='center')
        ax1.text(2.2, sl_median, f'中位数: {sl_median:.0f}m\n平均: {sl_avg:.0f}m', 
                fontsize=9, va='center')
    
    ax2 = axes[0, 1]
    bins = [0, 15, 30, 60, 120, 240, 480, 1440, float('inf')]
    labels = ['0-15m', '15-30m', '30-60m', '1-2h', '2-4h', '4-8h', '8-24h', '24h+']
    
    if tp_durations:
        tp_vals = [d['duration'] for d in tp_durations]
        tp_counts, _ = np.histogram(tp_vals, bins=bins)
    else:
        tp_counts = [0] * len(labels)
    
    if sl_durations:
        sl_vals = [d['duration'] for d in sl_durations]
        sl_counts, _ = np.histogram(sl_vals, bins=bins)
    else:
        sl_counts = [0] * len(labels)
    
    x = np.arange(len(labels))
    width = 0.35
    
    bars1 = ax2.bar(x - width/2, tp_counts, width, label='止盈', color='#27ae60', edgecolor='black', linewidth=0.5)
    bars2 = ax2.bar(x + width/2, sl_counts, width, label='止损', color='#c0392b', edgecolor='black', linewidth=0.5)
    
    ax2.set_xlabel('持仓时间区间')
    ax2.set_ylabel('交易数量')
    ax2.set_title('止盈/止损 持仓时间分布对比')
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels, rotation=45, ha='right')
    ax2.legend()
    
    ax3 = axes[1, 0]
    if tp_durations:
        long_tp = [d['duration'] for d in tp_durations if d['side'] == 'long']
        short_tp = [d['duration'] for d in tp_durations if d['side'] == 'short']
        
        if long_tp and short_tp:
            bp = ax3.boxplot([long_tp, short_tp], labels=['做多止盈', '做空止盈'], 
                            patch_artist=True, showfliers=False)
            bp['boxes'][0].set_facecolor('#3498db')
            bp['boxes'][1].set_facecolor('#9b59b6')
            ax3.set_ylabel('持仓时间 (分钟)')
            ax3.set_title('止盈交易: 做多 vs 做空 持仓时间')
    
    ax4 = axes[1, 1]
    if sl_durations:
        long_sl = [d['duration'] for d in sl_durations if d['side'] == 'long']
        short_sl = [d['duration'] for d in sl_durations if d['side'] == 'short']
        
        if long_sl and short_sl:
            bp = ax4.boxplot([long_sl, short_sl], labels=['做多止损', '做空止损'], 
                            patch_artist=True, showfliers=False)
            bp['boxes'][0].set_facecolor('#e67e22')
            bp['boxes'][1].set_facecolor('#1abc9c')
            ax4.set_ylabel('持仓时间 (分钟)')
            ax4.set_title('止损交易: 做多 vs 做空 持仓时间')
    
    plt.tight_layout()
    
    filepath = os.path.join(OUTPUT_DIR, 'entry_to_exit_by_result.png')
    if save:
        plt.savefig(filepath, dpi=150, bbox_inches='tight')
        print(f'图表已保存: {filepath}')
    
    if show:
        plt.show()
    else:
        plt.close()
    
    return filepath


def plot_complete_trade_lifecycle(positions: List[Dict], save: bool = True, show: bool = False) -> str:
    """
    绑制完整交易生命周期分析图
    """
    ensure_output_dir()
    
    valid_positions = []
    for p in positions:
        order_to_entry = p.get('order_to_entry_minutes')
        entry_to_exit = p.get('entry_to_exit_minutes')
        if order_to_entry is not None and entry_to_exit is not None:
            valid_positions.append({
                'order_to_entry': order_to_entry,
                'entry_to_exit': entry_to_exit,
                'total': order_to_entry + entry_to_exit,
                'side': p.get('side', ''),
                'is_win': p.get('is_win', False),
                'exit_type': p.get('exit_type', ''),
                'pnl': p.get('realized_pnl', 0)
            })
    
    if not valid_positions:
        print('无有效完整生命周期数据')
        return ''
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle('交易完整生命周期分析 (下单 → 持仓 → 平仓)', fontsize=16, fontweight='bold')
    
    ax1 = axes[0, 0]
    order_to_entry = [p['order_to_entry'] for p in valid_positions]
    entry_to_exit = [p['entry_to_exit'] for p in valid_positions]
    
    ax1.scatter(order_to_entry, entry_to_exit, alpha=0.3, s=20, c='#3498db')
    ax1.set_xlabel('等待成交时间 (分钟)')
    ax1.set_ylabel('持仓时间 (分钟)')
    ax1.set_title('等待成交时间 vs 持仓时间 散点图')
    
    ax1.axhline(y=np.median(entry_to_exit), color='red', linestyle='--', alpha=0.5, label=f'持仓中位数: {np.median(entry_to_exit):.0f}m')
    ax1.axvline(x=np.median(order_to_entry), color='green', linestyle='--', alpha=0.5, label=f'等待中位数: {np.median(order_to_entry):.0f}m')
    ax1.legend(fontsize=8)
    
    ax2 = axes[0, 1]
    categories = ['下单→持仓', '持仓→平仓']
    avg_order_to_entry = np.mean(order_to_entry)
    avg_entry_to_exit = np.mean(entry_to_exit)
    
    colors = ['#9b59b6', '#e74c3c']
    bars = ax2.bar(categories, [avg_order_to_entry, avg_entry_to_exit], color=colors, edgecolor='black', linewidth=0.5)
    ax2.set_ylabel('平均时间 (分钟)')
    ax2.set_title('交易各阶段平均耗时')
    
    for bar, val in zip(bars, [avg_order_to_entry, avg_entry_to_exit]):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1, 
                f'{val:.1f}m\n({val/60:.2f}h)', ha='center', va='bottom', fontsize=10)
    
    ax3 = axes[1, 0]
    win_positions = [p for p in valid_positions if p['is_win']]
    loss_positions = [p for p in valid_positions if not p['is_win']]
    
    if win_positions and loss_positions:
        categories = ['等待成交', '持仓时间', '总时长']
        win_vals = [
            np.mean([p['order_to_entry'] for p in win_positions]),
            np.mean([p['entry_to_exit'] for p in win_positions]),
            np.mean([p['total'] for p in win_positions])
        ]
        loss_vals = [
            np.mean([p['order_to_entry'] for p in loss_positions]),
            np.mean([p['entry_to_exit'] for p in loss_positions]),
            np.mean([p['total'] for p in loss_positions])
        ]
        
        x = np.arange(len(categories))
        width = 0.35
        
        bars1 = ax3.bar(x - width/2, win_vals, width, label='盈利', color='#27ae60', edgecolor='black', linewidth=0.5)
        bars2 = ax3.bar(x + width/2, loss_vals, width, label='亏损', color='#c0392b', edgecolor='black', linewidth=0.5)
        
        ax3.set_ylabel('平均时间 (分钟)')
        ax3.set_title('盈利 vs 亏损 各阶段耗时对比')
        ax3.set_xticks(x)
        ax3.set_xticklabels(categories)
        ax3.legend()
    
    ax4 = axes[1, 1]
    total_durations = [p['total'] for p in valid_positions]
    
    bins = [0, 30, 60, 120, 240, 480, 960, max(total_durations) + 1]
    labels = ['0-30m', '30-60m', '1-2h', '2-4h', '4-8h', '8-16h', '16h+']
    counts, _ = np.histogram(total_durations, bins=bins)
    colors = plt.cm.viridis(np.linspace(0.2, 0.8, len(labels)))
    
    bars = ax4.bar(labels, counts, color=colors, edgecolor='black', linewidth=0.5)
    ax4.set_xlabel('总时长 (下单到平仓)')
    ax4.set_ylabel('交易数量')
    ax4.set_title('交易完整生命周期时长分布')
    
    for bar, count in zip(bars, counts):
        if count > 0:
            ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 5, 
                    f'{count}\n({count/len(total_durations)*100:.1f}%)', 
                    ha='center', va='bottom', fontsize=8)
    
    plt.tight_layout()
    
    filepath = os.path.join(OUTPUT_DIR, 'complete_trade_lifecycle.png')
    if save:
        plt.savefig(filepath, dpi=150, bbox_inches='tight')
        print(f'图表已保存: {filepath}')
    
    if show:
        plt.show()
    else:
        plt.close()
    
    return filepath


def plot_pnl_summary(positions: List[Dict], save: bool = True, show: bool = False) -> str:
    """
    绑制盈亏汇总图
    """
    ensure_output_dir()
    
    long_trades = [p for p in positions if p.get('side') == 'long']
    short_trades = [p for p in positions if p.get('side') == 'short']
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle('盈亏汇总分析', fontsize=16, fontweight='bold')
    
    ax1 = axes[0, 0]
    long_wins = len([p for p in long_trades if p.get('is_win')])
    long_losses = len(long_trades) - long_wins
    short_wins = len([p for p in short_trades if p.get('is_win')])
    short_losses = len(short_trades) - short_wins
    
    x = np.arange(2)
    width = 0.35
    
    bars1 = ax1.bar(x - width/2, [long_wins, short_wins], width, label='盈利', color='#27ae60', edgecolor='black', linewidth=0.5)
    bars2 = ax1.bar(x + width/2, [long_losses, short_losses], width, label='亏损', color='#c0392b', edgecolor='black', linewidth=0.5)
    
    ax1.set_ylabel('交易数量')
    ax1.set_title('做多 vs 做空 盈亏次数对比')
    ax1.set_xticks(x)
    ax1.set_xticklabels(['做多', '做空'])
    ax1.legend()
    
    long_wr = long_wins / len(long_trades) * 100 if long_trades else 0
    short_wr = short_wins / len(short_trades) * 100 if short_trades else 0
    ax1.text(0, max(long_wins, long_losses) + 20, f'胜率: {long_wr:.1f}%', ha='center', fontsize=10)
    ax1.text(1, max(short_wins, short_losses) + 20, f'胜率: {short_wr:.1f}%', ha='center', fontsize=10)
    
    ax2 = axes[0, 1]
    long_pnl = sum(p.get('realized_pnl', 0) for p in long_trades)
    short_pnl = sum(p.get('realized_pnl', 0) for p in short_trades)
    
    colors = ['#27ae60' if pnl >= 0 else '#c0392b' for pnl in [long_pnl, short_pnl]]
    bars = ax2.bar(['做多', '做空'], [long_pnl, short_pnl], color=colors, edgecolor='black', linewidth=0.5)
    ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax2.set_ylabel('总盈亏 (USDT)')
    ax2.set_title('做多 vs 做空 总盈亏对比')
    
    for bar, pnl in zip(bars, [long_pnl, short_pnl]):
        y_pos = bar.get_height() + 50 if pnl >= 0 else bar.get_height() - 100
        ax2.text(bar.get_x() + bar.get_width()/2, y_pos, f'${pnl:.2f}', ha='center', fontsize=10)
    
    ax3 = axes[1, 0]
    all_pnl = [p.get('realized_pnl', 0) for p in positions]
    cumulative_pnl = np.cumsum(all_pnl)
    
    ax3.plot(range(len(cumulative_pnl)), cumulative_pnl, color='#3498db', linewidth=1)
    ax3.fill_between(range(len(cumulative_pnl)), cumulative_pnl, 
                     where=[p >= 0 for p in cumulative_pnl], alpha=0.3, color='#27ae60')
    ax3.fill_between(range(len(cumulative_pnl)), cumulative_pnl, 
                     where=[p < 0 for p in cumulative_pnl], alpha=0.3, color='#c0392b')
    ax3.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax3.set_xlabel('交易序号')
    ax3.set_ylabel('累计盈亏 (USDT)')
    ax3.set_title('累计盈亏曲线')
    
    ax4 = axes[1, 1]
    pnl_buckets = defaultdict(int)
    for pnl in all_pnl:
        if pnl < -40:
            pnl_buckets['<-40'] += 1
        elif pnl < -20:
            pnl_buckets['-40~-20'] += 1
        elif pnl < 0:
            pnl_buckets['-20~0'] += 1
        elif pnl < 20:
            pnl_buckets['0~20'] += 1
        elif pnl < 40:
            pnl_buckets['20~40'] += 1
        else:
            pnl_buckets['>40'] += 1
    
    labels = ['<-40', '-40~-20', '-20~0', '0~20', '20~40', '>40']
    values = [pnl_buckets[l] for l in labels]
    colors = ['#c0392b', '#e74c3c', '#f39c12', '#f1c40f', '#2ecc71', '#27ae60']
    
    bars = ax4.bar(labels, values, color=colors, edgecolor='black', linewidth=0.5)
    ax4.set_xlabel('单笔盈亏区间 (USDT)')
    ax4.set_ylabel('交易数量')
    ax4.set_title('单笔盈亏分布')
    
    for bar, val in zip(bars, values):
        if val > 0:
            ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 5, 
                    f'{val}', ha='center', va='bottom', fontsize=9)
    
    plt.tight_layout()
    
    filepath = os.path.join(OUTPUT_DIR, 'pnl_summary.png')
    if save:
        plt.savefig(filepath, dpi=150, bbox_inches='tight')
        print(f'图表已保存: {filepath}')
    
    if show:
        plt.show()
    else:
        plt.close()
    
    return filepath


def generate_all_charts(positions: List[Dict], show: bool = False):
    """
    生成所有图表
    """
    print('\n' + '='*60)
    print('开始生成分析图表...')
    print('='*60)
    
    charts = []
    
    print('\n[1/5] 生成持仓时间分布图...')
    charts.append(plot_holding_duration_distribution(positions, save=True, show=show))
    
    print('\n[2/5] 生成并发保证金分析图...')
    charts.append(plot_concurrent_margin(positions, save=True, show=show))
    
    print('\n[3/5] 生成下单到成交时间分布图...')
    charts.append(plot_order_to_entry_distribution(positions, save=True, show=show))
    
    print('\n[4/5] 生成持仓到平仓时间分析图...')
    charts.append(plot_entry_to_exit_by_result(positions, save=True, show=show))
    
    print('\n[5/5] 生成完整交易生命周期图...')
    charts.append(plot_complete_trade_lifecycle(positions, save=True, show=show))
    
    print('\n[额外] 生成盈亏汇总图...')
    charts.append(plot_pnl_summary(positions, save=True, show=show))
    
    print('\n' + '='*60)
    print(f'图表生成完成! 共 {len([c for c in charts if c])} 张图表')
    print(f'保存目录: {OUTPUT_DIR}')
    print('='*60)
    
    return charts
