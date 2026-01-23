#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
分析 Agent 主动平仓决策的有效性
比较 Agent 主动平仓 vs 如果不平仓而是等待原始 TP/SL 触发的结果
"""

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Paths
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

POSITION_HISTORY_PATH = ROOT / 'logs' / 'position_history.json'

# Config for Binance Client
try:
    from config.settings import get_config
except Exception:
    def get_config():
        return {
            'api': {
                'base_url': 'https://fapi.binance.com',
                'timeout': 10,
                'retry_times': 2,
            },
            'env': {},
        }

from monitor_module.clients.binance_rest import BinanceRestClient


def parse_ts(s: Optional[str]) -> Optional[datetime]:
    """解析时间戳为 datetime 对象"""
    if not s:
        return None
    try:
        if s.endswith('Z'):
            s = s.replace('Z', '+00:00')
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass
    return None


def load_positions() -> List[Dict[str, Any]]:
    """加载持仓历史记录"""
    try:
        with open(POSITION_HISTORY_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('positions', [])
    except Exception as e:
        print(f"Error loading positions: {e}")
        return []


def fetch_klines(client: BinanceRestClient, symbol: str, start_time: datetime, end_time: datetime) -> List[List[Any]]:
    """获取 K 线数据"""
    start_ms = int(start_time.timestamp() * 1000)
    end_ms = int(end_time.timestamp() * 1000)
    return client.get_klines(symbol, '1m', limit=1500, start_time=start_ms, end_time=end_ms)


def simulate_outcome(side: str, close_price: float, tp: float, sl: float, klines: List[List[Any]]) -> Tuple[str, float]:
    """
    模拟如果不主动平仓，从平仓点开始继续持有会发生什么
    
    Returns:
        (Outcome, PnL_per_unit)
        Outcome: 'TP', 'SL', 'HOLD'
    """
    for k in klines:
        # k: [open_time, open, high, low, close, volume, ...]
        high = float(k[2])
        low = float(k[3])
        
        if side.lower() == 'long':
            # 对于多单：价格跌破止损 或 涨到止盈
            if low <= sl:
                return 'SL', sl - close_price  # 从平仓价到止损的盈亏
            if high >= tp:
                return 'TP', tp - close_price  # 从平仓价到止盈的盈亏
        else:  # Short
            # 对于空单：价格涨破止损 或 跌到止盈
            if high >= sl:
                return 'SL', close_price - sl  # 从平仓价到止损的盈亏
            if low <= tp:
                return 'TP', close_price - tp  # 从平仓价到止盈的盈亏
    
    # 如果一直没触发，返回持有状态
    if klines:
        last_close = float(klines[-1][4])
        pnl = (last_close - close_price) if side.lower() == 'long' else (close_price - last_close)
        return 'HOLD', pnl
    
    return 'HOLD', 0.0


def main():
    print("=" * 80)
    print("分析 Agent 主动平仓决策的有效性")
    print("=" * 80)
    print()
    
    # 加载所有持仓
    positions = load_positions()
    
    # 筛选出 Agent 主动平仓的记录
    agent_closes = [p for p in positions if p.get('close_reason') == 'agent']
    
    print(f"总持仓记录: {len(positions)}")
    print(f"Agent 主动平仓: {len(agent_closes)}")
    print()
    
    if not agent_closes:
        print("没有找到 Agent 主动平仓的记录。")
        return
    
    client = BinanceRestClient(get_config())
    results = []
    
    print("开始分析每个主动平仓决策...\n")
    
    for pos in agent_closes:
        symbol = pos['symbol']
        side = pos['side']
        entry_price = float(pos['entry_price'])
        close_price = float(pos['close_price'])
        close_time = parse_ts(pos['close_time'])
        tp_price = float(pos['tp_price'])
        sl_price = float(pos['sl_price'])
        qty = float(pos.get('notional_usdt', 0)) / entry_price if entry_price else 0
        actual_pnl = float(pos['realized_pnl'])
        
        # 计算从入场到平仓的盈亏（每单位）
        pnl_at_close = (close_price - entry_price) if side.lower() == 'long' else (entry_price - close_price)
        
        if not close_time:
            print(f"跳过 {symbol}: 无法解析平仓时间")
            continue
        
        # 获取平仓后的 K 线数据（未来 48 小时或到现在）
        lookahead_time = min(datetime.now(timezone.utc), close_time + timedelta(hours=48))
        
        try:
            klines = fetch_klines(client, symbol, close_time, lookahead_time)
        except Exception as e:
            print(f"错误：获取 {symbol} K线失败: {e}")
            continue
        
        # 模拟如果不平仓会发生什么
        sim_outcome, sim_pnl_per_unit = simulate_outcome(side, close_price, tp_price, sl_price, klines)
        
        # 总盈亏对比
        sim_total_pnl = sim_pnl_per_unit * qty
        
        # 判断 Agent 决策是否正确
        # 如果模拟结果是止损，且 sim_pnl < 0，说明 Agent 平仓避免了更大亏损
        # 如果模拟结果是止盈，Agent 平仓就错过了盈利机会
        agent_decision_quality = "未知"
        
        if sim_outcome == 'SL':
            # 如果后续会触发止损
            if sim_pnl_per_unit < 0:
                # Agent 提前平仓，避免了进一步亏损
                agent_decision_quality = "✅ 止损防护（避免更大亏损）"
            else:
                # 理论上不应该发生（止损应该是负盈亏）
                agent_decision_quality = "⚠️ 异常情况"
        elif sim_outcome == 'TP':
            # 如果后续会触发止盈
            if sim_pnl_per_unit > 0:
                # Agent 过早平仓，错过了盈利机会
                agent_decision_quality = "❌ 过早平仓（错过止盈）"
            else:
                agent_decision_quality = "⚠️ 异常情况"
        else:  # HOLD
            # 后续既没止损也没止盈
            if abs(sim_pnl_per_unit) < abs(pnl_at_close) * 0.1:
                agent_decision_quality = "➡️ 中性（价格横盘）"
            elif sim_pnl_per_unit > 0:
                agent_decision_quality = "⚠️ 可能过早（后续上涨）"
            else:
                agent_decision_quality = "⚠️ 可能过早（后续下跌）"
        
        results.append({
            'symbol': symbol,
            'side': side,
            'entry': entry_price,
            'close': close_price,
            'tp': tp_price,
            'sl': sl_price,
            'actual_pnl': actual_pnl,
            'sim_outcome': sim_outcome,
            'sim_pnl': sim_total_pnl,
            'quality': agent_decision_quality,
        })
    
    # 打印结果表格
    print("=" * 120)
    print(f"{'Symbol':<12} {'Side':<6} {'Entry':<10} {'Close':<10} {'TP':<10} {'SL':<10} {'Actual PnL':<12} {'Would Be':<8} {'Decision Quality'}")
    print("-" * 120)
    
    prevented_loss = 0
    missed_profit = 0
    neutral = 0
    uncertain = 0
    
    for r in results:
        print(f"{r['symbol']:<12} {r['side']:<6} {r['entry']:<10.4f} {r['close']:<10.4f} {r['tp']:<10.4f} "
              f"{r['sl']:<10.4f} {r['actual_pnl']:<12.2f} {r['sim_outcome']:<8} {r['quality']}")
        
        if '止损防护' in r['quality']:
            prevented_loss += 1
        elif '过早平仓' in r['quality']:
            missed_profit += 1
        elif '中性' in r['quality']:
            neutral += 1
        else:
            uncertain += 1
    
    print("-" * 120)
    print(f"\n总结：")
    print(f"  ✅ 成功止损防护（避免更大亏损）: {prevented_loss} 次")
    print(f"  ❌ 过早平仓（错过止盈机会）: {missed_profit} 次")
    print(f"  ➡️ 中性决策: {neutral} 次")
    print(f"  ⚠️ 不确定/其他: {uncertain} 次")
    print()
    
    if prevented_loss + missed_profit > 0:
        success_rate = prevented_loss / (prevented_loss + missed_profit) * 100
        print(f"Agent 主动平仓成功率: {success_rate:.1f}% ({prevented_loss}/{prevented_loss + missed_profit})")
    
    print("\n" + "=" * 120)


if __name__ == '__main__':
    main()
