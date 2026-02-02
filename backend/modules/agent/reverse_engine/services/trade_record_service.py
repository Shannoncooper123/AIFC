"""开仓记录管理服务

职责：
- 创建/查询/更新开仓记录
- 持久化到 JSON 文件
- 服务重启后恢复状态
- 每个条件单触发后创建独立记录，支持独立 TP/SL 管理
"""

import json
import os
import threading
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
from modules.monitor.utils.logger import get_logger
from ..models import ReverseTradeRecord, ReverseAlgoOrder, TradeRecordStatus

logger = get_logger('reverse_engine.trade_record')


class TradeRecordService:
    """开仓记录管理服务
    
    功能：
    - 管理独立的开仓记录（不依赖 Binance 持仓合并）
    - 每条记录有独立的 TP/SL 价格
    - 持久化到 JSON 文件，支持服务重启恢复
    - 路径从 config.yaml 读取
    """
    
    def __init__(self):
        """初始化"""
        self._lock = threading.RLock()
        self.records: Dict[str, ReverseTradeRecord] = {}
        
        self.state_file = self._get_state_file_path()
        
        self._ensure_state_dir()
        self._load_state()
    
    def _get_state_file_path(self) -> str:
        """从 settings.py 获取状态文件路径"""
        try:
            from modules.config.settings import get_config
            config = get_config()
            reverse_cfg = config.get('agent', {}).get('reverse', {})
            return reverse_cfg.get('trade_records_path', 'modules/data/reverse_trade_records.json')
        except Exception as e:
            logger.warning(f"从 settings 获取路径失败，使用默认路径: {e}")
            return 'modules/data/reverse_trade_records.json'
    
    def _ensure_state_dir(self):
        """确保状态目录存在"""
        state_dir = os.path.dirname(self.state_file)
        if state_dir and not os.path.exists(state_dir):
            os.makedirs(state_dir, exist_ok=True)
    
    def _load_state(self):
        """从文件加载状态"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for record_data in data.get('records', []):
                        record = ReverseTradeRecord.from_dict(record_data)
                        self.records[record.id] = record
                logger.info(f"[TradeRecord] 已加载 {len(self.records)} 条开仓记录")
        except Exception as e:
            logger.error(f"[TradeRecord] 加载状态失败: {e}")
    
    def _save_state(self):
        """保存状态到文件"""
        try:
            data = {
                'records': [r.to_dict() for r in self.records.values()],
                'updated_at': datetime.now().isoformat()
            }
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[TradeRecord] 保存状态失败: {e}")
    
    def create_record(self, algo_order: ReverseAlgoOrder, filled_price: float) -> ReverseTradeRecord:
        """从条件单创建开仓记录
        
        Args:
            algo_order: 触发的条件单
            filled_price: 成交价格
            
        Returns:
            创建的开仓记录
        """
        with self._lock:
            notional = algo_order.quantity * filled_price
            margin = notional / algo_order.leverage
            
            record = ReverseTradeRecord(
                id=str(uuid.uuid4()),
                symbol=algo_order.symbol,
                side=algo_order.side,
                qty=algo_order.quantity,
                entry_price=filled_price,
                tp_price=algo_order.tp_price,
                sl_price=algo_order.sl_price,
                leverage=algo_order.leverage,
                margin_usdt=margin,
                notional_usdt=notional,
                status=TradeRecordStatus.OPEN,
                algo_order_id=algo_order.algo_id,
                agent_order_id=algo_order.agent_order_id,
                open_time=datetime.now().isoformat(),
                latest_mark_price=filled_price
            )
            
            self.records[record.id] = record
            self._save_state()
            
            logger.info(f"[TradeRecord] ✅ 创建开仓记录: {record.symbol} {record.side} "
                       f"qty={record.qty} entry={filled_price} "
                       f"TP={record.tp_price} SL={record.sl_price}")
            
            return record
    
    def close_record(self, record_id: str, close_price: float, 
                     close_reason: str) -> Optional[ReverseTradeRecord]:
        """关闭开仓记录
        
        Args:
            record_id: 记录ID
            close_price: 平仓价格
            close_reason: 平仓原因（TP_CLOSED/SL_CLOSED/MANUAL_CLOSED）
            
        Returns:
            关闭的记录，未找到返回 None
        """
        with self._lock:
            record = self.records.get(record_id)
            if not record:
                logger.warning(f"[TradeRecord] 未找到记录: {record_id}")
                return None
            
            if record.status != TradeRecordStatus.OPEN:
                logger.warning(f"[TradeRecord] 记录已关闭: {record_id}")
                return record
            
            if record.side.upper() in ('LONG', 'BUY'):
                pnl = (close_price - record.entry_price) * record.qty
            else:
                pnl = (record.entry_price - close_price) * record.qty
            
            record.close_price = close_price
            record.close_time = datetime.now().isoformat()
            record.realized_pnl = pnl
            record.close_reason = close_reason
            record.status = TradeRecordStatus(close_reason)
            
            self._save_state()
            
            pnl_pct = (pnl / record.margin_usdt * 100) if record.margin_usdt > 0 else 0
            logger.info(f"[TradeRecord] 📕 关闭记录: {record.symbol} {record.side} "
                       f"entry={record.entry_price} close={close_price} "
                       f"PnL={pnl:.4f} ({pnl_pct:.2f}%) reason={close_reason}")
            
            return record
    
    def get_record(self, record_id: str) -> Optional[ReverseTradeRecord]:
        """获取指定记录
        
        Args:
            record_id: 记录ID
            
        Returns:
            记录对象
        """
        return self.records.get(record_id)
    
    def get_open_records(self) -> List[ReverseTradeRecord]:
        """获取所有开仓中的记录"""
        with self._lock:
            return [r for r in self.records.values() 
                    if r.status == TradeRecordStatus.OPEN]
    
    def get_records_by_symbol(self, symbol: str) -> List[ReverseTradeRecord]:
        """获取指定交易对的所有记录
        
        Args:
            symbol: 交易对
            
        Returns:
            记录列表
        """
        with self._lock:
            return [r for r in self.records.values() if r.symbol == symbol]
    
    def get_open_records_by_symbol(self, symbol: str) -> List[ReverseTradeRecord]:
        """获取指定交易对的开仓中记录
        
        Args:
            symbol: 交易对
            
        Returns:
            记录列表
        """
        with self._lock:
            return [r for r in self.records.values() 
                    if r.symbol == symbol and r.status == TradeRecordStatus.OPEN]
    
    def update_mark_price(self, symbol: str, mark_price: float):
        """更新指定交易对所有开仓记录的标记价格
        
        Args:
            symbol: 交易对
            mark_price: 标记价格
        """
        with self._lock:
            for record in self.records.values():
                if record.symbol == symbol and record.status == TradeRecordStatus.OPEN:
                    record.latest_mark_price = mark_price
    
    def get_watched_symbols(self) -> set:
        """获取所有需要监控的交易对（有开仓记录的）"""
        with self._lock:
            return {r.symbol for r in self.records.values() 
                    if r.status == TradeRecordStatus.OPEN}
    
    def get_summary(self) -> List[Dict[str, Any]]:
        """获取开仓记录汇总（用于前端展示）
        
        返回格式与前端 ReversePosition 类型匹配
        """
        with self._lock:
            result = []
            for record in self.records.values():
                if record.status != TradeRecordStatus.OPEN:
                    continue
                
                unrealized_pnl = record.unrealized_pnl()
                roe = record.roe()
                
                result.append({
                    'id': record.id,
                    'symbol': record.symbol,
                    'side': record.side.upper(),
                    'size': record.qty,
                    'entry_price': record.entry_price,
                    'mark_price': record.latest_mark_price or record.entry_price,
                    'take_profit': record.tp_price,
                    'stop_loss': record.sl_price,
                    'unrealized_pnl': round(unrealized_pnl, 4),
                    'roe': round(roe * 100, 2),
                    'leverage': record.leverage,
                    'margin': round(record.margin_usdt, 2),
                    'opened_at': record.open_time,
                    'algo_order_id': record.algo_order_id
                })
            
            return result
    
    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取已关闭的记录历史
        
        返回格式与前端 ReverseHistoryEntry 类型匹配
        
        Args:
            limit: 返回数量限制
            
        Returns:
            历史记录列表
        """
        with self._lock:
            closed_records = [r for r in self.records.values() 
                            if r.status != TradeRecordStatus.OPEN]
            closed_records.sort(key=lambda x: x.close_time or '', reverse=True)
            
            result = []
            for record in closed_records[:limit]:
                pnl_pct = (record.realized_pnl / record.margin_usdt * 100) if record.margin_usdt > 0 else 0
                result.append({
                    'id': record.id,
                    'symbol': record.symbol,
                    'side': record.side.upper(),
                    'qty': record.qty,
                    'entry_price': record.entry_price,
                    'exit_price': record.close_price,
                    'leverage': record.leverage,
                    'margin_usdt': round(record.margin_usdt, 2),
                    'realized_pnl': round(record.realized_pnl or 0, 4),
                    'pnl_percent': round(pnl_pct, 2),
                    'open_time': record.open_time,
                    'close_time': record.close_time,
                    'close_reason': record.close_reason,
                    'algo_order_id': record.algo_order_id,
                    'agent_order_id': record.agent_order_id
                })
            
            return result
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息
        
        返回格式与前端 ReverseStatistics 类型匹配
        """
        with self._lock:
            open_records = [r for r in self.records.values() 
                          if r.status == TradeRecordStatus.OPEN]
            closed_records = [r for r in self.records.values() 
                            if r.status != TradeRecordStatus.OPEN]
            
            pnl_list = [r.realized_pnl or 0 for r in closed_records]
            total_pnl = sum(pnl_list)
            win_count = sum(1 for pnl in pnl_list if pnl > 0)
            loss_count = sum(1 for pnl in pnl_list if pnl < 0)
            
            avg_pnl = total_pnl / len(closed_records) if closed_records else 0
            max_profit = max(pnl_list) if pnl_list else 0
            max_loss = min(pnl_list) if pnl_list else 0
            
            return {
                'total_trades': len(closed_records),
                'winning_trades': win_count,
                'losing_trades': loss_count,
                'win_rate': round(win_count / len(closed_records) * 100, 2) if closed_records else 0,
                'total_pnl': round(total_pnl, 4),
                'avg_pnl': round(avg_pnl, 4),
                'max_profit': round(max_profit, 4),
                'max_loss': round(max_loss, 4),
                'open_count': len(open_records)
            }
    
    def remove_record(self, record_id: str) -> bool:
        """移除记录（仅用于清理）
        
        Args:
            record_id: 记录ID
            
        Returns:
            是否成功
        """
        with self._lock:
            if record_id in self.records:
                del self.records[record_id]
                self._save_state()
                logger.info(f"[TradeRecord] 移除记录: {record_id}")
                return True
            return False
    
    def clear_closed_records(self, keep_days: int = 30):
        """清理过期的已关闭记录
        
        Args:
            keep_days: 保留天数
        """
        with self._lock:
            cutoff = datetime.now().timestamp() - (keep_days * 24 * 3600)
            to_remove = []
            
            for record_id, record in self.records.items():
                if record.status == TradeRecordStatus.OPEN:
                    continue
                
                if record.close_time:
                    try:
                        close_ts = datetime.fromisoformat(record.close_time).timestamp()
                        if close_ts < cutoff:
                            to_remove.append(record_id)
                    except:
                        pass
            
            for record_id in to_remove:
                del self.records[record_id]
            
            if to_remove:
                self._save_state()
                logger.info(f"[TradeRecord] 清理了 {len(to_remove)} 条过期记录")
