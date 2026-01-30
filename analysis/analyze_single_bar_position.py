#!/usr/bin/env python3
"""
分析持仓时间只有 1 bar 的异常情况

案例：
- Symbol: ETHUSDT
- Side: SHORT
- Entry: 3375.00 (限价单)
- Exit: 3390.00 (止损)
- 开仓时间: 2025-01-26 05:00
- 平仓时间: 2025-01-31 15:15
- 持仓时间: 1 bar
- 平仓原因: 止损触发

问题：开仓和平仓时间相差 5 天，但只有 1 bar？
"""

from datetime import datetime, timezone
import urllib.request
import json


def get_klines(symbol: str, interval: str, start_time: int, end_time: int, limit: int = 500):
    """直接调用 Binance API 获取 K 线数据"""
    base_url = "https://fapi.binance.com/fapi/v1/klines"
    params = f"symbol={symbol}&interval={interval}&startTime={start_time}&endTime={end_time}&limit={limit}"
    url = f"{base_url}?{params}"
    
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode())
            return data
    except Exception as e:
        print(f"获取 K 线失败: {e}")
        return []


def analyze_klines():
    """获取并分析该时间段的 K 线数据"""
    
    symbol = "ETHUSDT"
    
    # 限价单信息
    limit_price = 3375.00  # 挂单价
    sl_price = 3390.00     # 止损价
    tp_price = 3280.00     # 止盈价
    
    # 时间范围
    # 开仓时间: 2025-01-26 05:00
    # 平仓时间: 2025-01-31 15:15
    start_time = datetime(2025, 1, 25, 0, 0, tzinfo=timezone.utc)
    end_time = datetime(2025, 2, 1, 0, 0, tzinfo=timezone.utc)
    
    print("=" * 80)
    print(f"分析 {symbol} 异常持仓情况")
    print("=" * 80)
    print(f"限价单挂单价: ${limit_price}")
    print(f"止损价: ${sl_price}")
    print(f"止盈价: ${tp_price}")
    print(f"方向: SHORT (做空)")
    print()
    
    # 获取不同周期的 K 线
    intervals = ["15m", "1h", "4h"]
    
    for interval in intervals:
        print(f"\n{'='*40}")
        print(f"获取 {interval} K 线数据")
        print(f"{'='*40}")
        
        klines = get_klines(
            symbol=symbol,
            interval=interval,
            start_time=int(start_time.timestamp() * 1000),
            end_time=int(end_time.timestamp() * 1000),
            limit=500
        )
        
        if not klines:
            print(f"未获取到 {interval} K 线数据")
            continue
        
        print(f"获取到 {len(klines)} 根 K 线")
        print()
        
        # 分析关键价位
        print("关键价位分析:")
        print("-" * 60)
        
        # 找出价格触及限价单挂单价的 K 线
        entry_klines = []
        sl_triggered_klines = []
        
        for k in klines:
            # K 线数据格式: [open_time, open, high, low, close, volume, ...]
            open_time = datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc)
            high = float(k[2])
            low = float(k[3])
            
            # 检查是否触及挂单价（做空限价单：价格上涨到挂单价时成交）
            if high >= limit_price:
                entry_klines.append((open_time, k))
            
            # 检查是否触及止损价
            if high >= sl_price:
                sl_triggered_klines.append((open_time, k))
        
        print(f"\n价格触及挂单价 ${limit_price} 的 K 线数量: {len(entry_klines)}")
        if entry_klines:
            print("首次触及:")
            first_entry = entry_klines[0]
            k = first_entry[1]
            print(f"  时间: {first_entry[0]}")
            print(f"  OHLC: O={float(k[1]):.2f}, H={float(k[2]):.2f}, L={float(k[3]):.2f}, C={float(k[4]):.2f}")
        
        print(f"\n价格触及止损价 ${sl_price} 的 K 线数量: {len(sl_triggered_klines)}")
        if sl_triggered_klines:
            print("首次触及:")
            first_sl = sl_triggered_klines[0]
            k = first_sl[1]
            print(f"  时间: {first_sl[0]}")
            print(f"  OHLC: O={float(k[1]):.2f}, H={float(k[2]):.2f}, L={float(k[3]):.2f}, C={float(k[4]):.2f}")
        
        # 检查是否在同一根 K 线内同时触及入场价和止损价
        same_bar_entry_sl = []
        for open_time, k in entry_klines:
            high = float(k[2])
            if high >= sl_price:
                same_bar_entry_sl.append((open_time, k))
        
        if same_bar_entry_sl:
            print(f"\n⚠️ 警告：有 {len(same_bar_entry_sl)} 根 K 线同时触及入场价和止损价！")
            print("这可能是导致 '1 bar' 持仓的原因：")
            for open_time, k in same_bar_entry_sl[:5]:  # 只显示前5个
                print(f"  时间: {open_time}")
                print(f"  OHLC: O={float(k[1]):.2f}, H={float(k[2]):.2f}, L={float(k[3]):.2f}, C={float(k[4]):.2f}")
                print(f"  分析: 最高价 {float(k[2]):.2f} >= 止损价 {sl_price}")
                print()
        
        # 打印关键时间段的 K 线
        print("\n关键时间段 K 线详情 (2025-01-26 附近):")
        print("-" * 90)
        print(f"{'时间':<20} {'Open':>10} {'High':>10} {'Low':>10} {'Close':>10} {'备注':<25}")
        print("-" * 90)
        
        for k in klines:
            open_time = datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc)
            o, h, l, c = float(k[1]), float(k[2]), float(k[3]), float(k[4])
            
            # 只显示 1月25日到1月27日的数据
            if open_time >= datetime(2025, 1, 25, 0, 0, tzinfo=timezone.utc) and \
               open_time <= datetime(2025, 1, 27, 0, 0, tzinfo=timezone.utc):
                
                notes = []
                if h >= limit_price and l <= limit_price:
                    notes.append("穿越入场价")
                elif h >= limit_price:
                    notes.append("高于入场价")
                if h >= sl_price:
                    notes.append("触及止损")
                if l <= tp_price:
                    notes.append("触及止盈")
                
                note_str = ", ".join(notes) if notes else ""
                
                print(f"{open_time.strftime('%Y-%m-%d %H:%M'):<20} {o:>10.2f} {h:>10.2f} {l:>10.2f} {c:>10.2f} {note_str:<25}")
        
        # 特别关注 1月31日的数据
        print("\n关键时间段 K 线详情 (2025-01-31 附近 - 平仓时间):")
        print("-" * 90)
        print(f"{'时间':<20} {'Open':>10} {'High':>10} {'Low':>10} {'Close':>10} {'备注':<25}")
        print("-" * 90)
        
        for k in klines:
            open_time = datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc)
            o, h, l, c = float(k[1]), float(k[2]), float(k[3]), float(k[4])
            
            # 只显示 1月31日的数据
            if open_time >= datetime(2025, 1, 31, 0, 0, tzinfo=timezone.utc) and \
               open_time <= datetime(2025, 2, 1, 0, 0, tzinfo=timezone.utc):
                
                notes = []
                if h >= limit_price and l <= limit_price:
                    notes.append("穿越入场价")
                elif h >= limit_price:
                    notes.append("高于入场价")
                if h >= sl_price:
                    notes.append("触及止损")
                if l <= tp_price:
                    notes.append("触及止盈")
                
                note_str = ", ".join(notes) if notes else ""
                
                print(f"{open_time.strftime('%Y-%m-%d %H:%M'):<20} {o:>10.2f} {h:>10.2f} {l:>10.2f} {c:>10.2f} {note_str:<25}")


def analyze_position_record():
    """分析持仓记录的逻辑"""
    print("\n" + "=" * 80)
    print("持仓记录逻辑分析")
    print("=" * 80)
    
    print("""
根据截图信息：
- 开仓时间: 2025-01-26 05:00 (这是限价单创建时间还是成交时间？)
- 平仓时间: 2025-01-31 15:15
- 持仓时间: 1 bar

可能的情况：

1. 【限价单在同一根 K 线内成交并止损】
   - 如果某根 K 线的波动范围很大
   - 最高价 >= 止损价 3390
   - 同时价格也经过了入场价 3375
   - 那么在回测逻辑中，可能会在同一根 K 线内完成入场和止损
   - 这就导致了 "1 bar" 的持仓时间

2. 【开仓时间是限价单创建时间，而非成交时间】
   - 限价单在 2025-01-26 05:00 创建
   - 但实际成交可能在 2025-01-31 15:15 附近
   - 成交后立即触发止损

3. 【回测时间步进问题】
   - 回测可能是按某个时间间隔步进的
   - 如果步进间隔较大，可能会跳过一些 K 线
   - 导致持仓时间计算不准确

建议检查：
- 回测日志中该订单的具体成交时间
- all_positions.jsonl 中该仓位的详细记录
- 回测的时间步进间隔设置
""")


if __name__ == "__main__":
    analyze_klines()
    analyze_position_record()
