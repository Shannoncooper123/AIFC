"""旁路Agent状态管理"""
import json
import os
from typing import Dict, Any
from datetime import datetime, timezone

DEFAULT_STATE = {
    "next_wakeup_ts": None,  # UTC毫秒时间戳
    "last_run_ts": None,     # UTC毫秒时间戳
    "last_summary": "",
    "last_symbols": [],
    "last_details": "",
}


def load_state(state_path: str) -> Dict[str, Any]:
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    if not os.path.exists(state_path):
        return DEFAULT_STATE.copy()
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {**DEFAULT_STATE, **data}
    except Exception:
        return DEFAULT_STATE.copy()


def save_state(state_path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    tmp_path = state_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, state_path)


def utc_now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)