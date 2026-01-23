#!/usr/bin/env python3

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as patches
from matplotlib.collections import LineCollection

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

POSITION_HISTORY_PATH = ROOT / 'logs' / 'position_history.json'
OUT_DIR = ROOT / 'analysis' / 'output' / 'kline_plot'

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
    if not s:
        return None
    try:
        ss = s.replace('Z', '+00:00')
        dt = datetime.fromisoformat(ss)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def load_positions() -> List[Dict[str, Any]]:
    try:
        with open(POSITION_HISTORY_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('positions', [])
    except Exception:
        return []


def fetch_klines_range(client: BinanceRestClient, symbol: str, start_time: datetime, end_time: datetime, interval: str) -> List[List[Any]]:
    res: List[List[Any]] = []
    start_ms = int(start_time.timestamp() * 1000)
    end_ms = int(end_time.timestamp() * 1000)
    cur = start_ms
    while cur < end_ms:
        batch = client.get_klines(symbol, interval, limit=1500, start_time=cur, end_time=end_ms)
        if not batch:
            break
        res.extend(batch)
        last_close = int(batch[-1][6])
        next_cur = last_close + 1
        if next_cur <= cur:
            break
        cur = next_cur
        if len(res) > 40000:
            break
    return res


def plot_candles(ax, klines):
    if not klines:
        return

    dates = [datetime.fromtimestamp(k[0]/1000, tz=timezone.utc) for k in klines]
    opens = [float(k[1]) for k in klines]
    highs = [float(k[2]) for k in klines]
    lows = [float(k[3]) for k in klines]
    closes = [float(k[4]) for k in klines]

    mdates_num = mdates.date2num(dates)
    
    if len(dates) > 1:
        # Calculate median diff to avoid gaps/overlaps if data is irregular
        diffs = [mdates_num[i+1] - mdates_num[i] for i in range(len(dates)-1)]
        if diffs:
            width = sorted(diffs)[len(diffs)//2] * 0.8
        else:
            width = 0.001
    else:
        width = 0.001

    up_color = '#2ca02c'
    down_color = '#d62728'
    
    lines = []
    rects = []
    colors = []
    
    for i in range(len(dates)):
        t = mdates_num[i]
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]
        
        lines.append([(t, l), (t, h)])
        
        if c >= o:
            color = up_color
            height = max(c - o, 0.00000001)
            y = o
        else:
            color = down_color
            height = max(o - c, 0.00000001)
            y = c
            
        rect = patches.Rectangle((t - width/2, y), width, height, facecolor=color, edgecolor=color)
        ax.add_patch(rect)
        colors.append(color)

    lc = LineCollection(lines, colors='#555555', linewidths=1)
    ax.add_collection(lc)
    
    ax.xaxis_date()
    # Set limits manually to ensure everything is visible
    if mdates_num.size > 0:
        ax.set_xlim(min(mdates_num) - width*5, max(mdates_num) + width*5)
    
    all_prices = highs + lows
    if all_prices:
        p_min, p_max = min(all_prices), max(all_prices)
        pad = (p_max - p_min) * 0.05
        if pad == 0: pad = p_max * 0.01
        ax.set_ylim(p_min - pad, p_max + pad)


def render_matplotlib(pos: Dict[str, Any], panels: List[Tuple[str, List[List[Any]]]], out_path: Path):
    symbol = pos['symbol']
    pid = pos.get('id', 'unknown')
    side = pos.get('side', '').upper()
    close_reason = pos.get('close_reason', '')
    pnl = pos.get('realized_pnl', 0.0)
    
    entry_price = float(pos.get('entry_price')) if pos.get('entry_price') is not None else None
    close_price = float(pos.get('close_price')) if pos.get('close_price') is not None else None
    tp_price = float(pos.get('tp_price')) if pos.get('tp_price') is not None else None
    sl_price = float(pos.get('sl_price')) if pos.get('sl_price') is not None else None
    
    open_time = parse_ts(pos.get('open_time'))
    close_time = parse_ts(pos.get('close_time'))
    ops = pos.get('operation_history') or []

    n_panels = len(panels)
    if n_panels == 0:
        return

    fig, axes = plt.subplots(n_panels, 1, figsize=(16, 6 * n_panels), sharex=False)
    if n_panels == 1:
        axes = [axes]
    
    # Title with PnL color
    pnl_color = 'green' if pnl >= 0 else 'red'
    fig.suptitle(f"{symbol} | {side} | {close_reason} | PnL: {pnl:.4f}", fontsize=16, fontweight='bold', color=pnl_color)

    for i, (interval, klines) in enumerate(panels):
        ax = axes[i]
        ax.set_title(f"Interval: {interval}", loc='left', fontsize=12)
        ax.grid(True, which='both', linestyle='--', alpha=0.3)
        
        if not klines:
            ax.text(0.5, 0.5, "No Data", ha='center', va='center')
            continue

        plot_candles(ax, klines)
        
        # Plot Entry
        if entry_price and open_time:
            ot_num = mdates.date2num(open_time)
            ax.axhline(y=entry_price, color='gray', linestyle='--', alpha=0.6, label='Entry')
            ax.plot(ot_num, entry_price, marker='^' if side == 'LONG' else 'v', color='blue', markersize=10, label='Entry Point')
            ax.annotate('Entry', (ot_num, entry_price), xytext=(10, 10), textcoords='offset points', fontsize=9, color='blue', fontweight='bold')

        # Plot Close
        if close_price and close_time:
            ct_num = mdates.date2num(close_time)
            ax.plot(ct_num, close_price, marker='x', color='purple', markersize=10, markeredgewidth=2, label='Close Point')
            ax.annotate(f'Close\n{close_reason}', (ct_num, close_price), xytext=(10, -20), textcoords='offset points', fontsize=9, color='purple', fontweight='bold')

        # Plot TP/SL lines (Initial or Final)
        if tp_price:
            ax.axhline(y=tp_price, color='#2274A5', linestyle=':', alpha=0.8, label='TP')
            # Label at the end
            ax.text(ax.get_xlim()[1], tp_price, f' TP {tp_price}', va='center', ha='left', color='#2274A5', fontsize=8, fontweight='bold')

        if sl_price:
            ax.axhline(y=sl_price, color='#FF7F0E', linestyle=':', alpha=0.8, label='SL')
            ax.text(ax.get_xlim()[1], sl_price, f' SL {sl_price}', va='center', ha='left', color='#FF7F0E', fontsize=8, fontweight='bold')

        # Plot Operations (TP/SL updates)
        for op in ops:
            ts = parse_ts(op.get('timestamp'))
            if not ts:
                continue
            ts_num = mdates.date2num(ts)
            
            op_type = op.get('operation', '').lower()
            details = op.get('details', {})
            
            if op_type == 'update_tp_sl':
                new_tp = details.get('new_tp')
                new_sl = details.get('new_sl')
                
                if new_tp:
                    ax.plot(ts_num, float(new_tp), marker='d', color='#2274A5', markersize=6)
                if new_sl:
                    ax.plot(ts_num, float(new_sl), marker='d', color='#FF7F0E', markersize=6)

            elif op_type == 'add_position':
                 ax.plot(ts_num, entry_price, marker='+', color='black', markersize=8)
                 ax.annotate('Add', (ts_num, entry_price), xytext=(0, 15), textcoords='offset points', fontsize=8)

        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
        
    plt.tight_layout(rect=[0, 0.03, 1, 0.97])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, format='svg', bbox_inches='tight')
    plt.close(fig)


def generate_for_position(client: BinanceRestClient, pos: Dict[str, Any], intervals: List[str], pre_hours: int, post_hours: int, out_root: Path) -> Path:
    symbol = pos['symbol']
    pid = pos.get('id', 'unknown')
    open_dt = parse_ts(pos.get('open_time'))
    close_dt = parse_ts(pos.get('close_time'))
    
    if not open_dt:
        return Path()
        
    # If not closed, use current time
    if not close_dt:
        close_dt = datetime.now(timezone.utc)

    start_dt = open_dt - timedelta(hours=pre_hours)
    end_dt = min(datetime.now(timezone.utc), close_dt + timedelta(hours=post_hours))
    
    panels: List[Tuple[str, List[List[Any]]]] = []
    for itv in intervals:
        kl = fetch_klines_range(client, symbol, start_dt, end_dt, itv)
        panels.append((itv, kl))
        
    out_dir = out_root / f"{symbol}_{pid}"
    out_path = out_dir / f"{symbol}_{pid}.svg"
    render_matplotlib(pos, panels, out_path)
    return out_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--intervals', default='4h,1h,15m')
    parser.add_argument('--pre_hours', type=int, default=48)
    parser.add_argument('--post_hours', type=int, default=72)
    parser.add_argument('--only_stop_loss', action='store_true')
    parser.add_argument('--symbol', default='')
    args = parser.parse_args()
    
    intervals = [s.strip() for s in args.intervals.split(',') if s.strip()]
    positions = load_positions()
    
    if not positions:
        print('no positions')
        return
        
    if args.only_stop_loss:
        positions = [p for p in positions if p.get('close_reason') == '止损']
        
    if args.symbol:
        positions = [p for p in positions if p.get('symbol') == args.symbol]
        
    client = BinanceRestClient(get_config())
    index: List[Dict[str, Any]] = []
    
    for p in positions:
        try:
            path = generate_for_position(client, p, intervals, args.pre_hours, args.post_hours, OUT_DIR)
            if path and str(path):
                index.append({'symbol': p.get('symbol'), 'id': p.get('id'), 'file': str(path)})
                print(f"Generated {path}")
        except Exception as e:
            print(f"Error generating for {p.get('symbol')}: {e}")
            import traceback
            traceback.print_exc()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / 'index.json').write_text(json.dumps({'items': index}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"saved -> {OUT_DIR}")


if __name__ == '__main__':
    main()
