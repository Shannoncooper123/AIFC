"""交易模拟状态持久化（精简版）"""
import json
import os
from typing import Dict, Any

from modules.agent.trade_simulator.utils.file_utils import WriteQueue, TaskType, locked_append_jsonl, locked_write_jsonl
from modules.monitor.utils.logger import get_logger

logger = get_logger('agent.trade_simulator.storage')

# 获取写入队列单例
_write_queue = WriteQueue.get_instance()


def load_state(path: str) -> Dict[str, Any]:
    """加载状态文件"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        return {"account": {}, "positions": [], "trades": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"account": {}, "positions": [], "trades": []}


def save_state(path: str, state: Dict[str, Any]) -> None:
    """保存状态文件（并发安全，异步非阻塞）
    
    使用写入队列异步写入，此函数立即返回，不阻塞主线程。
    """
    _write_queue.enqueue(TaskType.STATE, path, state)


def load_position_history(path: str) -> Dict[str, Any]:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        return {"positions": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if not content:
            return {"positions": []}
        if content[0] == "{":
            return json.loads(content) or {"positions": []}
        positions = []
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                positions.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return {"positions": positions}
    except Exception:
        return {"positions": []}


def append_position_history(path: str, record: Dict[str, Any]) -> None:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                first_char = f.read(1)
            if first_char == "{":
                history = load_position_history(path)
                positions = history.get("positions", [])
                positions.append(record)
                locked_write_jsonl(path, positions)
                return
        locked_append_jsonl(path, record)
    except Exception:
        history = load_position_history(path)
        if "positions" not in history:
            history["positions"] = []
        history["positions"].append(record)
        _write_queue.enqueue(TaskType.HISTORY, path, history)


class ConfigFacade:
    """配置访问门面类：简化配置项获取"""
    def __init__(self, config: Dict):
        self.config = config
        sim_cfg = config.get('agent', {}).get('simulator', {})
        self.ws_interval = sim_cfg.get('ws_interval', '1m')
        self.taker_fee_rate = float(sim_cfg.get('taker_fee_rate', 0.0005))
        self.max_leverage = int(sim_cfg.get('max_leverage', 10))
        self.trade_state_path = config.get('agent', {}).get('trade_state_path', '/home/sunfayao/monitor/agent/trade_state.json')
        self.position_history_path = config.get('agent', {}).get('position_history_path', '/home/sunfayao/monitor/logs/position_history.json')
