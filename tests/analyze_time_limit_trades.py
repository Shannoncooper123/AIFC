#!/usr/bin/env python3
"""
分析因时间限制平仓的仓位
使用真实K线数据判断如果继续持仓会触及TP还是SL
"""
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add parent directory to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Import Binance client
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


def fetch_klines(client: BinanceRestClient, symbol: str, start_time: datetime, end_time: datetime) -> List[List[Any]]:
    """获取 K 线数据"""
    start_ms = int(start_time.timestamp() * 1000)
    end_ms = int(end_time.timestamp() * 1000)
    return client.get_klines(symbol, '1m', limit=1500, start_time=start_ms, end_time=end_ms)


def simulate_outcome(side: str, close_price: float, tp: float, sl: float, klines: List[List[Any]]) -> Tuple[str, float, int]:
    """
    模拟如果继续持仓会发生什么
    
    Returns:
        (Outcome, PnL_per_unit, minutes_to_trigger)
        Outcome: 'TP', 'SL', 'HOLD'
    """
    for i, k in enumerate(klines):
        # k: [open_time, open, high, low, close, volume, ...]
        high = float(k[2])
        low = float(k[3])
        
        if side.lower() == 'long':
            # 对于多单：先检查止损，再检查止盈（同一根K线内）
            if low <= sl:
                pnl_per_unit = sl - close_price
                return 'SL', pnl_per_unit, i
            if high >= tp:
                pnl_per_unit = tp - close_price
                return 'TP', pnl_per_unit, i
        else:  # Short
            # 对于空单：先检查止损，再检查止盈
            if high >= sl:
                pnl_per_unit = close_price - sl
                return 'SL', pnl_per_unit, i
            if low <= tp:
                pnl_per_unit = close_price - tp
                return 'TP', pnl_per_unit, i
    
    # 如果一直没触发
    if klines:
        last_close = float(klines[-1][4])
        pnl = (last_close - close_price) if side.lower() == 'long' else (close_price - last_close)
        return 'HOLD', pnl, len(klines)
    
    return 'HOLD', 0.0, 0


def analyze_time_limit_positions(file_path: str):
    """分析因时间限制平仓的仓位"""
    
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    positions = data['positions']
    
    # 筛选因时间限制平仓的仓位
    time_limit_positions = [
        p for p in positions 
        if p.get('close_reason') == '时间限制'
    ]
    
    print("\n" + "=" * 120)
    print("⏰ 因时间限制平仓的仓位分析（基于真实K线数据）")
    print("=" * 120)
    print(f"\n总共有 {len(time_limit_positions)} 个仓位因时间限制而平仓\n")
    
    if not time_limit_positions:
        print("没有找到因时间限制平仓的仓位")
        return
    
    # 初始化 Binance 客户端
    print("正在连接 Binance API...")
    client = BinanceRestClient(get_config())
    
    # 统计数据
    actual_profit_count = 0
    actual_loss_count = 0
    actual_total_pnl = 0
    
    hypothetical_tp_count = 0
    hypothetical_sl_count = 0
    hypothetical_hold_count = 0
    hypothetical_total_pnl = 0
    
    results = []
    
    print(f"开始分析 {len(time_limit_positions)} 个仓位...\n")
    
    for idx, p in enumerate(time_limit_positions, 1):
        symbol = p['symbol']
        side = p['side']
        entry_price = p['entry_price']
        close_price = p['close_price']
        close_time = parse_ts(p['close_time'])
        tp_price = p.get('tp_price')
        sl_price = p.get('sl_price')
        realized_pnl = p['realized_pnl']
        notional = p['notional_usdt']
        
        if not close_time or not tp_price or not sl_price:
            print(f"[{idx}/{len(time_limit_positions)}] 跳过 {symbol}: 缺少必要数据")
            continue
        
        # 实际结果统计
        is_actual_profit = realized_pnl > 0
        if is_actual_profit:
            actual_profit_count += 1
        else:
            actual_loss_count += 1
        actual_total_pnl += realized_pnl
        
        # 获取平仓后的K线数据（未来48小时或到现在）
        lookahead_time = min(datetime.now(timezone.utc), close_time + timedelta(hours=48))
        
        try:
            klines = fetch_klines(client, symbol, close_time, lookahead_time)
            print(f"[{idx}/{len(time_limit_positions)}] {symbol} - 获取到 {len(klines)} 根K线")
        except Exception as e:
            print(f"[{idx}/{len(time_limit_positions)}] ❌ {symbol} 获取K线失败: {e}")
            continue
        
        # 模拟继续持仓的结果
        sim_outcome, sim_pnl_per_unit, minutes = simulate_outcome(side, close_price, tp_price, sl_price, klines)
        
        # 计算数量和总盈亏
        qty = notional / entry_price
        sim_total_pnl = sim_pnl_per_unit * qty
        
        # 统计
        if sim_outcome == 'TP':
            hypothetical_tp_count += 1
            hypothetical_total_pnl += sim_total_pnl
        elif sim_outcome == 'SL':
            hypothetical_sl_count += 1
            hypothetical_total_pnl += sim_total_pnl
        else:  # HOLD
            hypothetical_hold_count += 1
            hypothetical_total_pnl += sim_total_pnl
        
        results.append({
            'symbol': symbol,
            'side': side,
            'entry_price': entry_price,
            'close_price': close_price,
            'tp_price': tp_price,
            'sl_price': sl_price,
            'actual_pnl': realized_pnl,
            'sim_outcome': sim_outcome,
            'sim_pnl': sim_total_pnl,
            'minutes_to_trigger': minutes,
            'is_actual_profit': is_actual_profit
        })
    
    print(f"\n成功分析 {len(results)} 个仓位\n")
    
    # 打印汇总统计
    print("=" * 120)
    print("📊 对比分析")
    print("=" * 120)
    
    print(f"\n【实际结果 - 因时间限制平仓】")
    print(f"  盈利仓位: {actual_profit_count} ({actual_profit_count/len(results)*100:.1f}%)")
    print(f"  亏损仓位: {actual_loss_count} ({actual_loss_count/len(results)*100:.1f}%)")
    print(f"  总盈亏: {actual_total_pnl:.6f} USDT")
    print(f"  平均盈亏: {actual_total_pnl/len(results):.6f} USDT")
    
    print(f"\n【假设继续持仓 - 基于真实K线模拟】")
    print(f"  触及止盈(TP): {hypothetical_tp_count} ({hypothetical_tp_count/len(results)*100:.1f}%)")
    print(f"  触及止损(SL): {hypothetical_sl_count} ({hypothetical_sl_count/len(results)*100:.1f}%)")
    print(f"  仍在持有(HOLD): {hypothetical_hold_count} ({hypothetical_hold_count/len(results)*100:.1f}%)")
    print(f"  预计总盈亏: {hypothetical_total_pnl:.6f} USDT")
    print(f"  预计平均盈亏: {hypothetical_total_pnl/len(results):.6f} USDT")
    
    # 对比
    diff_pnl = hypothetical_total_pnl - actual_total_pnl
    print(f"\n【差异分析】")
    print(f"  盈亏差异: {diff_pnl:+.6f} USDT")
    
    if diff_pnl > 0:
        print(f"  ✅ 如果继续持仓，预计可多盈利 {diff_pnl:.2f} USDT")
        if actual_total_pnl != 0:
            print(f"     相对提升: {diff_pnl/abs(actual_total_pnl)*100:+.1f}%")
    elif diff_pnl < 0:
        print(f"  ❌ 如果继续持仓，预计会多亏损 {abs(diff_pnl):.2f} USDT")
        if actual_total_pnl != 0:
            print(f"     相对损失: {diff_pnl/abs(actual_total_pnl)*100:.1f}%")
    else:
        print(f"  ⚪ 结果相同")
    
    # 详细列表
    print("\n" + "=" * 140)
    print("📋 详细列表")
    print("=" * 140)
    print(f"\n{'交易对':<12} {'方向':<6} {'开仓价':<12} {'平仓价':<12} {'TP':<12} {'SL':<12} "
          f"{'实际PNL':<12} {'模拟结果':<10} {'模拟PNL':<12} {'触发时间(分钟)'}")
    print("─" * 140)
    
    for r in results:
        tp_str = f"{r['tp_price']:.6f}"
        sl_str = f"{r['sl_price']:.6f}"
        
        actual_indicator = "🟢" if r['is_actual_profit'] else "🔴"
        sim_indicator = "🟢" if r['sim_outcome'] == 'TP' else "🔴" if r['sim_outcome'] == 'SL' else "⚪"
        
        time_str = f"{r['minutes_to_trigger']}" if r['sim_outcome'] != 'HOLD' else "N/A"
        
        print(f"{r['symbol']:<12} {r['side']:<6} {r['entry_price']:<12.6f} {r['close_price']:<12.6f} "
              f"{tp_str:<12} {sl_str:<12} {actual_indicator}{r['actual_pnl']:>11.6f} "
              f"{sim_indicator}{r['sim_outcome']:<9} {r['sim_pnl']:<12.6f} {time_str}")
    
    # 转换矩阵
    print("\n" + "=" * 120)
    print("📊 结果转换分析")
    print("=" * 120)
    
    profit_to_tp = sum(1 for r in results if r['is_actual_profit'] and r['sim_outcome'] == 'TP')
    profit_to_sl = sum(1 for r in results if r['is_actual_profit'] and r['sim_outcome'] == 'SL')
    profit_to_hold = sum(1 for r in results if r['is_actual_profit'] and r['sim_outcome'] == 'HOLD')
    
    loss_to_tp = sum(1 for r in results if not r['is_actual_profit'] and r['sim_outcome'] == 'TP')
    loss_to_sl = sum(1 for r in results if not r['is_actual_profit'] and r['sim_outcome'] == 'SL')
    loss_to_hold = sum(1 for r in results if not r['is_actual_profit'] and r['sim_outcome'] == 'HOLD')
    
    print(f"\n实际盈利 → 模拟结果:")
    print(f"  → 触及TP: {profit_to_tp} ({profit_to_tp/len(results)*100:.1f}%) ✅ 应该继续持仓")
    print(f"  → 触及SL: {profit_to_sl} ({profit_to_sl/len(results)*100:.1f}%) ⚠️ 提前平仓避免反转")
    print(f"  → 仍持有: {profit_to_hold} ({profit_to_hold/len(results)*100:.1f}%)")
    
    print(f"\n实际亏损 → 模拟结果:")
    print(f"  → 触及TP: {loss_to_tp} ({loss_to_tp/len(results)*100:.1f}%) ❌ 过早平仓错过反转")
    print(f"  → 触及SL: {loss_to_sl} ({loss_to_sl/len(results)*100:.1f}%) ✅ 提前止损是对的")
    print(f"  → 仍持有: {loss_to_hold} ({loss_to_hold/len(results)*100:.1f}%)")
    
    # 平均触发时间
    tp_times = [r['minutes_to_trigger'] for r in results if r['sim_outcome'] == 'TP']
    sl_times = [r['minutes_to_trigger'] for r in results if r['sim_outcome'] == 'SL']
    
    if tp_times:
        avg_tp_time = sum(tp_times) / len(tp_times)
        print(f"\n触及止盈平均时间: {avg_tp_time:.0f} 分钟 ({avg_tp_time/60:.1f} 小时)")
    
    if sl_times:
        avg_sl_time = sum(sl_times) / len(sl_times)
        print(f"触及止损平均时间: {avg_sl_time:.0f} 分钟 ({avg_sl_time/60:.1f} 小时)")
    
    # 结论
    print("\n" + "=" * 120)
    print("💡 结论与建议")
    print("=" * 120)
    
    if hypothetical_tp_count > hypothetical_sl_count:
        tp_rate = hypothetical_tp_count / len(results) * 100
        print(f"\n✅ 如果继续持仓，有 {hypothetical_tp_count}/{len(results)} ({tp_rate:.1f}%) 的仓位会触及止盈")
        print(f"   说明当前4小时的时间限制可能过于保守")
        
        if avg_tp_time:
            suggested_hours = int(avg_tp_time / 60) + 2
            print(f"\n建议:")
            print(f"   - 平均 {avg_tp_time/60:.1f} 小时后触及止盈")
            print(f"   - 建议延长时间限制到 {suggested_hours} 小时")
            print(f"   - 在 config.yaml 中设置: time_limit.bars = {suggested_hours * 4}")
    else:
        sl_rate = hypothetical_sl_count / len(results) * 100
        print(f"\n⚠️ 如果继续持仓，有 {hypothetical_sl_count}/{len(results)} ({sl_rate:.1f}%) 的仓位会触及止损")
        print(f"   说明当前的时间限制起到了保护作用")
        print(f"\n建议: 保持当前4小时的时间限制设置")
    
    if diff_pnl > 10:
        print(f"\n💰 潜在收益: 延长时间限制可能带来 +{diff_pnl:.2f} USDT 的额外收益")
    elif diff_pnl < -10:
        print(f"\n🛡️ 风险防护: 当前时间限制避免了 {abs(diff_pnl):.2f} USDT 的额外损失")
    
    print("\n" + "=" * 120)


def main():
    """主函数"""
    file_path = sys.argv[1] if len(sys.argv) > 1 else '/home/sunfayao/monitor/logs/position_history.json'
    
    try:
        analyze_time_limit_positions(file_path)
    except FileNotFoundError:
        print(f"❌ 文件未找到: {file_path}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()


def analyze_time_limit_positions(file_path: str):
    """分析因时间限制平仓的仓位"""
    
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    positions = data['positions']
    
    # 筛选因时间限制平仓的仓位
    time_limit_positions = [
        p for p in positions 
        if p.get('close_reason') == '时间限制'
    ]
    
    print("\n" + "=" * 120)
    print("⏰ 因时间限制平仓的仓位分析")
    print("=" * 120)
    print(f"\n总共有 {len(time_limit_positions)} 个仓位因时间限制而平仓\n")
    
    if not time_limit_positions:
        print("没有找到因时间限制平仓的仓位")
        return
    
    # 统计实际结果
    actual_profit_count = 0
    actual_loss_count = 0
    actual_total_pnl = 0
    
    # 统计假设继续持仓的结果
    hypothetical_tp_count = 0
    hypothetical_sl_count = 0
    hypothetical_total_pnl = 0
    
    # 详细列表
    results = []
    
    for p in time_limit_positions:
        symbol = p['symbol']
        side = p['side']
        entry_price = p['entry_price']
        close_price = p['close_price']
        tp_price = p.get('tp_price')
        sl_price = p.get('sl_price')
        realized_pnl = p['realized_pnl']
        notional = p['notional_usdt']
        
        # 实际结果
        is_actual_profit = realized_pnl > 0
        if is_actual_profit:
            actual_profit_count += 1
        else:
            actual_loss_count += 1
        actual_total_pnl += realized_pnl
        
        # 分析假设继续持仓的情况
        # 需要判断：如果继续持仓，是先触及TP还是SL
        hypothetical_result = None
        hypothetical_pnl = None
        
        if tp_price and sl_price:
            # 对于多头
            if side == 'long':
                # 计算到TP和SL的距离
                distance_to_tp = tp_price - close_price
                distance_to_sl = close_price - sl_price
                
                # 简化假设：根据当前价格相对于entry的位置，以及TP/SL距离判断
                # 如果当前价格已经在朝TP方向移动，假设更可能触及TP
                if close_price >= entry_price:
                    # 价格在成本之上，更可能触及TP
                    hypothetical_result = 'TP'
                    hypothetical_pnl = (notional / entry_price) * (tp_price - entry_price)
                else:
                    # 价格在成本之下，更可能触及SL
                    hypothetical_result = 'SL'
                    hypothetical_pnl = (notional / entry_price) * (sl_price - entry_price)
            
            # 对于空头
            else:  # short
                if close_price <= entry_price:
                    # 价格在成本之下，更可能触及TP
                    hypothetical_result = 'TP'
                    hypothetical_pnl = (notional / entry_price) * (entry_price - tp_price)
                else:
                    # 价格在成本之上，更可能触及SL
                    hypothetical_result = 'SL'
                    hypothetical_pnl = (notional / entry_price) * (entry_price - sl_price)
        
        if hypothetical_result == 'TP':
            hypothetical_tp_count += 1
            hypothetical_total_pnl += hypothetical_pnl
        elif hypothetical_result == 'SL':
            hypothetical_sl_count += 1
            hypothetical_total_pnl += hypothetical_pnl
        
        results.append({
            'symbol': symbol,
            'side': side,
            'entry_price': entry_price,
            'close_price': close_price,
            'tp_price': tp_price,
            'sl_price': sl_price,
            'actual_pnl': realized_pnl,
            'hypothetical_result': hypothetical_result,
            'hypothetical_pnl': hypothetical_pnl,
            'price_vs_entry': 'above' if (side == 'long' and close_price >= entry_price) or (side == 'short' and close_price <= entry_price) else 'below'
        })
    
    # 打印汇总统计
    print("─" * 120)
    print("📊 实际结果（因时间限制平仓）")
    print("─" * 120)
    print(f"盈利仓位: {actual_profit_count} ({actual_profit_count/len(time_limit_positions)*100:.1f}%)")
    print(f"亏损仓位: {actual_loss_count} ({actual_loss_count/len(time_limit_positions)*100:.1f}%)")
    print(f"总盈亏: {actual_total_pnl:.6f} USDT")
    print(f"平均盈亏: {actual_total_pnl/len(time_limit_positions):.6f} USDT")
    
    print("\n" + "─" * 120)
    print("🔮 假设继续持仓（直到触及TP或SL）")
    print("─" * 120)
    print(f"触及止盈(TP): {hypothetical_tp_count} ({hypothetical_tp_count/len(time_limit_positions)*100:.1f}%)")
    print(f"触及止损(SL): {hypothetical_sl_count} ({hypothetical_sl_count/len(time_limit_positions)*100:.1f}%)")
    print(f"预计总盈亏: {hypothetical_total_pnl:.6f} USDT")
    print(f"预计平均盈亏: {hypothetical_total_pnl/len(time_limit_positions):.6f} USDT")
    
    # 对比
    print("\n" + "─" * 120)
    print("📈 对比分析")
    print("─" * 120)
    diff_pnl = hypothetical_total_pnl - actual_total_pnl
    print(f"盈亏差异: {diff_pnl:+.6f} USDT")
    
    if diff_pnl > 0:
        print(f"✅ 如果继续持仓，预计可多盈利 {diff_pnl:.2f} USDT (+{diff_pnl/abs(actual_total_pnl)*100:.1f}%)")
    elif diff_pnl < 0:
        print(f"❌ 如果继续持仓，预计会多亏损 {abs(diff_pnl):.2f} USDT ({diff_pnl/abs(actual_total_pnl)*100:.1f}%)")
    else:
        print(f"⚪ 结果相同")
    
    # 详细列表
    print("\n" + "=" * 120)
    print("📋 详细列表")
    print("=" * 120)
    print(f"\n{'交易对':<12} {'方向':<6} {'开仓价':<12} {'平仓价':<12} {'TP':<12} {'SL':<12} "
          f"{'实际PNL':<12} {'假设结果':<10} {'假设PNL':<12}")
    print("─" * 120)
    
    for r in results:
        tp_str = f"{r['tp_price']:.6f}" if r['tp_price'] else "N/A"
        sl_str = f"{r['sl_price']:.6f}" if r['sl_price'] else "N/A"
        hyp_result = r['hypothetical_result'] or "N/A"
        hyp_pnl = f"{r['hypothetical_pnl']:.6f}" if r['hypothetical_pnl'] is not None else "N/A"
        
        actual_indicator = "🟢" if r['actual_pnl'] > 0 else "🔴"
        hyp_indicator = "🟢" if r['hypothetical_result'] == 'TP' else "🔴" if r['hypothetical_result'] == 'SL' else "⚪"
        
        print(f"{r['symbol']:<12} {r['side']:<6} {r['entry_price']:<12.6f} {r['close_price']:<12.6f} "
              f"{tp_str:<12} {sl_str:<12} {actual_indicator}{r['actual_pnl']:>11.6f} "
              f"{hyp_indicator}{hyp_result:<9} {hyp_pnl:<12}")
    
    # 分类统计
    print("\n" + "=" * 120)
    print("📊 分类统计")
    print("=" * 120)
    
    # 价格位置分类
    above_entry_count = sum(1 for r in results if r['price_vs_entry'] == 'above')
    below_entry_count = sum(1 for r in results if r['price_vs_entry'] == 'below')
    
    print(f"\n价格相对成本位置:")
    print(f"  高于成本: {above_entry_count} ({above_entry_count/len(results)*100:.1f}%)")
    print(f"  低于成本: {below_entry_count} ({below_entry_count/len(results)*100:.1f}%)")
    
    # 实际盈亏 vs 假设结果对比
    actual_profit_would_tp = sum(1 for r in results if r['actual_pnl'] > 0 and r['hypothetical_result'] == 'TP')
    actual_profit_would_sl = sum(1 for r in results if r['actual_pnl'] > 0 and r['hypothetical_result'] == 'SL')
    actual_loss_would_tp = sum(1 for r in results if r['actual_pnl'] < 0 and r['hypothetical_result'] == 'TP')
    actual_loss_would_sl = sum(1 for r in results if r['actual_pnl'] < 0 and r['hypothetical_result'] == 'SL')
    
    print(f"\n结果转换矩阵:")
    print(f"  实际盈利 → 假设触及TP: {actual_profit_would_tp}")
    print(f"  实际盈利 → 假设触及SL: {actual_profit_would_sl}")
    print(f"  实际亏损 → 假设触及TP: {actual_loss_would_tp}")
    print(f"  实际亏损 → 假设触及SL: {actual_loss_would_sl}")
    
    print("\n" + "=" * 120)
    print("💡 结论")
    print("=" * 120)
    
    if hypothetical_tp_count > hypothetical_sl_count:
        print(f"\n如果继续持仓，有 {hypothetical_tp_count}/{len(results)} 的仓位会触及止盈")
        print(f"说明时间限制可能过早平仓，导致错过了潜在盈利")
    else:
        print(f"\n如果继续持仓，有 {hypothetical_sl_count}/{len(results)} 的仓位会触及止损")
        print(f"说明时间限制起到了保护作用，避免了更大的亏损")
    
    if diff_pnl > 0:
        print(f"\n建议: 考虑适当延长持仓时间限制，可能获得 {diff_pnl:.2f} USDT 的额外收益")
    elif diff_pnl < 0:
        print(f"\n建议: 当前的时间限制设置较为合理，避免了 {abs(diff_pnl):.2f} USDT 的额外损失")
    
    print("\n" + "=" * 120)


def main():
    """主函数"""
    import sys
    
    file_path = sys.argv[1] if len(sys.argv) > 1 else '/home/sunfayao/monitor/logs/position_history.json'
    
    try:
        analyze_time_limit_positions(file_path)
    except FileNotFoundError:
        print(f"❌ 文件未找到: {file_path}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
