"""反向交易历史记录写入器

架构说明：
- 强制复用 live_engine 的 HistoryWriter（双写模式）
- 同时保留反向交易专用的历史文件用于统计
- 平仓时同时写入两个地方：
  1. 反向交易专用历史（用于统计胜率、盈亏等）
  2. live_engine 的通用历史（用于前端统一展示）
"""

import json
import os
import threading
from datetime import datetime
from typing import Dict, List, Any, TYPE_CHECKING
from modules.monitor.utils.logger import get_logger
from ..models import ReversePosition, ReverseTradeHistory

if TYPE_CHECKING:
    from modules.agent.live_engine.persistence.history_writer import HistoryWriter as LiveHistoryWriter

logger = get_logger('reverse_engine.history_writer')


class ReverseHistoryWriter:
    """反向交易历史记录写入器
    
    职责：
    - 记录反向交易的平仓历史到独立文件（用于统计）
    - 同时写入 live_engine 的历史文件（用于前端展示）
    - 计算反向交易的统计信息
    
    架构：
    - 强制依赖 live_history_writer
    - 双写模式确保数据一致性
    - 路径从 config.yaml 读取
    """
    
    MAX_HISTORY_RECORDS = 1000
    
    def __init__(self, config: Dict, live_history_writer: 'LiveHistoryWriter'):
        """初始化
        
        Args:
            config: 配置字典
            live_history_writer: live_engine 的历史写入器（必需）
            
        Raises:
            ValueError: 如果 live_history_writer 为 None
        """
        if live_history_writer is None:
            raise ValueError("ReverseHistoryWriter 必须传入 live_history_writer 参数")
        
        self.config = config
        self.live_history_writer = live_history_writer
        self._lock = threading.RLock()
        
        self.history_file = self._get_history_file_path()
        self.history: List[ReverseTradeHistory] = []
        
        self._ensure_history_dir()
        self._load_history()
        
        logger.info("[反向] 历史记录写入器已初始化（双写模式）")
    
    def _get_history_file_path(self) -> str:
        """从 settings.py 获取历史文件路径"""
        try:
            from modules.config.settings import get_config
            config = get_config()
            reverse_cfg = config.get('agent', {}).get('reverse', {})
            return reverse_cfg.get('history_path', 'modules/data/reverse_history.json')
        except Exception as e:
            logger.warning(f"从 settings 获取路径失败，使用默认路径: {e}")
            return 'modules/data/reverse_history.json'
    
    def _ensure_history_dir(self):
        """确保历史目录存在"""
        history_dir = os.path.dirname(self.history_file)
        if history_dir and not os.path.exists(history_dir):
            os.makedirs(history_dir, exist_ok=True)
    
    def _load_history(self):
        """从文件加载历史"""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for record in data.get('history', []):
                        self.history.append(ReverseTradeHistory.from_dict(record))
                logger.info(f"[反向] 已加载 {len(self.history)} 条历史记录")
        except Exception as e:
            logger.error(f"[反向] 加载历史记录失败: {e}")
    
    def _save_history(self):
        """保存历史到文件"""
        try:
            data = {
                'history': [h.to_dict() for h in self.history[-self.MAX_HISTORY_RECORDS:]],
                'updated_at': datetime.now().isoformat()
            }
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[反向] 保存历史记录失败: {e}")
    
    def record_closed_position(self, position: ReversePosition,
                                close_reason: str,
                                close_price: float,
                                close_order_id: int = None):
        """记录平仓历史（双写模式）
        
        同时写入：
        1. 反向交易专用历史文件（用于统计）
        2. live_engine 的通用历史文件（用于前端展示）
        
        Args:
            position: 被平仓的持仓
            close_reason: 平仓原因（止盈/止损/手动）
            close_price: 平仓价格
            close_order_id: 平仓订单ID
        """
        with self._lock:
            try:
                # 计算盈亏
                if position.side == 'long' or position.side.lower() == 'buy':
                    realized_pnl = (close_price - position.entry_price) * position.qty
                else:
                    realized_pnl = (position.entry_price - close_price) * position.qty
                
                pnl_percent = 0.0
                if position.margin_usdt > 0:
                    pnl_percent = (realized_pnl / position.margin_usdt) * 100
                
                # 1. 写入反向交易专用历史
                record = ReverseTradeHistory(
                    id=position.id,
                    symbol=position.symbol,
                    side=position.side,
                    qty=position.qty,
                    entry_price=position.entry_price,
                    exit_price=close_price,
                    leverage=position.leverage,
                    margin_usdt=position.margin_usdt,
                    realized_pnl=round(realized_pnl, 4),
                    pnl_percent=round(pnl_percent, 2),
                    open_time=position.open_time,
                    close_time=datetime.now().isoformat(),
                    close_reason=close_reason,
                    algo_order_id=position.algo_order_id,
                    agent_order_id=position.agent_order_id
                )
                
                self.history.append(record)
                
                if len(self.history) > self.MAX_HISTORY_RECORDS:
                    self.history = self.history[-self.MAX_HISTORY_RECORDS:]
                
                self._save_history()
                
                # 2. 写入 live_engine 的通用历史（标记为反向交易）
                self.live_history_writer.record_closed_position(
                    position=position,
                    close_reason=f"[反向] {close_reason}",
                    close_price=close_price,
                    realized_pnl=realized_pnl,
                    close_order_id=close_order_id,
                    is_reverse=True
                )
                
                logger.info(f"[反向] 平仓记录已保存（双写）: {position.symbol} "
                           f"reason={close_reason} pnl={realized_pnl:.2f}U ({pnl_percent:.1f}%)")
                
            except Exception as e:
                logger.error(f"[反向] 记录平仓历史失败: {e}", exc_info=True)
    
    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取历史记录
        
        Args:
            limit: 返回数量限制
            
        Returns:
            历史记录列表
        """
        with self._lock:
            records = self.history[-limit:]
            records.reverse()
            return [h.to_dict() for h in records]
    
    def get_total_pnl(self) -> float:
        """获取总盈亏"""
        with self._lock:
            return sum(h.realized_pnl for h in self.history)
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            if not self.history:
                return {
                    'total_trades': 0,
                    'winning_trades': 0,
                    'losing_trades': 0,
                    'win_rate': 0.0,
                    'total_pnl': 0.0,
                    'avg_pnl': 0.0,
                    'max_profit': 0.0,
                    'max_loss': 0.0
                }
            
            winning = [h for h in self.history if h.realized_pnl > 0]
            losing = [h for h in self.history if h.realized_pnl < 0]
            
            total_pnl = sum(h.realized_pnl for h in self.history)
            pnls = [h.realized_pnl for h in self.history]
            
            return {
                'total_trades': len(self.history),
                'winning_trades': len(winning),
                'losing_trades': len(losing),
                'win_rate': round(len(winning) / len(self.history) * 100, 1) if self.history else 0.0,
                'total_pnl': round(total_pnl, 2),
                'avg_pnl': round(total_pnl / len(self.history), 2) if self.history else 0.0,
                'max_profit': round(max(pnls), 2) if pnls else 0.0,
                'max_loss': round(min(pnls), 2) if pnls else 0.0
            }
