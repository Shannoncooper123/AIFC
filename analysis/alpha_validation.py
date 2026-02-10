#!/usr/bin/env python3
"""
Alpha 验证测试
- 对比 Agent 策略与随机基准的胜率差异
- 验证 Agent 是否真的有预测能力
- 使用相同时间点、相同止盈止损设置进行公平对比
"""
import json
import random
import sys
import os
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple
import statistics
import pandas as pd
import numpy as np

POSITIONS_FILE = '/Users/bytedance/Desktop/crypto_agentx/analysis/all_positions.jsonl'
KLINE_CACHE_DIR = '/Users/bytedance/Desktop/crypto_agentx/backend/modules/data/kline_cache'


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


def load_kline_data(symbol: str, interval: str = '1m') -> Optional[pd.DataFrame]:
    """从 parquet 文件加载 K 线数据"""
    filepath = os.path.join(KLINE_CACHE_DIR, symbol, f'{interval}.parquet')
    if not os.path.exists(filepath):
        print(f"  警告: K线文件不存在 {filepath}")
        return None
    
    try:
        df = pd.read_parquet(filepath)
        if 'open_time' in df.columns:
            df['timestamp'] = pd.to_datetime(df['open_time'], unit='ms', utc=True)
        elif 'timestamp' in df.columns:
            if df['timestamp'].dtype == 'int64':
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
        df = df.set_index('timestamp').sort_index()
        return df
    except Exception as e:
        print(f"  错误: 加载K线失败 {filepath}: {e}")
        return None


def parse_datetime(time_str: str) -> Optional[datetime]:
    """解析ISO格式时间字符串"""
    if not time_str:
        return None
    try:
        return datetime.fromisoformat(time_str.replace('Z', '+00:00'))
    except:
        return None


def simulate_trade_outcome(
    kline_df: pd.DataFrame,
    entry_time: datetime,
    entry_price: float,
    side: str,
    tp_distance_pct: float,
    sl_distance_pct: float,
    max_holding_minutes: int = 1440,
) -> Dict:
    """
    模拟单笔交易的结果
    
    Args:
        kline_df: 1分钟K线数据
        entry_time: 入场时间
        entry_price: 入场价格
        side: 'long' 或 'short'
        tp_distance_pct: 止盈距离百分比
        sl_distance_pct: 止损距离百分比
        max_holding_minutes: 最大持仓时间（分钟）
    
    Returns:
        交易结果字典
    """
    if side == 'long':
        tp_price = entry_price * (1 + tp_distance_pct / 100)
        sl_price = entry_price * (1 - sl_distance_pct / 100)
    else:
        tp_price = entry_price * (1 - tp_distance_pct / 100)
        sl_price = entry_price * (1 + sl_distance_pct / 100)
    
    end_time = entry_time + timedelta(minutes=max_holding_minutes)
    
    try:
        future_klines = kline_df.loc[entry_time:end_time]
    except:
        return {'success': False, 'reason': 'no_data'}
    
    if len(future_klines) == 0:
        return {'success': False, 'reason': 'no_data'}
    
    for idx, row in future_klines.iterrows():
        high = row.get('high', row.get('High', 0))
        low = row.get('low', row.get('Low', 0))
        
        if side == 'long':
            if high >= tp_price:
                return {
                    'success': True,
                    'exit_type': 'tp',
                    'is_win': True,
                    'holding_minutes': (idx - entry_time).total_seconds() / 60,
                }
            if low <= sl_price:
                return {
                    'success': True,
                    'exit_type': 'sl',
                    'is_win': False,
                    'holding_minutes': (idx - entry_time).total_seconds() / 60,
                }
        else:
            if low <= tp_price:
                return {
                    'success': True,
                    'exit_type': 'tp',
                    'is_win': True,
                    'holding_minutes': (idx - entry_time).total_seconds() / 60,
                }
            if high >= sl_price:
                return {
                    'success': True,
                    'exit_type': 'sl',
                    'is_win': False,
                    'holding_minutes': (idx - entry_time).total_seconds() / 60,
                }
    
    return {
        'success': True,
        'exit_type': 'timeout',
        'is_win': None,
        'holding_minutes': max_holding_minutes,
    }


def run_random_baseline_test(
    positions: List[Dict],
    kline_df: pd.DataFrame,
) -> Dict:
    """
    运行随机基准测试（优化版：单次模拟，使用理论概率）
    
    核心思想：
    - 对于每笔交易，计算如果随机选择方向，期望胜率是多少
    - 由于止盈止损不对称，随机方向的期望胜率不一定是50%
    - 通过同时模拟做多和做空，计算理论随机胜率
    """
    valid_positions = []
    
    for p in positions:
        entry_time = parse_datetime(p.get('entry_time', ''))
        if entry_time is None:
            continue
        
        tp_dist = p.get('tp_distance_percent', 0)
        sl_dist = p.get('sl_distance_percent', 0)
        entry_price = p.get('entry_price', 0)
        
        if tp_dist <= 0 or sl_dist <= 0 or entry_price <= 0:
            continue
        
        valid_positions.append({
            'entry_time': entry_time,
            'entry_price': entry_price,
            'agent_side': p.get('side', ''),
            'tp_distance_pct': tp_dist,
            'sl_distance_pct': sl_dist,
            'agent_is_win': p.get('is_win', False),
            'agent_exit_type': p.get('exit_type', ''),
        })
    
    print(f"\n有效交易数: {len(valid_positions)}")
    
    agent_wins = sum(1 for p in valid_positions if p['agent_is_win'])
    agent_winrate = agent_wins / len(valid_positions) * 100
    
    random_wins_total = 0
    random_trades_total = 0
    
    total = len(valid_positions)
    for i, p in enumerate(valid_positions):
        if i % 500 == 0:
            print(f"  进度: {i}/{total} ({i/total*100:.1f}%)", end='\r')
        
        long_result = simulate_trade_outcome(
            kline_df=kline_df,
            entry_time=p['entry_time'],
            entry_price=p['entry_price'],
            side='long',
            tp_distance_pct=p['tp_distance_pct'],
            sl_distance_pct=p['sl_distance_pct'],
            max_holding_minutes=1440,
        )
        
        short_result = simulate_trade_outcome(
            kline_df=kline_df,
            entry_time=p['entry_time'],
            entry_price=p['entry_price'],
            side='short',
            tp_distance_pct=p['tp_distance_pct'],
            sl_distance_pct=p['sl_distance_pct'],
            max_holding_minutes=1440,
        )
        
        if long_result['success'] and long_result['is_win'] is not None:
            random_trades_total += 1
            if long_result['is_win']:
                random_wins_total += 0.5
        
        if short_result['success'] and short_result['is_win'] is not None:
            random_trades_total += 1
            if short_result['is_win']:
                random_wins_total += 0.5
    
    print(f"  进度: {total}/{total} (100.0%)   ")
    
    avg_random_winrate = (random_wins_total / (random_trades_total / 2)) * 100 if random_trades_total > 0 else 0
    
    return {
        'agent_winrate': agent_winrate,
        'agent_wins': agent_wins,
        'agent_total': len(valid_positions),
        'random_winrate_mean': avg_random_winrate,
        'random_winrate_std': 0,
        'alpha': agent_winrate - avg_random_winrate,
    }


def run_direction_accuracy_test(
    positions: List[Dict],
    kline_df: pd.DataFrame,
    lookahead_minutes: List[int] = [5, 15, 30, 60, 120],
) -> Dict:
    """
    测试 Agent 方向预测准确率（向量化优化版）
    
    不考虑止盈止损，只看 Agent 预测的方向是否正确。
    如果 Agent 说"做多"，那么 N 分钟后价格是否真的上涨？
    """
    results = {}
    
    valid_positions = []
    for p in positions:
        entry_time = parse_datetime(p.get('entry_time', ''))
        entry_price = p.get('entry_price', 0)
        side = p.get('side', '')
        
        if entry_time and entry_price > 0 and side in ['long', 'short']:
            valid_positions.append({
                'entry_time': entry_time,
                'entry_price': entry_price,
                'side': side,
            })
    
    print(f"\n方向预测测试 - 有效交易数: {len(valid_positions)}")
    
    close_col = 'close' if 'close' in kline_df.columns else 'Close'
    
    for lookahead in lookahead_minutes:
        print(f"  测试 {lookahead} 分钟窗口...", end='\r')
        correct = 0
        total = 0
        
        for p in valid_positions:
            target_time = p['entry_time'] + timedelta(minutes=lookahead)
            
            try:
                mask = (kline_df.index >= p['entry_time']) & (kline_df.index <= target_time)
                future_rows = kline_df.loc[mask]
                
                if len(future_rows) == 0:
                    continue
                
                future_price = future_rows.iloc[-1][close_col]
                
                if future_price <= 0:
                    continue
                
                total += 1
                
                if p['side'] == 'long':
                    if future_price > p['entry_price']:
                        correct += 1
                else:
                    if future_price < p['entry_price']:
                        correct += 1
                        
            except Exception:
                continue
        
        accuracy = correct / total * 100 if total > 0 else 0
        results[lookahead] = {
            'accuracy': accuracy,
            'correct': correct,
            'total': total,
            'is_significant': accuracy > 52 or accuracy < 48,
        }
        print(f"  测试 {lookahead} 分钟窗口: {accuracy:.1f}%    ")
    
    return results


def run_same_direction_vs_opposite_test(
    positions: List[Dict],
    kline_df: pd.DataFrame,
) -> Dict:
    """
    对比测试：
    1. 使用 Agent 的方向
    2. 使用 Agent 的反向
    
    如果反向胜率更高，说明 Agent 的预测是错误的
    """
    valid_positions = []
    
    for p in positions:
        entry_time = parse_datetime(p.get('entry_time', ''))
        if entry_time is None:
            continue
        
        tp_dist = p.get('tp_distance_percent', 0)
        sl_dist = p.get('sl_distance_percent', 0)
        entry_price = p.get('entry_price', 0)
        side = p.get('side', '')
        
        if tp_dist <= 0 or sl_dist <= 0 or entry_price <= 0 or side not in ['long', 'short']:
            continue
        
        valid_positions.append({
            'entry_time': entry_time,
            'entry_price': entry_price,
            'agent_side': side,
            'tp_distance_pct': tp_dist,
            'sl_distance_pct': sl_dist,
        })
    
    agent_wins = 0
    opposite_wins = 0
    total = 0
    
    n = len(valid_positions)
    for i, p in enumerate(valid_positions):
        if i % 500 == 0:
            print(f"  进度: {i}/{n} ({i/n*100:.1f}%)", end='\r')
        
        opposite_side = 'short' if p['agent_side'] == 'long' else 'long'
        
        agent_result = simulate_trade_outcome(
            kline_df=kline_df,
            entry_time=p['entry_time'],
            entry_price=p['entry_price'],
            side=p['agent_side'],
            tp_distance_pct=p['tp_distance_pct'],
            sl_distance_pct=p['sl_distance_pct'],
        )
        
        opposite_result = simulate_trade_outcome(
            kline_df=kline_df,
            entry_time=p['entry_time'],
            entry_price=p['entry_price'],
            side=opposite_side,
            tp_distance_pct=p['tp_distance_pct'],
            sl_distance_pct=p['sl_distance_pct'],
        )
        
        if agent_result['success'] and opposite_result['success']:
            if agent_result['is_win'] is not None and opposite_result['is_win'] is not None:
                total += 1
                if agent_result['is_win']:
                    agent_wins += 1
                if opposite_result['is_win']:
                    opposite_wins += 1
    
    print(f"  进度: {n}/{n} (100.0%)   ")
    
    agent_winrate = agent_wins / total * 100 if total > 0 else 0
    opposite_winrate = opposite_wins / total * 100 if total > 0 else 0
    
    return {
        'agent_winrate': agent_winrate,
        'opposite_winrate': opposite_winrate,
        'agent_wins': agent_wins,
        'opposite_wins': opposite_wins,
        'total': total,
        'difference': agent_winrate - opposite_winrate,
        'conclusion': 'agent_better' if agent_winrate > opposite_winrate else 
                     'opposite_better' if opposite_winrate > agent_winrate else 'equal',
    }


def print_section(title: str):
    print('\n' + '=' * 80)
    print(f'  {title}')
    print('=' * 80)


def main():
    print('=' * 80)
    print('  Alpha 验证测试 - Agent vs 随机基准')
    print('=' * 80)
    
    positions = load_positions(POSITIONS_FILE)
    print(f'\n加载交易记录: {len(positions)} 条')
    
    symbols = set(p.get('symbol', '') for p in positions if p.get('symbol'))
    print(f'交易对: {symbols}')
    
    symbol = 'DOGEUSDT'
    print(f'\n加载 {symbol} 1分钟K线数据...')
    kline_df = load_kline_data(symbol, '1m')
    
    if kline_df is None or len(kline_df) == 0:
        print("错误: 无法加载K线数据")
        return
    
    print(f'K线数据范围: {kline_df.index.min()} ~ {kline_df.index.max()}')
    print(f'K线数据量: {len(kline_df)} 根')
    
    symbol_positions = [p for p in positions if p.get('symbol') == symbol]
    print(f'\n{symbol} 交易数: {len(symbol_positions)}')
    
    print_section('测试1: Agent vs 随机基准胜率对比')
    print('\n运行随机基准测试...')
    print('  方法：对每笔交易同时模拟做多和做空，计算理论随机胜率')
    
    baseline_result = run_random_baseline_test(
        positions=symbol_positions,
        kline_df=kline_df,
    )
    
    print(f'\n--- 结果 ---')
    print(f'  Agent 胜率:     {baseline_result["agent_winrate"]:.2f}% ({baseline_result["agent_wins"]}/{baseline_result["agent_total"]})')
    print(f'  随机基准胜率:   {baseline_result["random_winrate_mean"]:.2f}% ± {baseline_result["random_winrate_std"]:.2f}%')
    print(f'  Alpha (差异):   {baseline_result["alpha"]:+.2f}%')
    
    print(f'\n--- 结论 ---')
    if abs(baseline_result['alpha']) < 3:
        print(f'  ❌ Alpha < 3%, Agent 没有显著的预测能力')
        print(f'     Agent 的表现与随机开仓没有统计学差异')
    elif baseline_result['alpha'] > 3:
        print(f'  ✅ Alpha > 3%, Agent 可能有一定的预测能力')
    else:
        print(f'  ⚠️ Alpha < -3%, Agent 的预测可能是反向指标！')
    
    print_section('测试2: 方向预测准确率测试')
    print('\n测试 Agent 预测方向的准确性 (不考虑止盈止损)...')
    
    direction_results = run_direction_accuracy_test(
        positions=symbol_positions,
        kline_df=kline_df,
        lookahead_minutes=[5, 15, 30, 60, 120, 240],
    )
    
    print(f'\n--- 结果 ---')
    print(f'  {"预测窗口":>12s} {"准确率":>10s} {"样本数":>10s} {"是否显著":>10s}')
    print(f'  {"-"*12} {"-"*10} {"-"*10} {"-"*10}')
    
    for lookahead, result in direction_results.items():
        significant = '✅' if result['is_significant'] else '❌'
        print(f'  {lookahead:>10d}分钟 {result["accuracy"]:>9.1f}% {result["total"]:>10d} {significant:>10s}')
    
    print(f'\n--- 结论 ---')
    significant_count = sum(1 for r in direction_results.values() if r['is_significant'])
    if significant_count == 0:
        print(f'  ❌ 所有时间窗口的方向预测准确率都接近 50%')
        print(f'     Agent 的方向预测能力等同于抛硬币')
    else:
        print(f'  ⚠️ 有 {significant_count} 个时间窗口显示显著差异，需要进一步分析')
    
    print_section('测试3: Agent方向 vs 反向对比')
    print('\n对比使用 Agent 方向 vs 使用反向的胜率...')
    
    opposite_result = run_same_direction_vs_opposite_test(
        positions=symbol_positions,
        kline_df=kline_df,
    )
    
    print(f'\n--- 结果 ---')
    print(f'  Agent方向胜率:  {opposite_result["agent_winrate"]:.2f}% ({opposite_result["agent_wins"]}/{opposite_result["total"]})')
    print(f'  反向胜率:       {opposite_result["opposite_winrate"]:.2f}% ({opposite_result["opposite_wins"]}/{opposite_result["total"]})')
    print(f'  差异:           {opposite_result["difference"]:+.2f}%')
    
    print(f'\n--- 结论 ---')
    if abs(opposite_result['difference']) < 3:
        print(f'  ❌ Agent方向与反向胜率差异 < 3%')
        print(f'     Agent 的方向选择没有预测价值')
    elif opposite_result['difference'] > 3:
        print(f'  ✅ Agent方向胜率更高 (+{opposite_result["difference"]:.1f}%)')
        print(f'     Agent 的方向选择有一定价值')
    else:
        print(f'  ⚠️ 反向胜率更高 ({-opposite_result["difference"]:.1f}%)')
        print(f'     Agent 可能是反向指标！')
    
    print_section('综合诊断')
    
    has_alpha = baseline_result['alpha'] > 3
    has_direction_skill = any(r['accuracy'] > 52 for r in direction_results.values())
    agent_better_than_opposite = opposite_result['difference'] > 3
    
    print(f'\n  测试项                      结果')
    print(f'  {"-"*25} {"-"*10}')
    print(f'  Alpha (vs随机)              {"✅ 有" if has_alpha else "❌ 无"}')
    print(f'  方向预测能力                {"✅ 有" if has_direction_skill else "❌ 无"}')
    print(f'  优于反向                    {"✅ 是" if agent_better_than_opposite else "❌ 否"}')
    
    if not has_alpha and not has_direction_skill and not agent_better_than_opposite:
        print(f'\n  ════════════════════════════════════════════════════')
        print(f'  ⚠️  最终结论: Agent 当前没有可测量的预测能力')
        print(f'  ════════════════════════════════════════════════════')
        print(f'\n  可能的原因:')
        print(f'    1. LLM 看 K 线图本身无法预测价格走势')
        print(f'    2. 技术分析在高效市场中没有 alpha')
        print(f'    3. Prompt 设计需要根本性改变')
        print(f'\n  建议行动:')
        print(f'    - 重新定义 Agent 角色（风险过滤 vs 方向预测）')
        print(f'    - 引入更多数据源（订单簿、资金费率等）')
        print(f'    - 或接受短线技术分析的局限性')
    else:
        print(f'\n  Agent 显示了一定的预测能力，可以进一步优化')
    
    print('\n' + '=' * 80)
    print('  测试完成')
    print('=' * 80)


if __name__ == '__main__':
    main()
