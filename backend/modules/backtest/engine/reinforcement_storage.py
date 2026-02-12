"""强化学习会话存储 - 负责保存和读取强化学习会话数据

职责：
- 保存 ReinforcementSession 到文件系统
- 维护会话索引文件用于快速查询
- 提供会话检索功能
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from modules.backtest.models import ReinforcementSession
from modules.agent.trade_simulator.utils.file_utils import locked_append_jsonl
from modules.monitor.utils.logger import get_logger

logger = get_logger('backtest.reinforcement_storage')


class ReinforcementStorage:
    """强化学习会话存储管理器
    
    存储结构：
    - {base_dir}/backtest/{backtest_id}/reinforcement/
      - sessions_index.jsonl  # 会话索引（快速查询）
      - sessions/
        - {session_id}.json   # 完整会话详情
    """
    
    def __init__(self, backtest_id: str, base_dir: str):
        """初始化存储管理器
        
        Args:
            backtest_id: 回测ID
            base_dir: 基础数据目录
        """
        self.backtest_id = backtest_id
        self.base_dir = base_dir
        self._lock = threading.Lock()
        
        self._reinforcement_dir = os.path.join(
            base_dir, "backtest", backtest_id, "reinforcement"
        )
        self._sessions_dir = os.path.join(self._reinforcement_dir, "sessions")
        self._index_path = os.path.join(self._reinforcement_dir, "sessions_index.jsonl")
        
        self._ensure_dirs()
    
    def _ensure_dirs(self) -> None:
        """确保目录结构存在"""
        os.makedirs(self._sessions_dir, exist_ok=True)
    
    def save_session(self, session: ReinforcementSession) -> str:
        """保存强化学习会话
        
        Args:
            session: 要保存的会话
            
        Returns:
            会话文件路径
        """
        with self._lock:
            session_path = os.path.join(
                self._sessions_dir, f"{session.session_id}.json"
            )
            
            session_data = session.to_dict()
            session_data["saved_at"] = datetime.now(timezone.utc).isoformat()
            
            with open(session_path, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2, default=str)
            
            index_record = {
                "session_id": session.session_id,
                "symbol": session.symbol,
                "kline_time": session.kline_time.isoformat(),
                "backtest_id": session.backtest_id,
                "final_outcome": session.final_outcome,
                "improvement_achieved": session.improvement_achieved,
                "total_rounds": session.total_rounds,
                "saved_at": session_data["saved_at"],
            }
            locked_append_jsonl(self._index_path, index_record, fsync=False)
            
            logger.info(
                f"保存强化学习会话: {session.session_id}, "
                f"symbol={session.symbol}, rounds={session.total_rounds}, "
                f"improvement={session.improvement_achieved}"
            )
            
            return session_path
    
    def load_session(self, session_id: str) -> Optional[ReinforcementSession]:
        """加载指定会话
        
        Args:
            session_id: 会话ID
            
        Returns:
            会话对象，如果不存在返回 None
        """
        session_path = os.path.join(self._sessions_dir, f"{session_id}.json")
        
        if not os.path.exists(session_path):
            logger.warning(f"会话文件不存在: {session_path}")
            return None
        
        try:
            with open(session_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return ReinforcementSession.from_dict(data)
        except Exception as e:
            logger.error(f"加载会话失败 {session_id}: {e}")
            return None
    
    def list_sessions(self) -> List[Dict[str, Any]]:
        """列出所有会话的索引信息
        
        Returns:
            会话索引记录列表
        """
        sessions = []
        
        if not os.path.exists(self._index_path):
            return sessions
        
        try:
            with open(self._index_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        sessions.append(record)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error(f"读取会话索引失败: {e}")
        
        return sessions
    
    def get_sessions_by_outcome(self, outcome: str) -> List[Dict[str, Any]]:
        """按最终结果筛选会话
        
        Args:
            outcome: 结果类型 ("loss", "profit", "timeout", "no_trade")
            
        Returns:
            符合条件的会话索引记录列表
        """
        all_sessions = self.list_sessions()
        return [s for s in all_sessions if s.get("final_outcome") == outcome]
    
    def get_improved_sessions(self) -> List[Dict[str, Any]]:
        """获取成功改进的会话（从亏损转为盈利/观望）
        
        Returns:
            成功改进的会话索引记录列表
        """
        all_sessions = self.list_sessions()
        return [s for s in all_sessions if s.get("improvement_achieved")]
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取强化学习统计信息
        
        Returns:
            统计信息字典
        """
        sessions = self.list_sessions()
        
        if not sessions:
            return {
                "total_sessions": 0,
                "improved_count": 0,
                "improvement_rate": 0.0,
                "outcome_distribution": {},
                "avg_rounds": 0.0,
            }
        
        improved_count = sum(1 for s in sessions if s.get("improvement_achieved"))
        
        outcome_dist = {}
        for s in sessions:
            outcome = s.get("final_outcome", "unknown")
            outcome_dist[outcome] = outcome_dist.get(outcome, 0) + 1
        
        total_rounds = sum(s.get("total_rounds", 0) for s in sessions)
        avg_rounds = total_rounds / len(sessions) if sessions else 0
        
        return {
            "total_sessions": len(sessions),
            "improved_count": improved_count,
            "improvement_rate": improved_count / len(sessions) if sessions else 0,
            "outcome_distribution": outcome_dist,
            "avg_rounds": round(avg_rounds, 2),
        }
    
    @property
    def reinforcement_dir(self) -> str:
        """获取强化学习数据目录"""
        return self._reinforcement_dir
    
    @property
    def index_path(self) -> str:
        """获取索引文件路径"""
        return self._index_path
