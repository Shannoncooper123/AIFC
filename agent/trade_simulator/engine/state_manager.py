"""状态持久化管理"""
from __future__ import annotations
import os
import json
from typing import Dict, List, Any
from datetime import datetime, timezone

from agent.trade_simulator.models import Position, Account
from agent.trade_simulator.storage import (
    load_state as load_trade_state, 
    save_state as save_trade_state,
    append_position_history,
    ConfigFacade
)
from agent.trade_simulator.utils.file_utils import locked_write_json
from config.settings import get_config
from monitor_module.utils.logger import get_logger

logger = get_logger('agent.trade_engine.state_manager')


class StateManager:
    """状态管理服务：负责状态恢复、持久化、操作日志"""
    def __init__(self, config: Dict, account: Account, positions: Dict[str, Position]):
        self.cfg = ConfigFacade(config)
        self.state_path = self.cfg.trade_state_path
        self.history_path = self.cfg.position_history_path
        self.account = account
        self.positions = positions
    
    def restore(self) -> None:
        """恢复账户与持仓状态"""
        try:
            st = load_trade_state(self.state_path)
            acc = st.get('account', {})
            if acc:
                self.account.balance = float(acc.get('balance', self.account.balance))
                self.account.equity = float(acc.get('equity', self.account.equity))
                self.account.realized_pnl = float(acc.get('realized_pnl', 0.0))
                self.account.unrealized_pnl = float(acc.get('unrealized_pnl', 0.0))
                self.account.reserved_margin_sum = float(acc.get('reserved_margin_sum', 0.0))
                self.account.positions_count = int(acc.get('positions_count', 0))
                self.account.total_fees = float(acc.get('total_fees', 0.0))  # 恢复累计手续费
            for p in st.get('positions', []):
                pos = Position(**p)
                self.positions[pos.symbol] = pos
            logger.info(f"状态恢复成功: balance={self.account.balance}, positions={len(self.positions)}")
        except Exception as e:
            logger.warning(f"状态恢复失败或不存在: {e}")
    
    def persist(self) -> None:
        """持久化当前状态（异步非阻塞）"""
        st = {
            'account': self.account.to_dict(),
            'positions': [self.pos_to_dict(p) for p in self.positions.values() if p.status == 'open'],
            'ts': datetime.now(timezone.utc).isoformat(),
        }
        save_trade_state(self.state_path, st)
    
    def persist_sync(self) -> None:
        """同步持久化当前状态（用于关闭时确保数据写入）
        
        与 persist() 的区别：
        - persist(): 异步写入，立即返回，数据进入队列
        - persist_sync(): 同步写入，使用文件锁直接写入磁盘
        """
        st = {
            'account': self.account.to_dict(),
            'positions': [self.pos_to_dict(p) for p in self.positions.values() if p.status == 'open'],
            'ts': datetime.now(timezone.utc).isoformat(),
        }
        # 使用文件锁同步写入
        locked_write_json(self.state_path, st)
        logger.info(f"同步持久化完成: balance={self.account.balance}, positions={len([p for p in self.positions.values() if p.status == 'open'])}")
    
    @staticmethod
    def pos_to_dict(p: Position) -> Dict[str, Any]:
        """Position对象转字典"""
        return p.__dict__.copy()
    
    def log_operation(self, event: str, payload: Dict[str, Any]) -> None:
        """记录操作事件（仅记录已平仓位到历史）"""
        try:
            if event == 'close_position' and payload.get('status') == 'closed':
                record = {
                    'id': payload.get('id'),
                    'symbol': payload.get('symbol'),
                    'side': payload.get('side'),
                    'entry_price': payload.get('entry_price'),
                    'close_price': payload.get('close_price'),
                    'tp_price': payload.get('tp_price'),
                    'sl_price': payload.get('sl_price'),
                    'original_sl_price': payload.get('original_sl_price'),  # 原始止损价
                    'original_tp_price': payload.get('original_tp_price'),  # 原始止盈价
                    'leverage': payload.get('leverage'),
                    'notional_usdt': payload.get('notional_usdt'),
                    'fees_open': payload.get('fees_open'),
                    'fees_close': payload.get('fees_close'),
                    'realized_pnl': payload.get('realized_pnl'),
                    'open_time': payload.get('open_time'),
                    'close_time': payload.get('close_time'),
                    'close_reason': payload.get('close_reason') or 'agent',
                    'operation_history': payload.get('operation_history', []),  # 操作历史
                }
                append_position_history(self.history_path, record)
                logger.info(f"操作日志记录: {event}, symbol={record.get('symbol')}, pnl={record.get('realized_pnl')}, ops_count={len(record.get('operation_history', []))}")
        except Exception as e:
            logger.error(f"写入操作日志失败: {e}")

