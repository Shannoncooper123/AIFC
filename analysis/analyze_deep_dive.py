#!/usr/bin/env python3
"""
深度分析交易记录
重点分析：
1. 50+ bars 盈利交易的特征
2. 短期亏损交易的特征
3. Agent 执行情况分析
"""

import json
from collections import defaultdict
from datetime import datetime, timedelta
import statistics

def load_positions(filepath: str):
    """加载仓位数据，只加载 type=trade 的记录"""
    positions = []
    with open(filepath, 'r') as f:
        for line in f:
            if line.strip():
                data = json.loads(line)
                if data.get('type') == 'trade':
                    positions.append(data)
    return positions


def analyze_winning_trades(positions):
    """分析盈利交易的特征"""
    print("=" * 80)
    print("盈利交易深度分析 (50+ bars)")
    print("=" * 80)
    
    long_duration_wins = [p for p in positions 
                         if p.get('holding_bars', 0) >= 50 and p.get('is_win', False)]
    
    print(f"\n50+ bars 盈利交易数量: {len(long_duration_wins)}")
    
    if not long_duration_wins:
        print("没有符合条件的交易")
        return
    
    # 分析止损距离
    sl_distances = []
    tp_distances = []
    rr_ratios = []
    holding_bars_list = []
    pnl_list = []
    
    for p in long_duration_wins:
        entry = p.get('entry_price', 0)
        sl = p.get('sl_price', 0)
        tp = p.get('tp_price', 0)
        side = p.get('side', '')
        
        if entry and sl:
            if side == 'long':
                sl_dist = (entry - sl) / entry * 100
                tp_dist = (tp - entry) / entry * 100 if tp else 0
            else:
                sl_dist = (sl - entry) / entry * 100
                tp_dist = (entry - tp) / entry * 100 if tp else 0
            
            sl_distances.append(sl_dist)
            if tp_dist > 0:
                tp_distances.append(tp_dist)
                rr_ratios.append(tp_dist / sl_dist if sl_dist > 0 else 0)
        
        holding_bars_list.append(p.get('holding_bars', 0))
        pnl_list.append(p.get('realized_pnl', 0))
    
    print(f"\n【止损距离分析】")
    print(f"  平均止损距离: {statistics.mean(sl_distances):.2f}%")
    print(f"  中位数止损距离: {statistics.median(sl_distances):.2f}%")
    print(f"  最小止损距离: {min(sl_distances):.2f}%")
    print(f"  最大止损距离: {max(sl_distances):.2f}%")
    
    print(f"\n【止盈距离分析】")
    if tp_distances:
        print(f"  平均止盈距离: {statistics.mean(tp_distances):.2f}%")
        print(f"  中位数止盈距离: {statistics.median(tp_distances):.2f}%")
    
    print(f"\n【盈亏比分析】")
    if rr_ratios:
        print(f"  平均盈亏比: {statistics.mean(rr_ratios):.2f}:1")
        print(f"  中位数盈亏比: {statistics.median(rr_ratios):.2f}:1")
    
    print(f"\n【持仓时间分析】")
    print(f"  平均持仓 bars: {statistics.mean(holding_bars_list):.1f}")
    print(f"  中位数持仓 bars: {statistics.median(holding_bars_list):.1f}")
    print(f"  最长持仓 bars: {max(holding_bars_list)}")
    
    print(f"\n【盈利分析】")
    print(f"  总盈利: ${sum(pnl_list):.2f}")
    print(f"  平均单笔盈利: ${statistics.mean(pnl_list):.2f}")
    print(f"  最大单笔盈利: ${max(pnl_list):.2f}")
    
    # 按方向分组
    long_wins = [p for p in long_duration_wins if p.get('side') == 'long']
    short_wins = [p for p in long_duration_wins if p.get('side') == 'short']
    
    print(f"\n【方向分布】")
    print(f"  做多盈利: {len(long_wins)} 笔, P&L: ${sum(p.get('realized_pnl', 0) for p in long_wins):.2f}")
    print(f"  做空盈利: {len(short_wins)} 笔, P&L: ${sum(p.get('realized_pnl', 0) for p in short_wins):.2f}")
    
    # 输出几个典型案例
    print(f"\n【典型盈利案例 (前5笔)】")
    sorted_wins = sorted(long_duration_wins, key=lambda x: x.get('realized_pnl', 0), reverse=True)[:5]
    for i, p in enumerate(sorted_wins, 1):
        print(f"\n  案例 {i}:")
        print(f"    方向: {p.get('side')}")
        print(f"    入场价: ${p.get('entry_price', 0):.2f}")
        print(f"    止损价: ${p.get('sl_price', 0):.2f}")
        print(f"    止盈价: ${p.get('tp_price', 0):.2f}")
        print(f"    出场价: ${p.get('exit_price', 0):.2f}")
        print(f"    持仓 bars: {p.get('holding_bars', 0)}")
        print(f"    盈利: ${p.get('realized_pnl', 0):.2f}")
        print(f"    入场时间: {p.get('entry_time', '')}")
        print(f"    出场时间: {p.get('exit_time', '')}")
        
        # 计算实际盈亏比
        entry = p.get('entry_price', 0)
        sl = p.get('sl_price', 0)
        tp = p.get('tp_price', 0)
        side = p.get('side', '')
        if entry and sl and tp:
            if side == 'long':
                sl_dist = (entry - sl) / entry * 100
                tp_dist = (tp - entry) / entry * 100
            else:
                sl_dist = (sl - entry) / entry * 100
                tp_dist = (entry - tp) / entry * 100
            print(f"    止损距离: {sl_dist:.2f}%")
            print(f"    止盈距离: {tp_dist:.2f}%")
            print(f"    设定盈亏比: {tp_dist/sl_dist:.2f}:1" if sl_dist > 0 else "")


def analyze_losing_trades(positions):
    """分析短期亏损交易的特征"""
    print("\n" + "=" * 80)
    print("短期亏损交易深度分析 (1-5 bars)")
    print("=" * 80)
    
    short_duration_losses = [p for p in positions 
                            if p.get('holding_bars', 0) <= 5 and not p.get('is_win', False)]
    
    print(f"\n1-5 bars 亏损交易数量: {len(short_duration_losses)}")
    
    if not short_duration_losses:
        print("没有符合条件的交易")
        return
    
    # 分析止损距离
    sl_distances = []
    tp_distances = []
    rr_ratios = []
    
    for p in short_duration_losses:
        entry = p.get('entry_price', 0)
        sl = p.get('sl_price', 0)
        tp = p.get('tp_price', 0)
        side = p.get('side', '')
        
        if entry and sl:
            if side == 'long':
                sl_dist = (entry - sl) / entry * 100
                tp_dist = (tp - entry) / entry * 100 if tp else 0
            else:
                sl_dist = (sl - entry) / entry * 100
                tp_dist = (entry - tp) / entry * 100 if tp else 0
            
            sl_distances.append(sl_dist)
            if tp_dist > 0:
                tp_distances.append(tp_dist)
                rr_ratios.append(tp_dist / sl_dist if sl_dist > 0 else 0)
    
    print(f"\n【止损距离分析】")
    print(f"  平均止损距离: {statistics.mean(sl_distances):.2f}%")
    print(f"  中位数止损距离: {statistics.median(sl_distances):.2f}%")
    print(f"  最小止损距离: {min(sl_distances):.2f}%")
    print(f"  最大止损距离: {max(sl_distances):.2f}%")
    
    # 止损距离分布
    tight = len([d for d in sl_distances if d < 0.5])
    medium = len([d for d in sl_distances if 0.5 <= d < 1.0])
    wide = len([d for d in sl_distances if d >= 1.0])
    print(f"\n  止损距离分布:")
    print(f"    紧止损 (<0.5%): {tight} ({tight/len(sl_distances)*100:.1f}%)")
    print(f"    中等止损 (0.5%-1%): {medium} ({medium/len(sl_distances)*100:.1f}%)")
    print(f"    宽止损 (>1%): {wide} ({wide/len(sl_distances)*100:.1f}%)")
    
    print(f"\n【盈亏比分析】")
    if rr_ratios:
        print(f"  平均盈亏比: {statistics.mean(rr_ratios):.2f}:1")
        print(f"  中位数盈亏比: {statistics.median(rr_ratios):.2f}:1")
        
        # 盈亏比分布
        low_rr = len([r for r in rr_ratios if r < 2])
        medium_rr = len([r for r in rr_ratios if 2 <= r < 4])
        high_rr = len([r for r in rr_ratios if r >= 4])
        print(f"\n  盈亏比分布:")
        print(f"    低盈亏比 (<2:1): {low_rr} ({low_rr/len(rr_ratios)*100:.1f}%)")
        print(f"    中等盈亏比 (2:1-4:1): {medium_rr} ({medium_rr/len(rr_ratios)*100:.1f}%)")
        print(f"    高盈亏比 (>4:1): {high_rr} ({high_rr/len(rr_ratios)*100:.1f}%)")
    
    # 按方向分组
    long_losses = [p for p in short_duration_losses if p.get('side') == 'long']
    short_losses = [p for p in short_duration_losses if p.get('side') == 'short']
    
    print(f"\n【方向分布】")
    print(f"  做多亏损: {len(long_losses)} 笔, P&L: ${sum(p.get('realized_pnl', 0) for p in long_losses):.2f}")
    print(f"  做空亏损: {len(short_losses)} 笔, P&L: ${sum(p.get('realized_pnl', 0) for p in short_losses):.2f}")
    
    # 1 bar 止损的特殊分析
    one_bar_losses = [p for p in short_duration_losses if p.get('holding_bars', 0) == 1]
    print(f"\n【同K线止损分析 (1 bar)】")
    print(f"  数量: {len(one_bar_losses)}")
    if one_bar_losses:
        one_bar_sl_distances = []
        for p in one_bar_losses:
            entry = p.get('entry_price', 0)
            sl = p.get('sl_price', 0)
            side = p.get('side', '')
            if entry and sl:
                if side == 'long':
                    sl_dist = (entry - sl) / entry * 100
                else:
                    sl_dist = (sl - entry) / entry * 100
                one_bar_sl_distances.append(sl_dist)
        
        if one_bar_sl_distances:
            print(f"  平均止损距离: {statistics.mean(one_bar_sl_distances):.2f}%")
            print(f"  中位数止损距离: {statistics.median(one_bar_sl_distances):.2f}%")


def analyze_agent_behavior(positions):
    """分析 Agent 执行行为"""
    print("\n" + "=" * 80)
    print("Agent 执行行为分析")
    print("=" * 80)
    
    # 分析挂单价格与入场价格的关系
    limit_orders = [p for p in positions if p.get('order_type') == 'limit']
    print(f"\n限价单数量: {len(limit_orders)}")
    
    # 分析挂单到成交的时间
    order_to_fill_times = []
    for p in limit_orders:
        order_time = p.get('order_created_time', '')
        entry_time = p.get('entry_time', '')
        if order_time and entry_time:
            try:
                order_dt = datetime.fromisoformat(order_time.replace('Z', '+00:00'))
                entry_dt = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
                diff_hours = (entry_dt - order_dt).total_seconds() / 3600
                if diff_hours >= 0:
                    order_to_fill_times.append(diff_hours)
            except:
                pass
    
    if order_to_fill_times:
        print(f"\n【挂单到成交时间分析】")
        print(f"  平均等待时间: {statistics.mean(order_to_fill_times):.2f} 小时")
        print(f"  中位数等待时间: {statistics.median(order_to_fill_times):.2f} 小时")
        print(f"  最短等待时间: {min(order_to_fill_times):.2f} 小时")
        print(f"  最长等待时间: {max(order_to_fill_times):.2f} 小时")
        
        # 等待时间分布
        quick = len([t for t in order_to_fill_times if t < 1])
        medium = len([t for t in order_to_fill_times if 1 <= t < 4])
        long_wait = len([t for t in order_to_fill_times if t >= 4])
        print(f"\n  等待时间分布:")
        print(f"    快速成交 (<1h): {quick} ({quick/len(order_to_fill_times)*100:.1f}%)")
        print(f"    中等等待 (1-4h): {medium} ({medium/len(order_to_fill_times)*100:.1f}%)")
        print(f"    长时间等待 (>4h): {long_wait} ({long_wait/len(order_to_fill_times)*100:.1f}%)")
    
    # 分析盈亏比设定
    print(f"\n【盈亏比设定分析】")
    rr_ratios = []
    for p in positions:
        entry = p.get('entry_price', 0)
        sl = p.get('sl_price', 0)
        tp = p.get('tp_price', 0)
        side = p.get('side', '')
        if entry and sl and tp:
            if side == 'long':
                sl_dist = entry - sl
                tp_dist = tp - entry
            else:
                sl_dist = sl - entry
                tp_dist = entry - tp
            if sl_dist > 0:
                rr = tp_dist / sl_dist
                rr_ratios.append(rr)
    
    if rr_ratios:
        print(f"  平均设定盈亏比: {statistics.mean(rr_ratios):.2f}:1")
        print(f"  中位数设定盈亏比: {statistics.median(rr_ratios):.2f}:1")
        
        # 盈亏比与胜率的关系
        rr_buckets = {
            '1-2:1': {'trades': [], 'wins': 0},
            '2-3:1': {'trades': [], 'wins': 0},
            '3-4:1': {'trades': [], 'wins': 0},
            '4-5:1': {'trades': [], 'wins': 0},
            '5-6:1': {'trades': [], 'wins': 0},
            '6+:1': {'trades': [], 'wins': 0},
        }
        
        for i, p in enumerate(positions):
            if i < len(rr_ratios):
                rr = rr_ratios[i]
                is_win = p.get('is_win', False)
                
                if 1 <= rr < 2:
                    rr_buckets['1-2:1']['trades'].append(p)
                    if is_win: rr_buckets['1-2:1']['wins'] += 1
                elif 2 <= rr < 3:
                    rr_buckets['2-3:1']['trades'].append(p)
                    if is_win: rr_buckets['2-3:1']['wins'] += 1
                elif 3 <= rr < 4:
                    rr_buckets['3-4:1']['trades'].append(p)
                    if is_win: rr_buckets['3-4:1']['wins'] += 1
                elif 4 <= rr < 5:
                    rr_buckets['4-5:1']['trades'].append(p)
                    if is_win: rr_buckets['4-5:1']['wins'] += 1
                elif 5 <= rr < 6:
                    rr_buckets['5-6:1']['trades'].append(p)
                    if is_win: rr_buckets['5-6:1']['wins'] += 1
                elif rr >= 6:
                    rr_buckets['6+:1']['trades'].append(p)
                    if is_win: rr_buckets['6+:1']['wins'] += 1
        
        print(f"\n  盈亏比与胜率关系:")
        print(f"  {'盈亏比':<10} {'交易数':<10} {'胜率':<10} {'P&L':<15}")
        print(f"  {'-'*45}")
        for bucket, data in rr_buckets.items():
            count = len(data['trades'])
            if count > 0:
                winrate = data['wins'] / count * 100
                pnl = sum(p.get('realized_pnl', 0) for p in data['trades'])
                print(f"  {bucket:<10} {count:<10} {winrate:<9.1f}% ${pnl:<14.2f}")


def analyze_prompt_alignment(positions):
    """分析 Agent 是否符合提示词要求"""
    print("\n" + "=" * 80)
    print("提示词执行符合度分析")
    print("=" * 80)
    
    # 提示词要求：盈亏比 >= 1.5
    print(f"\n【盈亏比要求检查 (要求 >= 1.5:1)】")
    rr_violations = 0
    for p in positions:
        entry = p.get('entry_price', 0)
        sl = p.get('sl_price', 0)
        tp = p.get('tp_price', 0)
        side = p.get('side', '')
        if entry and sl and tp:
            if side == 'long':
                sl_dist = entry - sl
                tp_dist = tp - entry
            else:
                sl_dist = sl - entry
                tp_dist = entry - tp
            if sl_dist > 0:
                rr = tp_dist / sl_dist
                if rr < 1.5:
                    rr_violations += 1
    
    print(f"  违反盈亏比要求的交易: {rr_violations} ({rr_violations/len(positions)*100:.1f}%)")
    
    # 提示词要求：止损距离 0.5%-1%
    print(f"\n【止损距离检查 (建议 0.5%-1%)】")
    sl_too_tight = 0
    sl_too_wide = 0
    sl_ok = 0
    
    for p in positions:
        entry = p.get('entry_price', 0)
        sl = p.get('sl_price', 0)
        side = p.get('side', '')
        if entry and sl:
            if side == 'long':
                sl_dist = (entry - sl) / entry * 100
            else:
                sl_dist = (sl - entry) / entry * 100
            
            if sl_dist < 0.5:
                sl_too_tight += 1
            elif sl_dist > 1.0:
                sl_too_wide += 1
            else:
                sl_ok += 1
    
    total = sl_too_tight + sl_too_wide + sl_ok
    print(f"  止损过紧 (<0.5%): {sl_too_tight} ({sl_too_tight/total*100:.1f}%)")
    print(f"  止损适中 (0.5%-1%): {sl_ok} ({sl_ok/total*100:.1f}%)")
    print(f"  止损过宽 (>1%): {sl_too_wide} ({sl_too_wide/total*100:.1f}%)")
    
    # 分析各止损距离的胜率
    print(f"\n【止损距离与胜率关系】")
    sl_buckets = {
        '<0.3%': {'count': 0, 'wins': 0, 'pnl': 0},
        '0.3-0.5%': {'count': 0, 'wins': 0, 'pnl': 0},
        '0.5-0.7%': {'count': 0, 'wins': 0, 'pnl': 0},
        '0.7-1.0%': {'count': 0, 'wins': 0, 'pnl': 0},
        '1.0-1.5%': {'count': 0, 'wins': 0, 'pnl': 0},
        '>1.5%': {'count': 0, 'wins': 0, 'pnl': 0},
    }
    
    for p in positions:
        entry = p.get('entry_price', 0)
        sl = p.get('sl_price', 0)
        side = p.get('side', '')
        is_win = p.get('is_win', False)
        pnl = p.get('realized_pnl', 0)
        
        if entry and sl:
            if side == 'long':
                sl_dist = (entry - sl) / entry * 100
            else:
                sl_dist = (sl - entry) / entry * 100
            
            if sl_dist < 0.3:
                bucket = '<0.3%'
            elif sl_dist < 0.5:
                bucket = '0.3-0.5%'
            elif sl_dist < 0.7:
                bucket = '0.5-0.7%'
            elif sl_dist < 1.0:
                bucket = '0.7-1.0%'
            elif sl_dist < 1.5:
                bucket = '1.0-1.5%'
            else:
                bucket = '>1.5%'
            
            sl_buckets[bucket]['count'] += 1
            if is_win:
                sl_buckets[bucket]['wins'] += 1
            sl_buckets[bucket]['pnl'] += pnl
    
    print(f"  {'止损距离':<12} {'交易数':<10} {'胜率':<10} {'P&L':<15}")
    print(f"  {'-'*47}")
    for bucket, data in sl_buckets.items():
        if data['count'] > 0:
            winrate = data['wins'] / data['count'] * 100
            print(f"  {bucket:<12} {data['count']:<10} {winrate:<9.1f}% ${data['pnl']:<14.2f}")


def analyze_time_patterns(positions):
    """分析时间模式"""
    print("\n" + "=" * 80)
    print("时间模式分析")
    print("=" * 80)
    
    # 按入场时间的小时分析
    hour_stats = defaultdict(lambda: {'count': 0, 'wins': 0, 'pnl': 0})
    
    for p in positions:
        entry_time = p.get('entry_time', '')
        if entry_time:
            try:
                dt = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
                hour = dt.hour
                hour_stats[hour]['count'] += 1
                if p.get('is_win', False):
                    hour_stats[hour]['wins'] += 1
                hour_stats[hour]['pnl'] += p.get('realized_pnl', 0)
            except:
                pass
    
    print(f"\n【按入场小时分析 (UTC)】")
    print(f"  {'小时':<8} {'交易数':<10} {'胜率':<10} {'P&L':<15}")
    print(f"  {'-'*43}")
    for hour in sorted(hour_stats.keys()):
        data = hour_stats[hour]
        if data['count'] > 0:
            winrate = data['wins'] / data['count'] * 100
            print(f"  {hour:02d}:00    {data['count']:<10} {winrate:<9.1f}% ${data['pnl']:<14.2f}")


def main():
    filepath = "/Users/bytedance/Desktop/crypto_agentx/analysis/all_positions.jsonl"
    positions = load_positions(filepath)
    
    print(f"加载了 {len(positions)} 条交易记录\n")
    
    analyze_winning_trades(positions)
    analyze_losing_trades(positions)
    analyze_agent_behavior(positions)
    analyze_prompt_alignment(positions)
    analyze_time_patterns(positions)
    
    # 最终建议
    print("\n" + "=" * 80)
    print("基于分析的提示词优化建议")
    print("=" * 80)
    
    # 计算关键指标
    wins = [p for p in positions if p.get('is_win', False)]
    losses = [p for p in positions if not p.get('is_win', False)]
    
    long_trades = [p for p in positions if p.get('side') == 'long']
    short_trades = [p for p in positions if p.get('side') == 'short']
    
    long_winrate = len([p for p in long_trades if p.get('is_win', False)]) / len(long_trades) * 100 if long_trades else 0
    short_winrate = len([p for p in short_trades if p.get('is_win', False)]) / len(short_trades) * 100 if short_trades else 0
    
    short_duration_losses = [p for p in positions if p.get('holding_bars', 0) <= 5 and not p.get('is_win', False)]
    
    print(f"""
【核心问题诊断】

1. 盈亏比设定过高
   - 当前平均盈亏比约 5-6:1
   - 导致止盈目标过远，难以触达
   - 建议：将盈亏比要求从 1.5:1 调整为 2:1-3:1

2. 止损距离不合理
   - 大量交易止损距离 <0.5%，容易被噪音触发
   - 建议：最小止损距离设为 0.7%

3. 做多策略表现差
   - 做多胜率: {long_winrate:.1f}%
   - 做空胜率: {short_winrate:.1f}%
   - 建议：在震荡/下跌市场中减少做多频率

4. 同K线止损问题严重
   - {len(short_duration_losses)} 笔交易在5根K线内止损
   - 说明入场时机选择不佳
   - 建议：增加入场前的波动率检查

【提示词修改建议】

1. single_symbol_analysis_long_prompt.md:
   - 增加 "4h 趋势必须明确向上" 的硬性要求
   - 止损距离要求从 0.5%-1% 改为 0.7%-1.2%
   - 增加 "避免在高波动K线入场" 的检查

2. single_symbol_analysis_short_prompt.md:
   - 保持当前策略（做空表现较好）
   - 可适当放宽入场条件

3. opening_decision_prompt.md:
   - 盈亏比要求从 >= 1.5 改为 >= 2.0
   - 增加 "预期持仓时间" 评估
   - 增加 "当前K线波动幅度" 检查
""")


if __name__ == "__main__":
    main()
