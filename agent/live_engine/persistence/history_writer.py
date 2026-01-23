"""历史记录写入器：记录已平仓的持仓到 position_history.json"""
from typing import Dict, Any
import json
import os
from datetime import datetime, timezone
from agent.trade_simulator.utils.file_utils import WriteQueue, TaskType
from monitor_module.utils.logger import get_logger

logger = get_logger('live_engine.history_writer')


class HistoryWriter:
    """历史记录写入器
    
    职责：
    - 记录已平仓的持仓到 position_history.json
    - 管理历史文件的读写
    """
    
    def __init__(self, config: Dict):
        """初始化
        
        Args:
            config: 配置字典
        """
        self.config = config
        agent_cfg = config.get('agent', {})
        self.history_path = agent_cfg.get('position_history_path', 'logs/position_history.json')
        self.write_queue = WriteQueue.get_instance()
        
        # 确保目录存在
        os.makedirs(os.path.dirname(self.history_path), exist_ok=True)
        
        # 如果文件不存在，创建空文件
        if not os.path.exists(self.history_path):
            self._init_history_file()
    
    def _init_history_file(self):
        """初始化空的历史文件"""
        try:
            initial_data = {"positions": []}
            with open(self.history_path, 'w', encoding='utf-8') as f:
                json.dump(initial_data, f, indent=2, ensure_ascii=False)
            logger.info(f"已创建历史仓位文件: {self.history_path}")
        except Exception as e:
            logger.error(f"创建历史文件失败: {e}")
    
    def record_closed_position(self, position: Any, close_reason: str = 'unknown', 
                               close_price: float = None, realized_pnl: float = None,
                               close_order_id: int = None):
        """记录已平仓的仓位
        
        Args:
            position: Position对象
            close_reason: 平仓原因（agent/止盈/止损）
            close_price: 平仓价格
            realized_pnl: 已实现盈亏
            close_order_id: 平仓订单ID（用于复盘）
        """
        try:
            # 构造历史记录
            record = {
                'id': position.id,
                'symbol': position.symbol,
                'side': position.side,
                'qty': position.qty,
                'entry_price': position.entry_price,
                'close_price': close_price or position.latest_mark_price or position.entry_price,
                'leverage': position.leverage,
                'notional_usdt': position.notional_usdt,
                'margin_used': position.margin_used,
                'tp_price': position.tp_price,
                'sl_price': position.sl_price,
                'open_time': position.open_time,
                'close_time': datetime.now(timezone.utc).isoformat(),
                'close_reason': close_reason,
                'close_order_id': close_order_id,
                'realized_pnl': realized_pnl if realized_pnl is not None else position.unrealized_pnl(close_price),
                'fees_open': position.fees_open if hasattr(position, 'fees_open') else 0.0,
                'fees_close': 0.0,  # 实盘手续费从账户余额变化中体现
            }
            
            # 读取现有历史
            history = self._load_history()
            
            # 追加记录
            history['positions'].append(record)
            
            # 异步写入
            self.write_queue.enqueue(TaskType.HISTORY, self.history_path, history, indent=2, ensure_ascii=False)
            
            logger.info(f"已记录平仓历史: {position.symbol} {position.side} "
                       f"盈亏=${realized_pnl if realized_pnl is not None else 0:.2f} "
                       f"原因={close_reason}")
        
        except Exception as e:
            logger.error(f"记录平仓历史失败: {e}", exc_info=True)
    
    def _load_history(self) -> Dict[str, Any]:
        """加载历史文件（内部使用）"""
        try:
            if not os.path.exists(self.history_path):
                return {"positions": []}
            
            with open(self.history_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if not isinstance(data, dict) or 'positions' not in data:
                    return {"positions": []}
                return data
        except Exception as e:
            logger.error(f"读取历史文件失败: {e}")
            return {"positions": []}

