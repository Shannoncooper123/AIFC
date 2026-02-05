#!/usr/bin/env python3
"""
回测结果深度分析主入口
- 模块化设计
- 支持文本分析和图表生成
- 分析交易完整生命周期
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_loader import (
    load_positions, 
    enrich_positions_with_timing,
    get_time_range_from_positions,
    get_symbols_from_positions,
    kline_cache
)
from analyzers import (
    analyze_order_to_entry_timing,
    analyze_entry_to_exit_timing,
    analyze_complete_lifecycle,
    analyze_concurrent_margin,
    analyze_holding_duration,
    analyze_fee_usage
)
from visualizer import generate_all_charts

DATA_FILE = '/home/sunfayao/AIFC2/AIFC/analysis/all_positions.jsonl'


def basic_stats(positions):
    """基础统计"""
    print('\n' + '='*80)
    print('基础统计')
    print('='*80)
    
    long_trades = [p for p in positions if p.get('side') == 'long']
    short_trades = [p for p in positions if p.get('side') == 'short']
    
    print(f'\n总交易数: {len(positions)}')
    print(f'  做多: {len(long_trades)} ({len(long_trades)/len(positions)*100:.1f}%)')
    print(f'  做空: {len(short_trades)} ({len(short_trades)/len(positions)*100:.1f}%)')
    
    long_wins = len([p for p in long_trades if p.get('is_win')])
    short_wins = len([p for p in short_trades if p.get('is_win')])
    
    print(f'\n胜率:')
    print(f'  做多: {long_wins}/{len(long_trades)} = {long_wins/len(long_trades)*100:.1f}%')
    print(f'  做空: {short_wins}/{len(short_trades)} = {short_wins/len(short_trades)*100:.1f}%')
    
    long_pnl = sum(p.get('realized_pnl', 0) for p in long_trades)
    short_pnl = sum(p.get('realized_pnl', 0) for p in short_trades)
    total_pnl = long_pnl + short_pnl
    
    print(f'\n盈亏:')
    print(f'  做多: ${long_pnl:.2f}')
    print(f'  做空: ${short_pnl:.2f}')
    print(f'  总计: ${total_pnl:.2f}')
    
    tp_count = len([p for p in positions if p.get('exit_type') == 'tp'])
    sl_count = len([p for p in positions if p.get('exit_type') == 'sl'])
    
    print(f'\n平仓类型:')
    print(f'  止盈: {tp_count} ({tp_count/len(positions)*100:.1f}%)')
    print(f'  止损: {sl_count} ({sl_count/len(positions)*100:.1f}%)')
    
    return long_trades, short_trades


def print_summary_table(long_trades, short_trades):
    """输出汇总对比表格"""
    print('\n' + '='*80)
    print('核心数据汇总对比')
    print('='*80)
    
    long_wins = len([p for p in long_trades if p.get('is_win')])
    short_wins = len([p for p in short_trades if p.get('is_win')])
    long_wr = long_wins / len(long_trades) * 100 if long_trades else 0
    short_wr = short_wins / len(short_trades) * 100 if short_trades else 0
    
    long_pnl = sum(p.get('realized_pnl', 0) for p in long_trades)
    short_pnl = sum(p.get('realized_pnl', 0) for p in short_trades)
    
    long_sl = sum(p.get('sl_distance_percent', 0) for p in long_trades) / len(long_trades) if long_trades else 0
    short_sl = sum(p.get('sl_distance_percent', 0) for p in short_trades) / len(short_trades) if short_trades else 0
    long_tp = sum(p.get('tp_distance_percent', 0) for p in long_trades) / len(long_trades) if long_trades else 0
    short_tp = sum(p.get('tp_distance_percent', 0) for p in short_trades) / len(short_trades) if short_trades else 0
    
    long_rr = long_tp / long_sl if long_sl > 0 else 0
    short_rr = short_tp / short_sl if short_sl > 0 else 0
    
    print(f'''
┌─────────────────────────────────────────────────────────────────────────────┐
│                              核心数据对比                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  指标              │  做多                │  做空                │  差异     │
├─────────────────────────────────────────────────────────────────────────────┤
│  交易数量          │  {len(long_trades):>5d}               │  {len(short_trades):>5d}               │  {len(long_trades)-len(short_trades):>+5d}    │
│  胜率              │  {long_wr:>5.1f}%              │  {short_wr:>5.1f}%              │  {long_wr-short_wr:>+5.1f}%   │
│  总P&L             │  ${long_pnl:>9.2f}         │  ${short_pnl:>9.2f}         │  ${long_pnl-short_pnl:>+9.2f}│
│  平均止损距离      │  {long_sl:>5.3f}%              │  {short_sl:>5.3f}%              │  {long_sl-short_sl:>+5.3f}%   │
│  平均止盈距离      │  {long_tp:>5.3f}%              │  {short_tp:>5.3f}%              │  {long_tp-short_tp:>+5.3f}%   │
│  R:R (TP/SL)       │  {long_rr:>5.2f}               │  {short_rr:>5.2f}               │  {long_rr - short_rr:>+5.2f}    │
└─────────────────────────────────────────────────────────────────────────────┘
''')


def main():
    parser = argparse.ArgumentParser(description='回测结果深度分析')
    parser.add_argument('--no-charts', action='store_true', help='跳过图表生成')
    parser.add_argument('--show', action='store_true', help='显示图表窗口')
    parser.add_argument('--data', type=str, default=DATA_FILE, help='数据文件路径')
    args = parser.parse_args()
    
    print('='*80)
    print('回测结果深度分析')
    print('='*80)
    
    positions = load_positions(args.data)
    print(f'\n加载交易记录: {len(positions)} 条')
    
    positions = enrich_positions_with_timing(positions)
    print(f'已计算时间字段')
    
    long_trades, short_trades = basic_stats(positions)
    
    analyze_concurrent_margin(positions)
    
    analyze_holding_duration(positions)
    
    analyze_order_to_entry_timing(positions)
    
    analyze_entry_to_exit_timing(positions)
    
    analyze_complete_lifecycle(positions)

    analyze_fee_usage(positions)
    
    print_summary_table(long_trades, short_trades)
    
    if not args.no_charts:
        generate_all_charts(positions, show=args.show)
    
    print('\n' + '='*80)
    print('分析完成')
    print('='*80)


if __name__ == "__main__":
    main()
