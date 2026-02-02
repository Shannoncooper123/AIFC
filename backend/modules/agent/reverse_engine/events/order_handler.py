"""反向交易订单事件处理器

职责说明（v3 - Binance 条件单管理 TP/SL）：
- 处理来自 Binance User Data Stream 的订单更新事件
- 监听条件单 (Algo Order) 的状态变化（ALGO_UPDATE 事件）
- 开仓条件单触发后创建开仓记录，并下止盈止损条件单
- 止盈/止损条件单触发后关闭开仓记录，并取消另一个条件单

工作流程：
1. 开仓条件单触发 (ALGO_UPDATE TRIGGERED) -> 创建开仓记录 -> 下 TP/SL 条件单
2. TP 条件单触发 -> 关闭记录 (TP_CLOSED) -> 取消 SL 条件单
3. SL 条件单触发 -> 关闭记录 (SL_CLOSED) -> 取消 TP 条件单

条件单类型区分：
- 开仓条件单：在 algo_order_service.pending_orders 中跟踪
- TP/SL 条件单：通过 trade_record_service 的 tp_algo_id/sl_algo_id 跟踪
"""

from typing import Dict, Any, Optional, TYPE_CHECKING
from modules.monitor.utils.logger import get_logger
from ..services.algo_order_service import AlgoOrderService
from ..services.history_writer import ReverseHistoryWriter
from ..models import AlgoOrderStatus, TradeRecordStatus

if TYPE_CHECKING:
    from ..services.trade_record_service import TradeRecordService

logger = get_logger('reverse_engine.order_handler')


class ReverseOrderHandler:
    """反向交易订单事件处理器
    
    职责：
    - 处理 ALGO_UPDATE 事件（条件单状态变化）
    - 区分开仓条件单和止盈止损条件单
    - 开仓条件单触发后创建开仓记录
    - 止盈止损条件单触发后关闭记录并取消另一个
    
    事件类型：
    - ALGO_UPDATE: 条件单状态更新（主要关注）
    - ORDER_TRADE_UPDATE: 普通订单状态更新（用于调试）
    - ACCOUNT_UPDATE: 账户状态更新
    """
    
    def __init__(self, algo_order_service: AlgoOrderService,
                 trade_record_service: 'TradeRecordService',
                 history_writer: ReverseHistoryWriter):
        """初始化
        
        Args:
            algo_order_service: 条件单服务
            trade_record_service: 开仓记录服务
            history_writer: 历史记录写入器
        """
        self.algo_order_service = algo_order_service
        self.trade_record_service = trade_record_service
        self.history_writer = history_writer
    
    def handle_event(self, event_type: str, data: Dict[str, Any]):
        """处理事件
        
        Args:
            event_type: 事件类型
            data: 事件数据
        """
        try:
            if event_type == 'ALGO_UPDATE':
                self._handle_algo_update(data)
            elif event_type == 'ORDER_TRADE_UPDATE':
                self._handle_order_update(data)
            elif event_type == 'ACCOUNT_UPDATE':
                self._handle_account_update(data)
        except Exception as e:
            logger.error(f"[反向] 处理事件失败: {e}", exc_info=True)
    
    def _handle_algo_update(self, data: Dict[str, Any]):
        """处理条件单状态更新事件 (ALGO_UPDATE)
        
        需要区分三种条件单：
        1. 开仓条件单 - 在 algo_order_service.pending_orders 中
        2. 止盈条件单 - 在某个开仓记录的 tp_algo_id 中
        3. 止损条件单 - 在某个开仓记录的 sl_algo_id 中
        
        Args:
            data: ALGO_UPDATE 事件数据
        """
        order_info = data.get('o', {})
        
        status = order_info.get('X', '')
        algo_id = str(order_info.get('aid', ''))
        symbol = order_info.get('s', '')
        side = order_info.get('S', '')
        order_type = order_info.get('o', '')
        
        logger.info(f"[反向] 📥 ALGO_UPDATE: {symbol} | status={status} | "
                   f"algoId={algo_id} | side={side} | type={order_type}")
        
        algo_order = self.algo_order_service.get_order(algo_id)
        if algo_order:
            self._handle_entry_order_update(algo_id, algo_order, status, order_info)
            return
        
        tp_record = self.trade_record_service.get_record_by_tp_algo_id(algo_id)
        if tp_record:
            self._handle_tp_order_update(algo_id, tp_record, status, order_info)
            return
        
        sl_record = self.trade_record_service.get_record_by_sl_algo_id(algo_id)
        if sl_record:
            self._handle_sl_order_update(algo_id, sl_record, status, order_info)
            return
        
        logger.debug(f"[反向] algoId={algo_id} 不在任何跟踪列表中")
    
    def _handle_entry_order_update(self, algo_id: str, algo_order, status: str, order_info: Dict):
        """处理开仓条件单状态更新
        
        Args:
            algo_id: 条件单ID
            algo_order: 条件单对象
            status: 状态
            order_info: 订单信息
        """
        symbol = algo_order.symbol
        
        if status == 'TRIGGERED':
            avg_price = float(order_info.get('ap', 0))
            if avg_price == 0:
                avg_price = algo_order.trigger_price
            
            logger.info(f"[反向] ✅ 开仓条件单已触发: {symbol} algoId={algo_id} price={avg_price}")
            
            self.algo_order_service.mark_order_triggered(algo_id, avg_price)
            
            record = self.trade_record_service.create_record(algo_order, avg_price)
            
            if record:
                logger.info(f"[反向] 📗 开仓记录已创建: {symbol} {record.side} @ {avg_price}")
                logger.info(f"[反向]    TP={record.tp_price} (algoId={record.tp_algo_id})")
                logger.info(f"[反向]    SL={record.sl_price} (algoId={record.sl_algo_id})")
            
            self.algo_order_service.remove_order(algo_id)
        
        elif status == 'FINISHED':
            avg_price = float(order_info.get('ap', 0))
            aq = float(order_info.get('aq', 0))
            
            logger.info(f"[反向] 开仓条件单已完成: {symbol} algoId={algo_id} "
                       f"avgPrice={avg_price} filledQty={aq}")
            
            if algo_id in self.algo_order_service.pending_orders:
                if avg_price > 0:
                    self.algo_order_service.mark_order_triggered(algo_id, avg_price)
                    record = self.trade_record_service.create_record(algo_order, avg_price)
                    if record:
                        logger.info(f"[反向] 📗 开仓记录已创建 (FINISHED): {symbol} @ {avg_price}")
                
                self.algo_order_service.remove_order(algo_id)
        
        elif status == 'CANCELED':
            logger.info(f"[反向] 开仓条件单已取消: {symbol} algoId={algo_id}")
            self.algo_order_service.remove_order(algo_id)
        
        elif status == 'EXPIRED':
            logger.info(f"[反向] 开仓条件单已过期: {symbol} algoId={algo_id}")
            self.algo_order_service.remove_order(algo_id)
        
        elif status == 'REJECTED':
            reason = order_info.get('rm', '')
            logger.warning(f"[反向] ⚠️ 开仓条件单被拒绝: {symbol} algoId={algo_id} reason={reason}")
            self.algo_order_service.remove_order(algo_id)
        
        elif status == 'NEW':
            logger.info(f"[反向] 开仓条件单已创建: {symbol} algoId={algo_id}")
        
        elif status == 'TRIGGERING':
            logger.info(f"[反向] 开仓条件单正在触发: {symbol} algoId={algo_id}")
    
    def _handle_tp_order_update(self, algo_id: str, record, status: str, order_info: Dict):
        """处理止盈条件单状态更新
        
        Args:
            algo_id: 条件单ID
            record: 关联的开仓记录
            status: 状态
            order_info: 订单信息
        """
        symbol = record.symbol
        
        if status in ('TRIGGERED', 'FINISHED'):
            avg_price = float(order_info.get('ap', 0))
            if avg_price == 0:
                avg_price = record.tp_price
            
            logger.info(f"[反向] 🎯 止盈单已触发: {symbol} algoId={algo_id} price={avg_price}")
            
            self.trade_record_service.cancel_remaining_tp_sl(record, 'TP')
            
            self.trade_record_service.close_record(
                record_id=record.id,
                close_price=avg_price,
                close_reason='TP_CLOSED'
            )
            
            logger.info(f"[反向] ✅ 止盈平仓完成: {symbol} @ {avg_price}")
        
        elif status == 'CANCELED':
            logger.info(f"[反向] 止盈单已取消: {symbol} algoId={algo_id}")
            record.tp_algo_id = None
            self.trade_record_service._save_state()
        
        elif status == 'EXPIRED':
            logger.info(f"[反向] 止盈单已过期: {symbol} algoId={algo_id}")
            record.tp_algo_id = None
            self.trade_record_service._save_state()
        
        elif status == 'REJECTED':
            reason = order_info.get('rm', '')
            logger.warning(f"[反向] ⚠️ 止盈单被拒绝: {symbol} algoId={algo_id} reason={reason}")
            record.tp_algo_id = None
            self.trade_record_service._save_state()
    
    def _handle_sl_order_update(self, algo_id: str, record, status: str, order_info: Dict):
        """处理止损条件单状态更新
        
        Args:
            algo_id: 条件单ID
            record: 关联的开仓记录
            status: 状态
            order_info: 订单信息
        """
        symbol = record.symbol
        
        if status in ('TRIGGERED', 'FINISHED'):
            avg_price = float(order_info.get('ap', 0))
            if avg_price == 0:
                avg_price = record.sl_price
            
            logger.info(f"[反向] 🛑 止损单已触发: {symbol} algoId={algo_id} price={avg_price}")
            
            self.trade_record_service.cancel_remaining_tp_sl(record, 'SL')
            
            self.trade_record_service.close_record(
                record_id=record.id,
                close_price=avg_price,
                close_reason='SL_CLOSED'
            )
            
            logger.info(f"[反向] ✅ 止损平仓完成: {symbol} @ {avg_price}")
        
        elif status == 'CANCELED':
            logger.info(f"[反向] 止损单已取消: {symbol} algoId={algo_id}")
            record.sl_algo_id = None
            self.trade_record_service._save_state()
        
        elif status == 'EXPIRED':
            logger.info(f"[反向] 止损单已过期: {symbol} algoId={algo_id}")
            record.sl_algo_id = None
            self.trade_record_service._save_state()
        
        elif status == 'REJECTED':
            reason = order_info.get('rm', '')
            logger.warning(f"[反向] ⚠️ 止损单被拒绝: {symbol} algoId={algo_id} reason={reason}")
            record.sl_algo_id = None
            self.trade_record_service._save_state()
    
    def _handle_order_update(self, data: Dict[str, Any]):
        """处理普通订单更新事件 (ORDER_TRADE_UPDATE)
        
        主要用于调试和日志记录。
        
        Args:
            data: 订单更新数据
        """
        order_info = data.get('o', {})
        
        order_type = order_info.get('ot', '')
        order_status = order_info.get('X', '')
        execution_type = order_info.get('x', '')
        symbol = order_info.get('s', '')
        order_id = str(order_info.get('i', ''))
        side = order_info.get('S', '')
        position_side = order_info.get('ps', '')
        
        logger.info(f"[反向] 📥 ORDER_TRADE_UPDATE: {symbol} | type={order_type} | "
                   f"status={order_status} | exec={execution_type} | "
                   f"side={side} | positionSide={position_side} | orderId={order_id}")
    
    def _handle_account_update(self, data: Dict[str, Any]):
        """处理账户更新事件
        
        Args:
            data: 账户更新数据
        """
        update_data = data.get('a', {})
        positions = update_data.get('P', [])
        
        for pos_data in positions:
            symbol = pos_data.get('s', '')
            position_amt = float(pos_data.get('pa', 0))
            mark_price = float(pos_data.get('mp', 0))
            
            open_records = self.trade_record_service.get_open_records_by_symbol(symbol)
            if open_records:
                self.trade_record_service.update_mark_price(symbol, mark_price)
                
                if position_amt == 0:
                    logger.info(f"[反向] {symbol} Binance 持仓已清零（账户更新检测）")
