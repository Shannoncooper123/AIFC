#!/usr/bin/env python3
"""
分析新的回测结果
- 基础统计
- 各时间段盈亏情况
- 保证金占用计算（从挂单时间到订单结束）
- 绘制每日累计亏损曲线
"""

import json
from collections import defaultdict
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

def load_positions(filepath):
    """加载交易数据"""
    positions = []
    with open(filepath, 'r') as f:
        for line in f:
            if line.strip():
                data = json.loads(line)
                if data.get('type') == 'trade':
                    positions.append(data)
    return positions

def get_hour_bucket(entry_time):
    """获取时段分类"""
    if not entry_time:
        return None
    try:
        hour = int(entry_time[11:13])
        if 0 <= hour < 6:
            return 'asia_night (00-06)'
        elif 6 <= hour < 12:
            return 'asia_day (06-12)'
        elif 12 <= hour < 18:
            return 'europe (12-18)'
        else:
            return 'us (18-24)'
    except:
        return None

def calculate_max_margin(positions):
    """
    计算最大保证金占用
    从 order_created_time（限价单创建时间）到 exit_time（平仓时间）
    """
    events = []
    for p in positions:
        order_time = p.get('order_created_time', p.get('order_time', p.get('entry_time', '')))
        exit_time = p.get('exit_time', '')
        margin = p.get('margin_usdt', 500)
        
        if order_time and exit_time:
            try:
                order_dt = datetime.fromisoformat(order_time.replace('Z', '+00:00'))
                exit_dt = datetime.fromisoformat(exit_time.replace('Z', '+00:00'))
                events.append(('open', order_dt, margin, p.get('trade_id')))
                events.append(('close', exit_dt, margin, p.get('trade_id')))
            except Exception as e:
                pass
    
    events.sort(key=lambda x: (x[1], 0 if x[0] == 'open' else 1))
    
    current_margin = 0
    max_margin = 0
    max_margin_time = None
    concurrent_positions = 0
    max_concurrent = 0
    
    margin_timeline = []
    
    for event_type, event_time, margin, trade_id in events:
        if event_type == 'open':
            current_margin += margin
            concurrent_positions += 1
        else:
            current_margin -= margin
            concurrent_positions -= 1
        
        margin_timeline.append((event_time, current_margin, concurrent_positions))
        
        if current_margin > max_margin:
            max_margin = current_margin
            max_margin_time = event_time
        
        if concurrent_positions > max_concurrent:
            max_concurrent = concurrent_positions
    
    return max_margin, max_margin_time, max_concurrent, margin_timeline

def plot_daily_pnl_curve(positions, output_path):
    """
    绘制每日累计盈亏曲线
    横轴：日期（1天为单位）
    纵轴：累计盈亏
    """
    daily_pnl = defaultdict(float)
    daily_trades = defaultdict(int)
    
    for p in positions:
        exit_date = p.get('exit_time', '')[:10]
        if exit_date:
            daily_pnl[exit_date] += p.get('realized_pnl', 0)
            daily_trades[exit_date] += 1
    
    sorted_dates = sorted(daily_pnl.keys())
    
    if not sorted_dates:
        print("没有有效的日期数据")
        return
    
    dates = [datetime.strptime(d, '%Y-%m-%d') for d in sorted_dates]
    daily_values = [daily_pnl[d] for d in sorted_dates]
    cumulative_pnl = np.cumsum(daily_values)
    
    fig, axes = plt.subplots(3, 1, figsize=(16, 14))
    
    ax1 = axes[0]
    ax1.fill_between(dates, cumulative_pnl, 0, 
                     where=(cumulative_pnl >= 0), color='green', alpha=0.3, label='盈利区间')
    ax1.fill_between(dates, cumulative_pnl, 0, 
                     where=(cumulative_pnl < 0), color='red', alpha=0.3, label='亏损区间')
    ax1.plot(dates, cumulative_pnl, 'b-', linewidth=1.5, label='累计盈亏')
    ax1.axhline(y=0, color='black', linestyle='--', linewidth=0.8)
    
    ax1.set_xlabel('日期', fontsize=12)
    ax1.set_ylabel('累计盈亏 (USDT)', fontsize=12)
    ax1.set_title('累计盈亏曲线 (Cumulative P&L)', fontsize=14, fontweight='bold')
    ax1.legend(loc='upper right')
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax1.xaxis.set_major_locator(mdates.MonthLocator())
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45)
    
    final_pnl = cumulative_pnl[-1]
    ax1.annotate(f'最终: ${final_pnl:,.2f}', 
                xy=(dates[-1], final_pnl),
                xytext=(10, 10), textcoords='offset points',
                fontsize=10, fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.7))
    
    ax2 = axes[1]
    colors = ['green' if v >= 0 else 'red' for v in daily_values]
    ax2.bar(dates, daily_values, color=colors, alpha=0.7, width=1.0)
    ax2.axhline(y=0, color='black', linestyle='--', linewidth=0.8)
    
    ax2.set_xlabel('日期', fontsize=12)
    ax2.set_ylabel('每日盈亏 (USDT)', fontsize=12)
    ax2.set_title('每日盈亏分布 (Daily P&L)', fontsize=14, fontweight='bold')
    ax2.grid(True, alpha=0.3, axis='y')
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax2.xaxis.set_major_locator(mdates.MonthLocator())
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)
    
    profit_days = sum(1 for v in daily_values if v > 0)
    loss_days = sum(1 for v in daily_values if v < 0)
    total_days = len(daily_values)
    avg_daily = np.mean(daily_values)
    max_daily_profit = max(daily_values)
    max_daily_loss = min(daily_values)
    
    stats_text = f'盈利天数: {profit_days} ({profit_days/total_days*100:.1f}%)\n'
    stats_text += f'亏损天数: {loss_days} ({loss_days/total_days*100:.1f}%)\n'
    stats_text += f'日均盈亏: ${avg_daily:,.2f}\n'
    stats_text += f'单日最大盈利: ${max_daily_profit:,.2f}\n'
    stats_text += f'单日最大亏损: ${max_daily_loss:,.2f}'
    
    ax2.text(0.02, 0.98, stats_text, transform=ax2.transAxes, fontsize=9,
            verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    
    ax3 = axes[2]
    trade_counts = [daily_trades[d] for d in sorted_dates]
    ax3.bar(dates, trade_counts, color='steelblue', alpha=0.7, width=1.0)
    
    ax3.set_xlabel('日期', fontsize=12)
    ax3.set_ylabel('交易笔数', fontsize=12)
    ax3.set_title('每日交易数量 (Daily Trade Count)', fontsize=14, fontweight='bold')
    ax3.grid(True, alpha=0.3, axis='y')
    ax3.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax3.xaxis.set_major_locator(mdates.MonthLocator())
    plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45)
    
    avg_trades = np.mean(trade_counts)
    ax3.axhline(y=avg_trades, color='red', linestyle='--', linewidth=1, label=f'平均: {avg_trades:.1f}笔/天')
    ax3.legend(loc='upper right')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    print(f'\n图表已保存至: {output_path}')
    
    return {
        'total_days': total_days,
        'profit_days': profit_days,
        'loss_days': loss_days,
        'avg_daily_pnl': avg_daily,
        'max_daily_profit': max_daily_profit,
        'max_daily_loss': max_daily_loss,
        'final_cumulative_pnl': final_pnl
    }

def main():
    filepath = '/Users/bytedance/Desktop/crypto_agentx/analysis/all_positions.jsonl'
    positions = load_positions(filepath)
    
    print('=' * 80)
    print('新回测结果分析')
    print('=' * 80)
    print(f'总交易数: {len(positions)}')
    
    if not positions:
        print("没有交易记录")
        return
    
    wins = [p for p in positions if p.get('is_win')]
    total_pnl = sum(p.get('realized_pnl', 0) for p in positions)
    win_rate = len(wins) / len(positions) * 100
    
    print(f'总胜率: {win_rate:.1f}% ({len(wins)}/{len(positions)})')
    print(f'总P&L: ${total_pnl:.2f}')
    
    wins_pnl = [p.get('realized_pnl', 0) for p in positions if p.get('is_win')]
    losses_pnl = [p.get('realized_pnl', 0) for p in positions if not p.get('is_win')]
    
    if wins_pnl:
        avg_win = sum(wins_pnl) / len(wins_pnl)
        print(f'平均盈利: ${avg_win:.2f}')
    if losses_pnl:
        avg_loss = sum(losses_pnl) / len(losses_pnl)
        print(f'平均亏损: ${avg_loss:.2f}')
    if wins_pnl and losses_pnl:
        print(f'盈亏比: {abs(avg_win/avg_loss):.2f}')
    
    print(f'\n' + '=' * 80)
    print('1. 按方向分析')
    print('=' * 80)
    for side in ['long', 'short']:
        side_trades = [p for p in positions if p.get('side') == side]
        if side_trades:
            side_wins = [p for p in side_trades if p.get('is_win')]
            side_pnl = sum(p.get('realized_pnl', 0) for p in side_trades)
            wr = len(side_wins) / len(side_trades) * 100
            print(f'{side}: {len(side_trades)} trades, {wr:.1f}% WR, P&L: ${side_pnl:.2f}')
    
    print(f'\n' + '=' * 80)
    print('2. 按出场类型分析')
    print('=' * 80)
    exit_types = defaultdict(lambda: {'wins': 0, 'total': 0, 'pnl': 0})
    for p in positions:
        et = p.get('exit_type', 'unknown')
        exit_types[et]['total'] += 1
        exit_types[et]['pnl'] += p.get('realized_pnl', 0)
        if p.get('is_win'):
            exit_types[et]['wins'] += 1
    
    for et, data in sorted(exit_types.items(), key=lambda x: -x[1]['total']):
        wr = data['wins'] / data['total'] * 100 if data['total'] > 0 else 0
        print(f'{et}: {data["total"]} trades, {wr:.1f}% WR, P&L: ${data["pnl"]:.2f}')
    
    print(f'\n' + '=' * 80)
    print('3. 止损距离分析')
    print('=' * 80)
    sl_buckets = defaultdict(lambda: {'wins': 0, 'total': 0, 'pnl': 0})
    for p in positions:
        sl_dist = p.get('sl_distance_percent', 0)
        if sl_dist < 0.5:
            bucket = '<0.5%'
        elif sl_dist < 1.0:
            bucket = '0.5-1.0%'
        elif sl_dist < 1.5:
            bucket = '1.0-1.5%'
        elif sl_dist < 2.0:
            bucket = '1.5-2.0%'
        else:
            bucket = '>2.0%'
        sl_buckets[bucket]['total'] += 1
        sl_buckets[bucket]['pnl'] += p.get('realized_pnl', 0)
        if p.get('is_win'):
            sl_buckets[bucket]['wins'] += 1
    
    for bucket in ['<0.5%', '0.5-1.0%', '1.0-1.5%', '1.5-2.0%', '>2.0%']:
        data = sl_buckets[bucket]
        if data['total'] > 0:
            wr = data['wins'] / data['total'] * 100
            print(f'{bucket}: {data["total"]} trades, {wr:.1f}% WR, P&L: ${data["pnl"]:.2f}')
    
    print(f'\n' + '=' * 80)
    print('4. 止盈距离分析')
    print('=' * 80)
    tp_buckets = defaultdict(lambda: {'wins': 0, 'total': 0, 'pnl': 0})
    for p in positions:
        tp_dist = p.get('tp_distance_percent', 0)
        if tp_dist < 1.0:
            bucket = '<1.0%'
        elif tp_dist < 2.0:
            bucket = '1.0-2.0%'
        elif tp_dist < 3.0:
            bucket = '2.0-3.0%'
        elif tp_dist < 5.0:
            bucket = '3.0-5.0%'
        else:
            bucket = '>5.0%'
        tp_buckets[bucket]['total'] += 1
        tp_buckets[bucket]['pnl'] += p.get('realized_pnl', 0)
        if p.get('is_win'):
            tp_buckets[bucket]['wins'] += 1
    
    for bucket in ['<1.0%', '1.0-2.0%', '2.0-3.0%', '3.0-5.0%', '>5.0%']:
        data = tp_buckets[bucket]
        if data['total'] > 0:
            wr = data['wins'] / data['total'] * 100
            print(f'{bucket}: {data["total"]} trades, {wr:.1f}% WR, P&L: ${data["pnl"]:.2f}')
    
    print(f'\n' + '=' * 80)
    print('5. 持仓时间分析')
    print('=' * 80)
    bar_buckets = defaultdict(lambda: {'wins': 0, 'total': 0, 'pnl': 0})
    for p in positions:
        bars = p.get('holding_bars', 0)
        if bars <= 2:
            bucket = '1-2 bars'
        elif bars <= 5:
            bucket = '3-5 bars'
        elif bars <= 10:
            bucket = '6-10 bars'
        elif bars <= 20:
            bucket = '11-20 bars'
        elif bars <= 50:
            bucket = '21-50 bars'
        else:
            bucket = '>50 bars'
        bar_buckets[bucket]['total'] += 1
        bar_buckets[bucket]['pnl'] += p.get('realized_pnl', 0)
        if p.get('is_win'):
            bar_buckets[bucket]['wins'] += 1
    
    for bucket in ['1-2 bars', '3-5 bars', '6-10 bars', '11-20 bars', '21-50 bars', '>50 bars']:
        data = bar_buckets[bucket]
        if data['total'] > 0:
            wr = data['wins'] / data['total'] * 100
            print(f'{bucket}: {data["total"]} trades, {wr:.1f}% WR, P&L: ${data["pnl"]:.2f}')
    
    print(f'\n' + '=' * 80)
    print('6. 时段分析')
    print('=' * 80)
    hour_buckets = defaultdict(lambda: {'wins': 0, 'total': 0, 'pnl': 0})
    for p in positions:
        hb = get_hour_bucket(p.get('entry_time', ''))
        if hb:
            hour_buckets[hb]['total'] += 1
            hour_buckets[hb]['pnl'] += p.get('realized_pnl', 0)
            if p.get('is_win'):
                hour_buckets[hb]['wins'] += 1
    
    for bucket in ['asia_night (00-06)', 'asia_day (06-12)', 'europe (12-18)', 'us (18-24)']:
        data = hour_buckets[bucket]
        if data['total'] > 0:
            wr = data['wins'] / data['total'] * 100
            print(f'{bucket}: {data["total"]} trades, {wr:.1f}% WR, P&L: ${data["pnl"]:.2f}')
    
    print(f'\n' + '=' * 80)
    print('7. 方向+时段组合分析')
    print('=' * 80)
    combo_buckets = defaultdict(lambda: {'wins': 0, 'total': 0, 'pnl': 0})
    for p in positions:
        side = p.get('side', '')
        hb = get_hour_bucket(p.get('entry_time', ''))
        if side and hb:
            key = f'{side} + {hb}'
            combo_buckets[key]['total'] += 1
            combo_buckets[key]['pnl'] += p.get('realized_pnl', 0)
            if p.get('is_win'):
                combo_buckets[key]['wins'] += 1
    
    for key, data in sorted(combo_buckets.items(), key=lambda x: x[1]['pnl']):
        if data['total'] > 0:
            wr = data['wins'] / data['total'] * 100
            print(f'{key}: {data["total"]} trades, {wr:.1f}% WR, P&L: ${data["pnl"]:.2f}')
    
    print(f'\n' + '=' * 80)
    print('8. 保证金占用分析（从限价单创建到订单结束）')
    print('=' * 80)
    
    max_margin, max_margin_time, max_concurrent, margin_timeline = calculate_max_margin(positions)
    
    print(f'\n最大并发保证金: ${max_margin:.2f}')
    print(f'最大并发持仓数: {max_concurrent}')
    if max_margin_time:
        print(f'最大保证金时间: {max_margin_time}')
    
    safety_factors = [1.0, 1.25, 1.5, 2.0]
    print(f'\n不同安全系数下的资金需求:')
    for sf in safety_factors:
        capital = max_margin * sf
        roi = total_pnl / capital * 100 if capital > 0 else 0
        print(f'  {sf}x: ${capital:,.2f} (预期收益率: {roi:.2f}%)')
    
    recommended_capital = max_margin * 1.5
    
    if positions:
        first_order = min(p.get('order_created_time', p.get('entry_time', '')) for p in positions if p.get('order_created_time') or p.get('entry_time'))
        last_exit = max(p.get('exit_time', '') for p in positions if p.get('exit_time'))
        try:
            first_dt = datetime.fromisoformat(first_order.replace('Z', '+00:00'))
            last_dt = datetime.fromisoformat(last_exit.replace('Z', '+00:00'))
            days = (last_dt - first_dt).days
            print(f'\n回测周期: {first_order[:10]} ~ {last_exit[:10]} ({days} 天)')
            if days > 0:
                daily_pnl_avg = total_pnl / days
                print(f'日均盈利: ${daily_pnl_avg:.2f}')
                
                print(f'\n年化收益率（不同资金规模）:')
                for sf in safety_factors:
                    capital = max_margin * sf
                    annualized_roi = (total_pnl / capital) * (365 / days) * 100 if capital > 0 else 0
                    print(f'  {sf}x (${capital:,.0f}): {annualized_roi:.2f}%')
        except:
            pass
    
    print(f'\n' + '=' * 80)
    print('9. 每日盈亏分布')
    print('=' * 80)
    
    daily_pnl = defaultdict(float)
    daily_trades = defaultdict(int)
    for p in positions:
        exit_date = p.get('exit_time', '')[:10]
        if exit_date:
            daily_pnl[exit_date] += p.get('realized_pnl', 0)
            daily_trades[exit_date] += 1
    
    print(f'\n盈利最多的日期 (Top 10):')
    for date, pnl in sorted(daily_pnl.items(), key=lambda x: -x[1])[:10]:
        trades = daily_trades[date]
        print(f'  {date}: ${pnl:.2f} ({trades} trades)')
    
    print(f'\n亏损最多的日期 (Top 10):')
    for date, pnl in sorted(daily_pnl.items(), key=lambda x: x[1])[:10]:
        trades = daily_trades[date]
        print(f'  {date}: ${pnl:.2f} ({trades} trades)')
    
    print(f'\n' + '=' * 80)
    print('10. 方向+止损距离组合分析')
    print('=' * 80)
    combo2 = defaultdict(lambda: {'wins': 0, 'total': 0, 'pnl': 0})
    for p in positions:
        side = p.get('side', '')
        sl_dist = p.get('sl_distance_percent', 0)
        if sl_dist < 0.5:
            sl_bucket = 'sl<0.5%'
        elif sl_dist < 1.0:
            sl_bucket = 'sl0.5-1%'
        elif sl_dist < 1.5:
            sl_bucket = 'sl1-1.5%'
        else:
            sl_bucket = 'sl>1.5%'
        key = f'{side} + {sl_bucket}'
        combo2[key]['total'] += 1
        combo2[key]['pnl'] += p.get('realized_pnl', 0)
        if p.get('is_win'):
            combo2[key]['wins'] += 1
    
    for key, data in sorted(combo2.items(), key=lambda x: x[1]['pnl']):
        if data['total'] > 0:
            wr = data['wins'] / data['total'] * 100
            print(f'{key}: {data["total"]} trades, {wr:.1f}% WR, P&L: ${data["pnl"]:.2f}')
    
    print(f'\n' + '=' * 80)
    print('11. 绘制盈亏曲线图')
    print('=' * 80)
    
    output_path = '/Users/bytedance/Desktop/crypto_agentx/analysis/pnl_curve.png'
    chart_stats = plot_daily_pnl_curve(positions, output_path)
    
    if chart_stats:
        print(f'\n图表统计:')
        print(f'  总交易天数: {chart_stats["total_days"]}')
        print(f'  盈利天数: {chart_stats["profit_days"]} ({chart_stats["profit_days"]/chart_stats["total_days"]*100:.1f}%)')
        print(f'  亏损天数: {chart_stats["loss_days"]} ({chart_stats["loss_days"]/chart_stats["total_days"]*100:.1f}%)')
        print(f'  日均盈亏: ${chart_stats["avg_daily_pnl"]:.2f}')
        print(f'  单日最大盈利: ${chart_stats["max_daily_profit"]:.2f}')
        print(f'  单日最大亏损: ${chart_stats["max_daily_loss"]:.2f}')
        print(f'  最终累计盈亏: ${chart_stats["final_cumulative_pnl"]:.2f}')

if __name__ == "__main__":
    main()
