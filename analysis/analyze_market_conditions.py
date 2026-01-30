#!/usr/bin/env python3
"""
客观分析交易数据
目标：发现 agent 在什么市场条件下表现好/差
不预设任何结论，只呈现数据
"""

import json
from collections import defaultdict
from datetime import datetime, timedelta
import statistics
import urllib.request

BINANCE_API = "https://fapi.binance.com"

def load_positions(filepath: str):
    """加载仓位数据"""
    positions = []
    with open(filepath, 'r') as f:
        for line in f:
            if line.strip():
                data = json.loads(line)
                if data.get('type') == 'trade':
                    positions.append(data)
    return positions


def fetch_kline(symbol: str, interval: str, start_time: int, end_time: int):
    """获取K线数据"""
    url = f"{BINANCE_API}/fapi/v1/klines?symbol={symbol}&interval={interval}&startTime={start_time}&endTime={end_time}&limit=1000"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode())
            return data
    except Exception as e:
        print(f"获取K线失败: {e}")
        return []


def get_market_context(symbol: str, entry_time_str: str, lookback_bars: int = 20):
    """
    获取入场时刻的市场环境
    返回入场前 lookback_bars 根K线的特征
    """
    try:
        entry_dt = datetime.fromisoformat(entry_time_str.replace('Z', '+00:00'))
        entry_ts = int(entry_dt.timestamp() * 1000)
        
        start_ts = entry_ts - (lookback_bars + 5) * 15 * 60 * 1000
        
        klines = fetch_kline(symbol, "15m", start_ts, entry_ts)
        
        if len(klines) < 5:
            return None
        
        closes = [float(k[4]) for k in klines]
        highs = [float(k[2]) for k in klines]
        lows = [float(k[3]) for k in klines]
        volumes = [float(k[5]) for k in klines]
        
        price_change = (closes[-1] - closes[0]) / closes[0] * 100
        
        ranges = [(h - l) / l * 100 for h, l in zip(highs, lows)]
        avg_volatility = statistics.mean(ranges)
        
        trend_direction = "up" if closes[-1] > closes[-5] else "down"
        
        ma5 = statistics.mean(closes[-5:])
        ma20 = statistics.mean(closes[-20:]) if len(closes) >= 20 else statistics.mean(closes)
        
        price_vs_ma5 = (closes[-1] - ma5) / ma5 * 100
        price_vs_ma20 = (closes[-1] - ma20) / ma20 * 100
        
        ma_trend = "bullish" if ma5 > ma20 else "bearish"
        
        recent_high = max(highs[-10:])
        recent_low = min(lows[-10:])
        price_position = (closes[-1] - recent_low) / (recent_high - recent_low) * 100 if recent_high != recent_low else 50
        
        return {
            'price_change_pct': price_change,
            'avg_volatility': avg_volatility,
            'trend_direction': trend_direction,
            'price_vs_ma5': price_vs_ma5,
            'price_vs_ma20': price_vs_ma20,
            'ma_trend': ma_trend,
            'price_position': price_position,
            'last_close': closes[-1],
        }
    except Exception as e:
        return None


def categorize_value(value, bins):
    """将数值分类到区间"""
    for i, (low, high, label) in enumerate(bins):
        if low <= value < high:
            return label
    return bins[-1][2]


def analyze_by_market_period(positions):
    """按市场时间段分析"""
    print("=" * 80)
    print("按回测时间段分析")
    print("=" * 80)
    
    period_stats = defaultdict(lambda: {'count': 0, 'wins': 0, 'pnl': 0, 'trades': []})
    
    for p in positions:
        entry_time = p.get('entry_time', '')
        if entry_time:
            try:
                dt = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
                period_key = dt.strftime('%Y-%m-%d')
                
                period_stats[period_key]['count'] += 1
                if p.get('is_win', False):
                    period_stats[period_key]['wins'] += 1
                period_stats[period_key]['pnl'] += p.get('realized_pnl', 0)
                period_stats[period_key]['trades'].append(p)
            except:
                pass
    
    print(f"\n{'日期':<12} {'交易数':<8} {'胜率':<10} {'P&L':<12} {'多/空':<10}")
    print("-" * 60)
    
    for date in sorted(period_stats.keys()):
        data = period_stats[date]
        winrate = data['wins'] / data['count'] * 100 if data['count'] > 0 else 0
        
        longs = len([t for t in data['trades'] if t.get('side') == 'long'])
        shorts = len([t for t in data['trades'] if t.get('side') == 'short'])
        
        print(f"{date:<12} {data['count']:<8} {winrate:<9.1f}% ${data['pnl']:<11.2f} {longs}/{shorts}")


def analyze_by_entry_price_level(positions):
    """按入场价格水平分析"""
    print("\n" + "=" * 80)
    print("按入场价格水平分析")
    print("=" * 80)
    
    price_stats = defaultdict(lambda: {'count': 0, 'wins': 0, 'pnl': 0, 'long_wins': 0, 'long_count': 0, 'short_wins': 0, 'short_count': 0})
    
    for p in positions:
        entry_price = p.get('entry_price', 0)
        if entry_price:
            price_bucket = int(entry_price / 50) * 50
            
            price_stats[price_bucket]['count'] += 1
            if p.get('is_win', False):
                price_stats[price_bucket]['wins'] += 1
            price_stats[price_bucket]['pnl'] += p.get('realized_pnl', 0)
            
            if p.get('side') == 'long':
                price_stats[price_bucket]['long_count'] += 1
                if p.get('is_win', False):
                    price_stats[price_bucket]['long_wins'] += 1
            else:
                price_stats[price_bucket]['short_count'] += 1
                if p.get('is_win', False):
                    price_stats[price_bucket]['short_wins'] += 1
    
    print(f"\n{'价格区间':<12} {'交易数':<8} {'总胜率':<10} {'做多胜率':<12} {'做空胜率':<12} {'P&L':<12}")
    print("-" * 80)
    
    for price in sorted(price_stats.keys()):
        data = price_stats[price]
        if data['count'] >= 10:
            total_winrate = data['wins'] / data['count'] * 100
            long_winrate = data['long_wins'] / data['long_count'] * 100 if data['long_count'] > 0 else 0
            short_winrate = data['short_wins'] / data['short_count'] * 100 if data['short_count'] > 0 else 0
            
            print(f"${price}-{price+50:<5} {data['count']:<8} {total_winrate:<9.1f}% {long_winrate:<11.1f}% {short_winrate:<11.1f}% ${data['pnl']:<11.2f}")


def analyze_consecutive_trades(positions):
    """分析连续交易模式"""
    print("\n" + "=" * 80)
    print("连续交易模式分析")
    print("=" * 80)
    
    sorted_positions = sorted(positions, key=lambda x: x.get('entry_time', ''))
    
    win_streaks = []
    loss_streaks = []
    current_streak = 0
    current_type = None
    
    for p in sorted_positions:
        is_win = p.get('is_win', False)
        
        if current_type is None:
            current_type = is_win
            current_streak = 1
        elif is_win == current_type:
            current_streak += 1
        else:
            if current_type:
                win_streaks.append(current_streak)
            else:
                loss_streaks.append(current_streak)
            current_type = is_win
            current_streak = 1
    
    if current_type is not None:
        if current_type:
            win_streaks.append(current_streak)
        else:
            loss_streaks.append(current_streak)
    
    print(f"\n连胜统计:")
    if win_streaks:
        print(f"  最长连胜: {max(win_streaks)}")
        print(f"  平均连胜: {statistics.mean(win_streaks):.1f}")
        print(f"  连胜分布: {dict(sorted([(k, win_streaks.count(k)) for k in set(win_streaks)]))}")
    
    print(f"\n连败统计:")
    if loss_streaks:
        print(f"  最长连败: {max(loss_streaks)}")
        print(f"  平均连败: {statistics.mean(loss_streaks):.1f}")
        print(f"  连败分布: {dict(sorted([(k, loss_streaks.count(k)) for k in set(loss_streaks)]))}")


def analyze_after_win_loss(positions):
    """分析赢/输后的下一笔交易表现"""
    print("\n" + "=" * 80)
    print("赢/输后下一笔交易分析")
    print("=" * 80)
    
    sorted_positions = sorted(positions, key=lambda x: x.get('entry_time', ''))
    
    after_win = {'count': 0, 'wins': 0, 'pnl': 0}
    after_loss = {'count': 0, 'wins': 0, 'pnl': 0}
    
    for i in range(1, len(sorted_positions)):
        prev_win = sorted_positions[i-1].get('is_win', False)
        curr_win = sorted_positions[i].get('is_win', False)
        curr_pnl = sorted_positions[i].get('realized_pnl', 0)
        
        if prev_win:
            after_win['count'] += 1
            if curr_win:
                after_win['wins'] += 1
            after_win['pnl'] += curr_pnl
        else:
            after_loss['count'] += 1
            if curr_win:
                after_loss['wins'] += 1
            after_loss['pnl'] += curr_pnl
    
    print(f"\n赢后下一笔:")
    print(f"  交易数: {after_win['count']}")
    print(f"  胜率: {after_win['wins']/after_win['count']*100:.1f}%" if after_win['count'] > 0 else "  胜率: N/A")
    print(f"  P&L: ${after_win['pnl']:.2f}")
    
    print(f"\n输后下一笔:")
    print(f"  交易数: {after_loss['count']}")
    print(f"  胜率: {after_loss['wins']/after_loss['count']*100:.1f}%" if after_loss['count'] > 0 else "  胜率: N/A")
    print(f"  P&L: ${after_loss['pnl']:.2f}")


def analyze_by_order_wait_time(positions):
    """按挂单等待时间分析"""
    print("\n" + "=" * 80)
    print("按挂单等待时间分析")
    print("=" * 80)
    
    wait_stats = defaultdict(lambda: {'count': 0, 'wins': 0, 'pnl': 0})
    
    for p in positions:
        order_time = p.get('order_created_time', '')
        entry_time = p.get('entry_time', '')
        
        if order_time and entry_time:
            try:
                order_dt = datetime.fromisoformat(order_time.replace('Z', '+00:00'))
                entry_dt = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
                wait_hours = (entry_dt - order_dt).total_seconds() / 3600
                
                if wait_hours < 0:
                    continue
                
                if wait_hours < 0.5:
                    bucket = "0-0.5h"
                elif wait_hours < 1:
                    bucket = "0.5-1h"
                elif wait_hours < 2:
                    bucket = "1-2h"
                elif wait_hours < 4:
                    bucket = "2-4h"
                elif wait_hours < 8:
                    bucket = "4-8h"
                elif wait_hours < 24:
                    bucket = "8-24h"
                else:
                    bucket = "24h+"
                
                wait_stats[bucket]['count'] += 1
                if p.get('is_win', False):
                    wait_stats[bucket]['wins'] += 1
                wait_stats[bucket]['pnl'] += p.get('realized_pnl', 0)
            except:
                pass
    
    print(f"\n{'等待时间':<12} {'交易数':<10} {'胜率':<10} {'P&L':<12}")
    print("-" * 50)
    
    order = ["0-0.5h", "0.5-1h", "1-2h", "2-4h", "4-8h", "8-24h", "24h+"]
    for bucket in order:
        if bucket in wait_stats:
            data = wait_stats[bucket]
            winrate = data['wins'] / data['count'] * 100 if data['count'] > 0 else 0
            print(f"{bucket:<12} {data['count']:<10} {winrate:<9.1f}% ${data['pnl']:<11.2f}")


def analyze_by_trade_direction_and_price_movement(positions):
    """分析交易方向与价格走势的关系"""
    print("\n" + "=" * 80)
    print("交易方向与价格走势分析")
    print("=" * 80)
    
    patterns = defaultdict(lambda: {'count': 0, 'wins': 0, 'pnl': 0})
    
    for p in positions:
        entry_price = p.get('entry_price', 0)
        exit_price = p.get('exit_price', 0)
        side = p.get('side', '')
        is_win = p.get('is_win', False)
        pnl = p.get('realized_pnl', 0)
        
        if entry_price and exit_price:
            price_moved = "up" if exit_price > entry_price else "down"
            
            pattern = f"{side}_{price_moved}"
            patterns[pattern]['count'] += 1
            if is_win:
                patterns[pattern]['wins'] += 1
            patterns[pattern]['pnl'] += pnl
    
    print(f"\n{'模式':<20} {'交易数':<10} {'胜率':<10} {'P&L':<12}")
    print("-" * 55)
    
    for pattern in sorted(patterns.keys()):
        data = patterns[pattern]
        winrate = data['wins'] / data['count'] * 100 if data['count'] > 0 else 0
        print(f"{pattern:<20} {data['count']:<10} {winrate:<9.1f}% ${data['pnl']:<11.2f}")


def analyze_sl_tp_hit_distribution(positions):
    """分析止损止盈触发分布"""
    print("\n" + "=" * 80)
    print("止损止盈触发详细分析")
    print("=" * 80)
    
    exit_analysis = defaultdict(lambda: {'count': 0, 'total_pnl': 0, 'avg_holding': []})
    
    for p in positions:
        exit_type = p.get('exit_type', 'unknown')
        side = p.get('side', '')
        holding_bars = p.get('holding_bars', 0)
        pnl = p.get('realized_pnl', 0)
        
        key = f"{side}_{exit_type}"
        exit_analysis[key]['count'] += 1
        exit_analysis[key]['total_pnl'] += pnl
        exit_analysis[key]['avg_holding'].append(holding_bars)
    
    print(f"\n{'类型':<20} {'数量':<10} {'总P&L':<15} {'平均持仓bars':<15}")
    print("-" * 65)
    
    for key in sorted(exit_analysis.keys()):
        data = exit_analysis[key]
        avg_holding = statistics.mean(data['avg_holding']) if data['avg_holding'] else 0
        print(f"{key:<20} {data['count']:<10} ${data['total_pnl']:<14.2f} {avg_holding:<14.1f}")


def analyze_pnl_distribution(positions):
    """分析盈亏分布"""
    print("\n" + "=" * 80)
    print("盈亏金额分布")
    print("=" * 80)
    
    pnls = [p.get('realized_pnl', 0) for p in positions]
    
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]
    
    print(f"\n盈利交易分布:")
    if wins:
        print(f"  数量: {len(wins)}")
        print(f"  总额: ${sum(wins):.2f}")
        print(f"  平均: ${statistics.mean(wins):.2f}")
        print(f"  中位数: ${statistics.median(wins):.2f}")
        print(f"  最大: ${max(wins):.2f}")
        print(f"  最小: ${min(wins):.2f}")
        print(f"  标准差: ${statistics.stdev(wins):.2f}" if len(wins) > 1 else "")
    
    print(f"\n亏损交易分布:")
    if losses:
        print(f"  数量: {len(losses)}")
        print(f"  总额: ${sum(losses):.2f}")
        print(f"  平均: ${statistics.mean(losses):.2f}")
        print(f"  中位数: ${statistics.median(losses):.2f}")
        print(f"  最大亏损: ${min(losses):.2f}")
        print(f"  最小亏损: ${max(losses):.2f}")
        print(f"  标准差: ${statistics.stdev(losses):.2f}" if len(losses) > 1 else "")
    
    print(f"\n盈亏比例:")
    if wins and losses:
        print(f"  平均盈利/平均亏损: {abs(statistics.mean(wins)/statistics.mean(losses)):.2f}")
        print(f"  总盈利/总亏损: {abs(sum(wins)/sum(losses)):.2f}")


def analyze_by_margin_size(positions):
    """按保证金大小分析"""
    print("\n" + "=" * 80)
    print("按保证金大小分析")
    print("=" * 80)
    
    margin_stats = defaultdict(lambda: {'count': 0, 'wins': 0, 'pnl': 0})
    
    for p in positions:
        margin = p.get('margin_usdt', 0)
        
        if margin < 100:
            bucket = "<100"
        elif margin < 200:
            bucket = "100-200"
        elif margin < 300:
            bucket = "200-300"
        elif margin < 500:
            bucket = "300-500"
        else:
            bucket = "500+"
        
        margin_stats[bucket]['count'] += 1
        if p.get('is_win', False):
            margin_stats[bucket]['wins'] += 1
        margin_stats[bucket]['pnl'] += p.get('realized_pnl', 0)
    
    print(f"\n{'保证金':<12} {'交易数':<10} {'胜率':<10} {'P&L':<12}")
    print("-" * 50)
    
    order = ["<100", "100-200", "200-300", "300-500", "500+"]
    for bucket in order:
        if bucket in margin_stats:
            data = margin_stats[bucket]
            winrate = data['wins'] / data['count'] * 100 if data['count'] > 0 else 0
            print(f"${bucket:<11} {data['count']:<10} {winrate:<9.1f}% ${data['pnl']:<11.2f}")


def analyze_entry_vs_limit_price(positions):
    """分析入场价与挂单价的关系"""
    print("\n" + "=" * 80)
    print("入场价与挂单价关系分析")
    print("=" * 80)
    
    for p in positions[:20]:
        limit_price = p.get('limit_price', 0)
        entry_price = p.get('entry_price', 0)
        
        if limit_price and entry_price:
            diff = (entry_price - limit_price) / limit_price * 100
            print(f"挂单: ${limit_price:.2f}, 入场: ${entry_price:.2f}, 差异: {diff:.4f}%")


def analyze_holding_time_vs_outcome(positions):
    """详细分析持仓时间与结果的关系"""
    print("\n" + "=" * 80)
    print("持仓时间与结果详细分析")
    print("=" * 80)
    
    holding_stats = defaultdict(lambda: {
        'count': 0, 'wins': 0, 'pnl': 0,
        'long_count': 0, 'long_wins': 0, 'long_pnl': 0,
        'short_count': 0, 'short_wins': 0, 'short_pnl': 0
    })
    
    for p in positions:
        bars = p.get('holding_bars', 0)
        side = p.get('side', '')
        is_win = p.get('is_win', False)
        pnl = p.get('realized_pnl', 0)
        
        if bars <= 1:
            bucket = "1"
        elif bars <= 2:
            bucket = "2"
        elif bars <= 3:
            bucket = "3"
        elif bars <= 5:
            bucket = "4-5"
        elif bars <= 10:
            bucket = "6-10"
        elif bars <= 20:
            bucket = "11-20"
        elif bars <= 50:
            bucket = "21-50"
        elif bars <= 100:
            bucket = "51-100"
        else:
            bucket = "100+"
        
        holding_stats[bucket]['count'] += 1
        if is_win:
            holding_stats[bucket]['wins'] += 1
        holding_stats[bucket]['pnl'] += pnl
        
        if side == 'long':
            holding_stats[bucket]['long_count'] += 1
            if is_win:
                holding_stats[bucket]['long_wins'] += 1
            holding_stats[bucket]['long_pnl'] += pnl
        else:
            holding_stats[bucket]['short_count'] += 1
            if is_win:
                holding_stats[bucket]['short_wins'] += 1
            holding_stats[bucket]['short_pnl'] += pnl
    
    print(f"\n{'持仓bars':<10} {'总数':<8} {'总胜率':<10} {'总P&L':<12} {'多胜率':<10} {'多P&L':<12} {'空胜率':<10} {'空P&L':<12}")
    print("-" * 100)
    
    order = ["1", "2", "3", "4-5", "6-10", "11-20", "21-50", "51-100", "100+"]
    for bucket in order:
        if bucket in holding_stats:
            data = holding_stats[bucket]
            total_wr = data['wins'] / data['count'] * 100 if data['count'] > 0 else 0
            long_wr = data['long_wins'] / data['long_count'] * 100 if data['long_count'] > 0 else 0
            short_wr = data['short_wins'] / data['short_count'] * 100 if data['short_count'] > 0 else 0
            
            print(f"{bucket:<10} {data['count']:<8} {total_wr:<9.1f}% ${data['pnl']:<11.2f} {long_wr:<9.1f}% ${data['long_pnl']:<11.2f} {short_wr:<9.1f}% ${data['short_pnl']:<11.2f}")


def main():
    filepath = "/Users/bytedance/Desktop/crypto_agentx/analysis/all_positions.jsonl"
    positions = load_positions(filepath)
    
    print(f"加载了 {len(positions)} 条交易记录")
    print(f"时间范围: {positions[0].get('entry_time', '')} ~ {positions[-1].get('entry_time', '')}")
    
    analyze_by_market_period(positions)
    analyze_by_entry_price_level(positions)
    analyze_holding_time_vs_outcome(positions)
    analyze_by_order_wait_time(positions)
    analyze_consecutive_trades(positions)
    analyze_after_win_loss(positions)
    analyze_by_trade_direction_and_price_movement(positions)
    analyze_sl_tp_hit_distribution(positions)
    analyze_pnl_distribution(positions)
    analyze_by_margin_size(positions)


if __name__ == "__main__":
    main()
