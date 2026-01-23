"""读取聚合告警JSONL：支持按时间窗口过滤与读取最新一条记录"""
import json
from typing import List, Dict, Optional

def read_latest_aggregate(jsonl_path: str) -> Optional[Dict]:
    """读取最新一条聚合告警记录。
    实现策略：顺序读取 JSONL，保留最后一个 type=="aggregate" 的对象并返回；如文件不存在或没有有效记录则返回 None。
    """
    latest: Optional[Dict] = None
    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if obj.get("type") != "aggregate":
                    continue
                latest = obj
    except FileNotFoundError:
        return None
    return latest