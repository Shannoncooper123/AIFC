"""反向交易历史记录写入器"""

import json
import os
import threading
from datetime import datetime
from typing import Dict, List, Any, Optional
from modules.monitor.utils.logger import get_logger
from ..models import ReversePosition, ReverseTradeHistory

logger = get_logger('reverse_engine.history_writer')


class ReverseHistoryWriter:
    """反向交易历史记录写入器"""
    
    HISTORY_FILE = 'agent/reverse_history.json'
    MAX_HISTORY_RECORDS = 1000
    
    def __init__(self, config: Dict):
        """初始化
        
        Args:
            config: 配置字典
        """
        self.config = config
        self._lock = threading.RLock()
        
        self.history: List[ReverseTradeHistory] = []
        
        self._ensure_history_dir()
        self._load_history()
    
    def _ensure_history_dir(self):
        """确保历史目录存在"""
        history_dir = os.path.dirname(self.HISTORY_FILE)
        if history_dir and not os.path.exists(history_dir):
            os.makedirs(history_dir, exist_ok=True)
    
    def _load_history(self):
        """从文件加载历史"""
        try:
            if os.path.exists(self.HISTORY_FILE):
                with open(self.HISTORY_FILE, 'r', encoding='utf-8') as f:
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
            with open(self.HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[反向] 保存历史记录失败: {e}")
    
    def record_closed_position(self, position: ReversePosition,
                                close_reason: str,
                                close_price: float,
                                close_order_id: Optional[int] = None):
        """记录平仓历史
        
        Args:
            position: 被平仓的持仓
            close_reason: 平仓原因（止盈/止损/手动）
            close_price: 平仓价格
            close_order_id: 平仓订单ID
        """
        with self._lock:
            try:
                if position.side == 'long':
                    realized_pnl = (close_price - position.entry_price) * position.qty
                else:
                    realized_pnl = (position.entry_price - close_price) * position.qty
                
                pnl_percent = 0.0
                if position.margin_usdt > 0:
                    pnl_percent = (realized_pnl / position.margin_usdt) * 100
                
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
                
                logger.info(f"[反向] 平仓记录已保存: {position.symbol} "
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
