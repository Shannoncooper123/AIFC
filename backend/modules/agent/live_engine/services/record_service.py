"""独立开仓记录服务（业务逻辑层）

管理独立的开仓记录，每条记录有独立的 TP/SL，支持多策略共用。

架构说明（v2 - 分层架构）：
- 数据层：RecordRepository（CRUD + 持久化）
- 业务层：RecordService（TP/SL 逻辑、统计等）

与 PositionService 的区别：
- PositionService: 跟踪 Binance 合约持仓（同币种同方向会合并）
- RecordService: 管理独立的开仓记录（每条记录有独立 TP/SL）
"""

from typing import Dict, List, Optional, Any, TYPE_CHECKING
from modules.monitor.utils.logger import get_logger
from modules.agent.shared import RecordRepository, RecordStatus, TradeRecord

if TYPE_CHECKING:
    from modules.monitor.clients.binance_rest import BinanceRestClient
    from .order_manager import OrderManager

logger = get_logger('live_engine.record_service')


class RecordService:
    """独立开仓记录服务（业务逻辑层）
    
    职责：
    - 创建/关闭记录（带业务逻辑）
    - TP/SL 订单管理
    - 统计和汇总
    
    数据操作委托给 RecordRepository。
    """
    
    def __init__(
        self,
        rest_client: 'BinanceRestClient' = None,
        order_manager: 'OrderManager' = None,
        repository: Optional[RecordRepository] = None,
        state_file: Optional[str] = None
    ):
        """初始化
        
        Args:
            rest_client: Binance REST 客户端
            order_manager: 订单管理器（用于下 TP/SL 单）
            repository: 数据仓库（可选，不传则自动创建）
            state_file: 状态文件路径（仅在不传 repository 时使用）
        """
        self.rest_client = rest_client
        self.order_manager = order_manager
        
        if repository:
            self._repository = repository
        else:
            file_path = state_file or self._get_state_file_path()
            self._repository = RecordRepository(state_file=file_path)
    
    def _get_state_file_path(self) -> str:
        """获取状态文件路径"""
        try:
            from modules.config.settings import get_config
            config = get_config()
            return config.get('agent', {}).get('records_path', 'modules/data/trade_records.json')
        except Exception as e:
            logger.warning(f"获取状态文件路径失败，使用默认路径: {e}")
            return 'modules/data/trade_records.json'
    
    @property
    def records(self) -> Dict[str, TradeRecord]:
        """兼容属性：获取所有记录的字典"""
        return {r.id: r for r in self._repository.get_all()}
    
    def create_record(
        self,
        symbol: str,
        side: str,
        qty: float,
        entry_price: float,
        leverage: int = 10,
        tp_price: Optional[float] = None,
        sl_price: Optional[float] = None,
        source: str = 'live',
        entry_order_id: Optional[int] = None,
        entry_algo_id: Optional[str] = None,
        agent_order_id: Optional[str] = None,
        entry_commission: float = 0.0,
        auto_place_tpsl: bool = True,
        extra_data: Optional[Dict] = None
    ) -> TradeRecord:
        """创建开仓记录
        
        Args:
            symbol: 交易对
            side: 方向
            qty: 数量
            entry_price: 开仓价格
            leverage: 杠杆
            tp_price: 止盈价
            sl_price: 止损价
            source: 来源标识（live/reverse/...）
            entry_order_id: 开仓订单ID
            entry_algo_id: 开仓策略单ID
            agent_order_id: Agent 订单ID
            entry_commission: 开仓手续费
            auto_place_tpsl: 是否自动下 TP/SL 单
            extra_data: 额外数据
            
        Returns:
            创建的记录
        """
        record = self._repository.create(
            symbol=symbol,
            side=side,
            qty=qty,
            entry_price=entry_price,
            leverage=leverage,
            tp_price=tp_price,
            sl_price=sl_price,
            source=source,
            entry_order_id=entry_order_id,
            entry_algo_id=entry_algo_id,
            agent_order_id=agent_order_id,
            extra_data=extra_data,
        )
        
        if entry_commission > 0:
            self._repository.update(record.id, entry_commission=entry_commission)
        
        logger.info(f"[RecordService] ✅ 创建记录: {symbol} {side} qty={qty} "
                   f"entry={entry_price} source={source}")
        
        if auto_place_tpsl and self.order_manager and (tp_price or sl_price):
            tpsl_result = self.order_manager.place_tp_sl_for_position(
                symbol=symbol,
                side=side,
                quantity=qty,
                tp_price=tp_price,
                sl_price=sl_price,
                use_limit_for_tp=True
            )
            
            self._repository.update_tpsl_ids(
                record.id,
                tp_order_id=tpsl_result.get('tp_order_id'),
                tp_algo_id=tpsl_result.get('tp_algo_id'),
                sl_algo_id=tpsl_result.get('sl_algo_id')
            )
            
            record = self._repository.get(record.id)
            logger.info(f"[RecordService] TP/SL 已下单: tp_order={record.tp_order_id} "
                       f"tp_algo={record.tp_algo_id} sl_algo={record.sl_algo_id}")
        
        return record
    
    def close_record(
        self,
        record_id: str,
        close_price: float,
        close_reason: str,
        exit_commission: float = 0.0,
        realized_pnl: Optional[float] = None
    ) -> Optional[TradeRecord]:
        """关闭记录
        
        Args:
            record_id: 记录ID
            close_price: 平仓价格
            close_reason: 平仓原因
            exit_commission: 平仓手续费
            realized_pnl: 已实现盈亏（可从 API 获取）
            
        Returns:
            关闭的记录
        """
        record = self._repository.get(record_id)
        if not record:
            logger.warning(f"[RecordService] 未找到记录: {record_id}")
            return None
        
        if record.status != RecordStatus.OPEN:
            logger.warning(f"[RecordService] 记录已关闭: {record_id}")
            return record
        
        total_commission = record.entry_commission + exit_commission
        
        if realized_pnl is None:
            if record.side.upper() in ('LONG', 'BUY'):
                pnl = (close_price - record.entry_price) * record.qty
            else:
                pnl = (record.entry_price - close_price) * record.qty
            realized_pnl = pnl - total_commission
        
        self._repository.update(record_id, 
                               exit_commission=exit_commission,
                               total_commission=total_commission)
        
        record = self._repository.close(record_id, close_price, close_reason, realized_pnl)
        
        if record:
            pnl_sign = '+' if (record.realized_pnl or 0) >= 0 else ''
            logger.info(f"[RecordService] 📕 关闭记录: {record.symbol} {record.side} "
                       f"PnL={pnl_sign}{record.realized_pnl:.4f} reason={close_reason}")
        
        return record
    
    def get_record(self, record_id: str) -> Optional[TradeRecord]:
        """获取记录"""
        return self._repository.get(record_id)
    
    def get_open_records(self, source: Optional[str] = None) -> List[TradeRecord]:
        """获取开仓中的记录"""
        return self._repository.get_open_records(source)
    
    def get_records_by_symbol(self, symbol: str, source: Optional[str] = None) -> List[TradeRecord]:
        """获取指定交易对的记录"""
        return self._repository.find_by_symbol(symbol, source)
    
    def get_open_records_by_symbol(self, symbol: str, source: Optional[str] = None) -> List[TradeRecord]:
        """获取指定交易对的开仓记录"""
        records = self._repository.find_by_symbol(symbol, source)
        return [r for r in records if r.status == RecordStatus.OPEN]
    
    def find_record_by_tp_order_id(self, tp_order_id: int) -> Optional[TradeRecord]:
        """根据止盈订单ID查找记录"""
        return self._repository.find_by_tp_order_id(tp_order_id)
    
    def find_record_by_tp_algo_id(self, tp_algo_id: str) -> Optional[TradeRecord]:
        """根据止盈策略单ID查找记录"""
        return self._repository.find_by_tp_algo_id(tp_algo_id)
    
    def find_record_by_sl_algo_id(self, sl_algo_id: str) -> Optional[TradeRecord]:
        """根据止损策略单ID查找记录"""
        return self._repository.find_by_sl_algo_id(sl_algo_id)
    
    def find_record_by_entry_order_id(self, order_id: int) -> Optional[TradeRecord]:
        """根据开仓订单ID查找记录"""
        return self._repository.find_by_entry_order_id(order_id)
    
    def find_record_by_entry_algo_id(self, algo_id: str) -> Optional[TradeRecord]:
        """根据开仓策略单ID查找记录"""
        return self._repository.find_by_entry_algo_id(algo_id)
    
    def update_mark_price(self, symbol: str, mark_price: float):
        """更新标记价格"""
        self._repository.update_mark_price(symbol, mark_price)
    
    def update_tpsl_ids(
        self,
        record_id: str,
        tp_order_id: Optional[int] = None,
        tp_algo_id: Optional[str] = None,
        sl_algo_id: Optional[str] = None
    ):
        """更新 TP/SL 订单ID"""
        self._repository.update_tpsl_ids(record_id, tp_order_id, tp_algo_id, sl_algo_id)
    
    def update_record_tpsl_ids(
        self,
        record_id: str,
        tp_order_id: Optional[int] = ...,
        tp_algo_id: Optional[str] = ...,
        sl_algo_id: Optional[str] = ...
    ):
        """更新单个 TP/SL 订单ID（允许设为 None）"""
        record = self._repository.get(record_id)
        if not record:
            return
        
        updates = {}
        if tp_order_id is not ...:
            updates['tp_order_id'] = tp_order_id
        if tp_algo_id is not ...:
            updates['tp_algo_id'] = tp_algo_id
        if sl_algo_id is not ...:
            updates['sl_algo_id'] = sl_algo_id
        
        if updates:
            self._repository.update(record_id, **updates)
    
    def clear_tpsl_ids(self, record_id: str):
        """清除记录的所有 TP/SL ID"""
        self._repository.clear_tpsl_ids(record_id)
    
    def cancel_remaining_tpsl(self, record: TradeRecord, triggered_type: str):
        """取消剩余的 TP/SL 订单
        
        Args:
            record: 记录
            triggered_type: 触发类型（TP/SL）
        """
        if not self.order_manager:
            return
        
        try:
            if triggered_type == 'TP':
                if record.sl_algo_id:
                    self.order_manager.cancel_algo_order(record.symbol, record.sl_algo_id)
                    logger.info(f"[RecordService] 🚫 取消止损单: {record.symbol} algoId={record.sl_algo_id}")
                    self._repository.update(record.id, sl_algo_id=None)
            elif triggered_type == 'SL':
                if record.tp_order_id:
                    self.order_manager.cancel_order(record.symbol, record.tp_order_id)
                    logger.info(f"[RecordService] 🚫 取消止盈限价单: {record.symbol} orderId={record.tp_order_id}")
                    self._repository.update(record.id, tp_order_id=None)
                if record.tp_algo_id:
                    self.order_manager.cancel_algo_order(record.symbol, record.tp_algo_id)
                    logger.info(f"[RecordService] 🚫 取消止盈策略单: {record.symbol} algoId={record.tp_algo_id}")
                    self._repository.update(record.id, tp_algo_id=None)
        except Exception as e:
            logger.error(f"[RecordService] 取消订单失败: {e}")
    
    def get_summary(self, source: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取开仓记录汇总"""
        records = self._repository.get_open_records(source)
        result = []
        
        for record in records:
            result.append({
                'id': record.id,
                'symbol': record.symbol,
                'side': record.side.upper(),
                'size': record.qty,
                'entry_price': record.entry_price,
                'mark_price': record.latest_mark_price or record.entry_price,
                'take_profit': record.tp_price,
                'stop_loss': record.sl_price,
                'tp_order_id': record.tp_order_id,
                'tp_algo_id': record.tp_algo_id,
                'sl_algo_id': record.sl_algo_id,
                'unrealized_pnl': round(record.unrealized_pnl(), 4),
                'roe': round(record.roe() * 100, 2),
                'leverage': record.leverage,
                'margin': round(record.margin_usdt, 4),
                'opened_at': record.open_time,
                'source': record.source
            })
        
        return result
    
    def get_statistics(self, source: Optional[str] = None) -> Dict[str, Any]:
        """获取统计信息"""
        all_records = self._repository.get_all()
        
        if source:
            all_records = [r for r in all_records if r.source == source]
        
        open_records = [r for r in all_records if r.status == RecordStatus.OPEN]
        closed_records = [r for r in all_records if r.status != RecordStatus.OPEN]
        
        pnl_list = [r.realized_pnl or 0 for r in closed_records]
        total_pnl = sum(pnl_list)
        win_count = sum(1 for pnl in pnl_list if pnl > 0)
        loss_count = sum(1 for pnl in pnl_list if pnl < 0)
        total_commission = sum(r.total_commission for r in closed_records)
        
        return {
            'total_trades': len(closed_records),
            'winning_trades': win_count,
            'losing_trades': loss_count,
            'win_rate': round(win_count / len(closed_records) * 100, 2) if closed_records else 0,
            'total_pnl': round(total_pnl, 4),
            'avg_pnl': round(total_pnl / len(closed_records), 4) if closed_records else 0,
            'max_profit': round(max(pnl_list), 4) if pnl_list else 0,
            'max_loss': round(min(pnl_list), 4) if pnl_list else 0,
            'open_count': len(open_records),
            'total_commission': round(total_commission, 6)
        }
    
    def get_watched_symbols(self, source: Optional[str] = None) -> set:
        """获取需要监控的交易对"""
        records = self._repository.get_open_records(source)
        return {r.symbol for r in records}
    
    def remove_record(self, record_id: str) -> bool:
        """移除记录（清理用）"""
        result = self._repository.delete(record_id)
        if result:
            logger.info(f"[RecordService] 移除记录: {record_id}")
        return result
