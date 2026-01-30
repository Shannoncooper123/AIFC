#!/usr/bin/env python3
"""
分析低胜率问题

当前统计：
- 总交易: 400
- 胜率: 19.8%
- 盈利: 79 笔
- 亏损: 321 笔
- 累计 P&L: +$317.15

Long: 121 笔, 胜率 19.0%, P&L -$569.66, W/L 23/98
Short: 279 笔, 胜率 20.1%, P&L +$886.81, W/L 56/223
"""

import json
from collections import defaultdict
from datetime import datetime

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

def analyze_positions(positions):
    """分析仓位数据"""
    
    print("=" * 80)
    print("交易记录深度分析")
    print("=" * 80)
    
    # 基础统计 - 使用 is_win 字段判断胜负，realized_pnl 字段获取盈亏
    total = len(positions)
    wins = [p for p in positions if p.get('is_win', False)]
    losses = [p for p in positions if not p.get('is_win', False)]
    total_pnl = sum(p.get('realized_pnl', 0) for p in positions)
    
    print(f"\n总交易数: {total}")
    print(f"盈利笔数: {len(wins)} ({len(wins)/total*100:.1f}%)")
    print(f"亏损笔数: {len(losses)} ({len(losses)/total*100:.1f}%)")
    print(f"累计 P&L: ${total_pnl:.2f}")
    
    # 按方向分析
    print("\n" + "=" * 60)
    print("按方向分析")
    print("=" * 60)
    
    longs = [p for p in positions if p.get('side') == 'long']
    shorts = [p for p in positions if p.get('side') == 'short']
    
    for side, trades in [('LONG', longs), ('SHORT', shorts)]:
        if not trades:
            continue
        side_wins = [t for t in trades if t.get('is_win', False)]
        side_losses = [t for t in trades if not t.get('is_win', False)]
        total_pnl = sum(t.get('realized_pnl', 0) for t in trades)
        avg_win = sum(t.get('realized_pnl', 0) for t in side_wins) / len(side_wins) if side_wins else 0
        avg_loss = sum(t.get('realized_pnl', 0) for t in side_losses) / len(side_losses) if side_losses else 0
        
        print(f"\n{side}:")
        print(f"  总数: {len(trades)}")
        print(f"  胜率: {len(side_wins)/len(trades)*100:.1f}%")
        print(f"  总 P&L: ${total_pnl:.2f}")
        print(f"  平均盈利: ${avg_win:.2f}")
        print(f"  平均亏损: ${avg_loss:.2f}")
        print(f"  盈亏比: {abs(avg_win/avg_loss):.2f}:1" if avg_loss != 0 else "  盈亏比: N/A")
    
    # 按退出类型分析
    print("\n" + "=" * 60)
    print("按退出类型分析")
    print("=" * 60)
    
    exit_types = defaultdict(list)
    for p in positions:
        exit_type = p.get('exit_type', 'unknown')
        exit_types[exit_type].append(p)
    
    for exit_type, trades in sorted(exit_types.items(), key=lambda x: -len(x[1])):
        count = len(trades)
        pnl = sum(t.get('realized_pnl', 0) for t in trades)
        wins_count = len([t for t in trades if t.get('is_win', False)])
        print(f"\n{exit_type}:")
        print(f"  数量: {count} ({count/total*100:.1f}%)")
        print(f"  胜率: {wins_count/count*100:.1f}%")
        print(f"  总 P&L: ${pnl:.2f}")
    
    # 按持仓时间分析
    print("\n" + "=" * 60)
    print("按持仓时间分析")
    print("=" * 60)
    
    duration_buckets = {
        '1 bar (同K线止损)': [],
        '2-5 bars': [],
        '6-20 bars': [],
        '21-50 bars': [],
        '50+ bars': []
    }
    
    for p in positions:
        bars = p.get('holding_bars', 0)
        if bars <= 1:
            duration_buckets['1 bar (同K线止损)'].append(p)
        elif bars <= 5:
            duration_buckets['2-5 bars'].append(p)
        elif bars <= 20:
            duration_buckets['6-20 bars'].append(p)
        elif bars <= 50:
            duration_buckets['21-50 bars'].append(p)
        else:
            duration_buckets['50+ bars'].append(p)
    
    for bucket, trades in duration_buckets.items():
        if not trades:
            continue
        count = len(trades)
        pnl = sum(t.get('realized_pnl', 0) for t in trades)
        wins_count = len([t for t in trades if t.get('is_win', False)])
        sl_count = len([t for t in trades if t.get('exit_type') == 'sl'])
        print(f"\n{bucket}:")
        print(f"  数量: {count} ({count/total*100:.1f}%)")
        print(f"  胜率: {wins_count/count*100:.1f}%")
        print(f"  止损占比: {sl_count/count*100:.1f}%")
        print(f"  总 P&L: ${pnl:.2f}")
    
    # 止损距离分析
    print("\n" + "=" * 60)
    print("止损距离分析 (入场价与止损价的距离)")
    print("=" * 60)
    
    sl_distances = []
    for p in positions:
        entry = p.get('entry_price', 0)
        sl = p.get('sl_price', 0)
        side = p.get('side', '')
        if entry and sl:
            if side == 'long':
                dist_pct = (entry - sl) / entry * 100
            else:
                dist_pct = (sl - entry) / entry * 100
            sl_distances.append({
                'position': p,
                'sl_distance_pct': dist_pct
            })
    
    # 按止损距离分组
    tight_sl = [d for d in sl_distances if d['sl_distance_pct'] < 0.5]
    medium_sl = [d for d in sl_distances if 0.5 <= d['sl_distance_pct'] < 1.0]
    wide_sl = [d for d in sl_distances if d['sl_distance_pct'] >= 1.0]
    
    for name, group in [('紧止损 (<0.5%)', tight_sl), ('中等止损 (0.5%-1%)', medium_sl), ('宽止损 (>1%)', wide_sl)]:
        if not group:
            continue
        trades = [d['position'] for d in group]
        count = len(trades)
        pnl = sum(t.get('realized_pnl', 0) for t in trades)
        wins_count = len([t for t in trades if t.get('is_win', False)])
        avg_dist = sum(d['sl_distance_pct'] for d in group) / len(group)
        print(f"\n{name}:")
        print(f"  数量: {count}")
        print(f"  平均止损距离: {avg_dist:.2f}%")
        print(f"  胜率: {wins_count/count*100:.1f}%")
        print(f"  总 P&L: ${pnl:.2f}")
    
    # 盈亏比分析
    print("\n" + "=" * 60)
    print("盈亏比分析 (TP距离 / SL距离)")
    print("=" * 60)
    
    rr_ratios = []
    for p in positions:
        entry = p.get('entry_price', 0)
        tp = p.get('tp_price', 0)
        sl = p.get('sl_price', 0)
        side = p.get('side', '')
        if entry and tp and sl:
            if side == 'long':
                tp_dist = tp - entry
                sl_dist = entry - sl
            else:
                tp_dist = entry - tp
                sl_dist = sl - entry
            if sl_dist > 0:
                rr = tp_dist / sl_dist
                rr_ratios.append({
                    'position': p,
                    'rr_ratio': rr
                })
    
    # 按盈亏比分组
    low_rr = [d for d in rr_ratios if d['rr_ratio'] < 1.0]
    medium_rr = [d for d in rr_ratios if 1.0 <= d['rr_ratio'] < 2.0]
    high_rr = [d for d in rr_ratios if d['rr_ratio'] >= 2.0]
    
    for name, group in [('低盈亏比 (<1:1)', low_rr), ('中等盈亏比 (1:1-2:1)', medium_rr), ('高盈亏比 (>2:1)', high_rr)]:
        if not group:
            continue
        trades = [d['position'] for d in group]
        count = len(trades)
        pnl = sum(t.get('realized_pnl', 0) for t in trades)
        wins_count = len([t for t in trades if t.get('is_win', False)])
        avg_rr = sum(d['rr_ratio'] for d in group) / len(group)
        print(f"\n{name}:")
        print(f"  数量: {count}")
        print(f"  平均盈亏比: {avg_rr:.2f}:1")
        print(f"  胜率: {wins_count/count*100:.1f}%")
        print(f"  总 P&L: ${pnl:.2f}")
    
    # 按币种分析
    print("\n" + "=" * 60)
    print("按币种分析 (前10)")
    print("=" * 60)
    
    by_symbol = defaultdict(list)
    for p in positions:
        symbol = p.get('symbol', 'unknown')
        by_symbol[symbol].append(p)
    
    symbol_stats = []
    for symbol, trades in by_symbol.items():
        count = len(trades)
        pnl = sum(t.get('realized_pnl', 0) for t in trades)
        wins_count = len([t for t in trades if t.get('is_win', False)])
        winrate = wins_count / count * 100 if count > 0 else 0
        symbol_stats.append({
            'symbol': symbol,
            'count': count,
            'pnl': pnl,
            'winrate': winrate
        })
    
    # 按交易次数排序
    symbol_stats.sort(key=lambda x: -x['count'])
    
    print(f"\n{'币种':<12} {'交易数':>8} {'胜率':>8} {'P&L':>12}")
    print("-" * 44)
    for stat in symbol_stats[:10]:
        print(f"{stat['symbol']:<12} {stat['count']:>8} {stat['winrate']:>7.1f}% ${stat['pnl']:>10.2f}")
    
    # 问题诊断
    print("\n" + "=" * 80)
    print("问题诊断与建议")
    print("=" * 80)
    
    # 计算关键指标
    one_bar_count = len(duration_buckets['1 bar (同K线止损)'])
    one_bar_pct = one_bar_count / total * 100 if total > 0 else 0
    
    sl_exit_count = len(exit_types.get('sl', []))
    sl_exit_pct = sl_exit_count / total * 100 if total > 0 else 0
    
    tight_sl_count = len(tight_sl)
    tight_sl_pct = tight_sl_count / len(sl_distances) * 100 if sl_distances else 0
    
    low_rr_count = len(low_rr)
    low_rr_pct = low_rr_count / len(rr_ratios) * 100 if rr_ratios else 0
    
    print(f"""
【诊断结果】

1. 止损触发率过高
   - 止损退出占比: {sl_exit_pct:.1f}%
   - 说明: 大部分交易都是被止损出局，而非止盈

2. 同K线止损问题
   - 1 bar 持仓占比: {one_bar_pct:.1f}%
   - 说明: 入场后立即被止损，可能是止损设置过紧或入场时机不佳

3. 止损距离问题
   - 紧止损 (<0.5%) 占比: {tight_sl_pct:.1f}%
   - 说明: 止损距离过小，容易被市场噪音触发

4. 盈亏比问题
   - 低盈亏比 (<1:1) 占比: {low_rr_pct:.1f}%
   - 说明: 风险回报不对等，即使胜率提高也难以盈利

【改进建议】

1. 扩大止损距离
   - 建议止损距离至少 0.8%-1.5%
   - 避免被市场正常波动触发止损

2. 提高盈亏比要求
   - 建议最低盈亏比 1.5:1
   - 在提示词中强制要求检查盈亏比

3. 优化入场时机
   - 等待更明确的反转信号
   - 避免在波动剧烈时入场

4. 减少交易频率
   - 只在高置信度信号出现时交易
   - 宁可错过机会，也不做低质量交易

5. 方向偏好
   - 当前做空胜率略高于做多
   - 可以考虑在趋势不明时偏向做空
""")


if __name__ == "__main__":
    import sys
    
    filepath = sys.argv[1] if len(sys.argv) > 1 else "/Users/bytedance/Desktop/crypto_agentx/analysis/all_positions.jsonl"
    
    positions = load_positions(filepath)
    analyze_positions(positions)
