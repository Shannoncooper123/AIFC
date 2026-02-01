"""交易模拟状态持久化（精简版）"""
import json
import os
from typing import Any, Dict

from modules.agent.trade_simulator.utils.file_utils import (
    TaskType,
    WriteQueue,
    locked_append_jsonl,
)
from modules.constants import DEFAULT_LEVERAGE, DEFAULT_TAKER_FEE_RATE
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
    """加载持仓历史记录（JSONL格式）

    文件格式：每行一个JSON对象，每行是一条已平仓位记录
    """
    dir_name = os.path.dirname(path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    if not os.path.exists(path):
        return {"positions": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if not content:
            return {"positions": []}

        positions = []
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                if isinstance(record, dict) and "positions" not in record:
                    positions.append(record)
            except json.JSONDecodeError:
                logger.warning(f"load_position_history: 跳过无效行: {line[:50]}...")
                continue
        return {"positions": positions}
    except Exception as e:
        logger.error(f"load_position_history: 加载失败, path={path}, error={e}")
        return {"positions": []}


def append_position_history(path: str, record: Dict[str, Any]) -> None:
    """追加已平仓位到历史记录文件（JSONL格式）

    文件格式：每行一个JSON对象，每行是一条已平仓位记录
    """
    try:
        logger.info(f"append_position_history: 写入历史记录, symbol={record.get('symbol')}, id={record.get('id')}, path={path}")

        if not path:
            logger.warning("append_position_history: path为空，跳过写入")
            return

        dir_name = os.path.dirname(path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        locked_append_jsonl(path, record)
        logger.info(f"append_position_history: 成功追加记录, symbol={record.get('symbol')}")

    except Exception as e:
        logger.error(f"append_position_history: 写入失败, error={e}", exc_info=True)


class ConfigFacade:
    """配置访问门面类：简化配置项获取"""
    def __init__(self, config: Dict):
        self.config = config
        sim_cfg = config.get('agent', {}).get('simulator', {})
        self.ws_interval = sim_cfg.get('ws_interval', '1m')
        self.taker_fee_rate = float(sim_cfg.get('taker_fee_rate', DEFAULT_TAKER_FEE_RATE))
        self.max_leverage = int(sim_cfg.get('max_leverage', DEFAULT_LEVERAGE))
        self.trade_state_path = config.get('agent', {}).get('trade_state_path', 'modules/data/trade_state.json')
        self.position_history_path = config.get('agent', {}).get('position_history_path', 'modules/data/position_history.json')
