#!/usr/bin/env python3

import argparse
import csv
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

POSITION_HISTORY_PATH = ROOT / 'logs' / 'position_history.json'
OUTPUT_DIR = ROOT / 'analysis' / 'output' / 'kline_manual'

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
        if len(res) > 20000:
            break
    return res


def write_json(out_path: Path, payload: Dict[str, Any]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def write_csv(out_path: Path, klines: List[List[Any]]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['open_time_ms','open','high','low','close','volume','close_time_ms'])
        for k in klines:
            w.writerow([k[0], k[1], k[2], k[3], k[4], k[5], k[6]])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--interval', default='1m')
    parser.add_argument('--pre_hours', type=int, default=6)
    parser.add_argument('--post_hours', type=int, default=48)
    parser.add_argument('--only_stop_loss', action='store_true')
    parser.add_argument('--symbol', default='')
    args = parser.parse_args()

    positions = load_positions()
    if not positions:
        print('no positions')
        return
    if args.only_stop_loss:
        positions = [p for p in positions if p.get('close_reason') == '止损']
    if args.symbol:
        positions = [p for p in positions if p.get('symbol') == args.symbol]
    client = BinanceRestClient(get_config())
    now = datetime.now(timezone.utc)
    index: List[Dict[str, Any]] = []
    for p in positions:
        open_dt = parse_ts(p.get('open_time'))
        close_dt = parse_ts(p.get('close_time'))
        if not open_dt or not close_dt:
            continue
        start_dt = open_dt - timedelta(hours=args.pre_hours)
        end_dt = min(now, close_dt + timedelta(hours=args.post_hours))
        kl = fetch_klines_range(client, p['symbol'], start_dt, end_dt, args.interval)
        base = f"{p['symbol']}_{p.get('id','unknown')}"
        json_path = OUTPUT_DIR / f"{base}.json"
        csv_path = OUTPUT_DIR / f"{base}.csv"
        payload = {
            'meta': {
                'id': p.get('id'),
                'symbol': p.get('symbol'),
                'side': p.get('side'),
                'entry_price': p.get('entry_price'),
                'close_price': p.get('close_price'),
                'tp_price': p.get('tp_price'),
                'sl_price': p.get('sl_price'),
                'open_time': p.get('open_time'),
                'close_time': p.get('close_time'),
                'close_reason': p.get('close_reason'),
                'realized_pnl': p.get('realized_pnl'),
                'interval': args.interval,
                'pre_hours': args.pre_hours,
                'post_hours': args.post_hours,
                'window_start': start_dt.isoformat(),
                'window_end': end_dt.isoformat(),
            },
            'klines': [[k[0], k[1], k[2], k[3], k[4], k[5], k[6]] for k in kl],
        }
        write_json(json_path, payload)
        write_csv(csv_path, kl)
        index.append({'symbol': p['symbol'], 'id': p.get('id'), 'json': str(json_path), 'csv': str(csv_path)})
    write_json(OUTPUT_DIR / 'index.json', {'items': index})
    print(f'saved -> {OUTPUT_DIR}')


if __name__ == '__main__':
    main()
