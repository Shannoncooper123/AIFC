import argparse
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from modules.backtest.providers.kline_storage import KlineStorage


def parse_time(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_trades(path: Path, max_lines: int):
    with path.open("r", encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            if max_lines and idx > max_lines:
                return
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def select_candidate(trade, max_minutes: int):
    if trade.get("type") != "trade":
        return False
    if trade.get("order_type") != "limit":
        return False
    if not trade.get("limit_price"):
        return False
    if not trade.get("order_created_time"):
        return False
    if not trade.get("entry_time"):
        return False
    start_time = parse_time(trade["order_created_time"])
    entry_time = parse_time(trade["entry_time"])
    delta_minutes = (entry_time - start_time).total_seconds() / 60
    return delta_minutes <= max_minutes


def touch_limit(side: str, limit_price: float, kline):
    if side == "long":
        return kline.low <= limit_price
    if side == "short":
        return kline.high >= limit_price
    return False


def format_kline(kline):
    ts = datetime.fromtimestamp(kline.timestamp / 1000, tz=timezone.utc).isoformat()
    return {
        "ts": ts,
        "open": kline.open,
        "high": kline.high,
        "low": kline.low,
        "close": kline.close,
        "volume": kline.volume,
    }


def build_sample(trade, limit_price: float, klines, touched: bool):
    return {
        "symbol": trade["symbol"],
        "side": trade["side"],
        "limit_price": limit_price,
        "order_created_time": trade["order_created_time"],
        "entry_time": trade["entry_time"],
        "touched": touched,
        "klines": [format_kline(k) for k in klines],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-candidates", type=int, default=2000)
    parser.add_argument("--max-lines", type=int, default=0)
    parser.add_argument("--sample-size", type=int, default=10)
    args = parser.parse_args()

    base_dir = Path("/home/sunfayao/AIFC2/AIFC/backend")
    cache_dir = base_dir / "modules/data/kline_cache"
    data_path = Path("/home/sunfayao/AIFC2/AIFC/analysis/all_positions.jsonl")
    max_minutes = 5
    storage = KlineStorage(str(cache_dir))

    stats = defaultdict(int)
    anomalies = []
    missing = []
    samples = []

    for trade in load_trades(data_path, args.max_lines):
        if not select_candidate(trade, max_minutes):
            continue
        stats["candidates"] += 1
        if args.max_candidates and stats["candidates"] > args.max_candidates:
            break
        symbol = trade["symbol"]
        side = trade["side"]
        limit_price = float(trade["limit_price"])
        start_time = parse_time(trade["order_created_time"])
        entry_time = parse_time(trade["entry_time"])
        if entry_time < start_time:
            stats["invalid_time"] += 1
            anomalies.append({
                "symbol": symbol,
                "order_created_time": trade["order_created_time"],
                "entry_time": trade["entry_time"],
                "limit_price": limit_price,
                "side": side,
                "reason": "entry_time_before_order_created_time",
            })
            continue
        end_time = entry_time + timedelta(minutes=1)
        klines = storage.load_klines(symbol, "1m", start_time, end_time)
        if not klines:
            stats["missing_1m"] += 1
            missing.append({
                "symbol": symbol,
                "order_created_time": trade["order_created_time"],
                "entry_time": trade["entry_time"],
            })
            continue
        matched = False
        for k in klines:
            if touch_limit(side, limit_price, k):
                matched = True
                break
        if matched:
            stats["matched"] += 1
            if len(samples) < args.sample_size:
                samples.append(build_sample(trade, limit_price, klines, True))
        else:
            stats["anomalies"] += 1
            anomalies.append({
                "symbol": symbol,
                "order_created_time": trade["order_created_time"],
                "entry_time": trade["entry_time"],
                "limit_price": limit_price,
                "side": side,
                "kline_count": len(klines),
            })
            if len(samples) < args.sample_size:
                samples.append(build_sample(trade, limit_price, klines, False))

    print("=== 限价单快速成交核验（<=5分钟） ===")
    print(f"max_candidates={args.max_candidates} max_lines={args.max_lines}")
    for k in ["candidates", "matched", "anomalies", "missing_1m", "invalid_time"]:
        if k in stats:
            print(f"{k}: {stats[k]}")
    if anomalies:
        print("\n=== 疑似异常样本（最多20条） ===")
        for item in anomalies[:20]:
            print(json.dumps(item, ensure_ascii=False))
    if samples:
        print("\n=== 成交样本（最多sample_size条） ===")
        for item in samples:
            print(json.dumps(item, ensure_ascii=False))
    if missing:
        print("\n=== 缺失1m数据样本（最多20条） ===")
        for item in missing[:20]:
            print(json.dumps(item, ensure_ascii=False))


if __name__ == "__main__":
    main()
