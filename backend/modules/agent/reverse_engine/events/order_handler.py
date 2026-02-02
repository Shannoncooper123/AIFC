"""反向交易订单事件处理器

职责说明（v2 - 自主管理 TP/SL）：
- 处理来自 Binance User Data Stream 的订单更新事件
- 监听条件单 (Algo Order) 的状态变化（ALGO_UPDATE 事件）
- 条件单触发后创建开仓记录（不再下 Binance TP/SL 订单）
- TP/SL 由 TPSLMonitorService 通过 Mark Price WebSocket 自行管理

工作流程：
1. 条件单触发 (ALGO_UPDATE TRIGGERED) -> 创建开仓记录
2. Mark Price 触达 TP/SL -> TPSLMonitorService 执行平仓

事件字段说明：
- ALGO_UPDATE: 条件单状态更新
  - o.X: 条件单状态 (NEW/TRIGGERED/FINISHED/CANCELED/EXPIRED)
  - o.aid: 条件单ID
  - o.ap: 触发后实际成交价格
  - o.s: 交易对
"""

from typing import Dict, Any, Optional, TYPE_CHECKING
from modules.monitor.utils.logger import get_logger
from ..services.algo_order_service import AlgoOrderService
from ..services.history_writer import ReverseHistoryWriter
from ..models import AlgoOrderStatus

if TYPE_CHECKING:
    from ..services.trade_record_service import TradeRecordService

logger = get_logger('reverse_engine.order_handler')


class ReverseOrderHandler:
    """反向交易订单事件处理器
    
    职责：
    - 处理 ALGO_UPDATE 事件（条件单状态变化）
    - 条件单触发后创建开仓记录
    - 协调 AlgoOrderService、TradeRecordService
    
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
        
        这是条件单专用的事件类型，包含条件单的完整状态信息。
        
        状态说明：
        - NEW: 条件订单已提交，但尚未触发
        - CANCELED: 条件订单已被取消
        - TRIGGERING: 条件订单已满足触发条件，正在转发至撮合引擎
        - TRIGGERED: 条件订单已成功触发并进入撮合引擎
        - FINISHED: 触发的条件订单已在撮合引擎中被成交或取消
        - REJECTED: 条件订单被撮合引擎拒绝
        - EXPIRED: 条件订单被系统取消
        
        Args:
            data: ALGO_UPDATE 事件数据
        """
        order_info = data.get('o', {})
        
        status = order_info.get('X', '')
        algo_id = str(order_info.get('aid', ''))
        symbol = order_info.get('s', '')
        side = order_info.get('S', '')
        
        logger.info(f"[反向] 📥 ALGO_UPDATE: {symbol} | status={status} | algoId={algo_id} | side={side}")
        
        algo_order = self.algo_order_service.get_order(algo_id)
        
        if not algo_order:
            pending_ids = list(self.algo_order_service.pending_orders.keys())
            logger.debug(f"[反向] algoId={algo_id} 不在跟踪列表中，当前跟踪: {pending_ids}")
            return
        
        if status == 'TRIGGERED':
            avg_price = float(order_info.get('ap', 0))
            if avg_price == 0:
                avg_price = algo_order.trigger_price
            
            logger.info(f"[反向] ✅ 条件单已触发: {symbol} algoId={algo_id} price={avg_price}")
            
            self.algo_order_service.mark_order_triggered(algo_id, avg_price)
            
            record = self.trade_record_service.create_record(algo_order, avg_price)
            
            if record:
                logger.info(f"[反向] 📗 开仓记录已创建: {symbol} {record.side} @ {avg_price}")
                logger.info(f"[反向]    TP={record.tp_price} SL={record.sl_price}")
            
            self.algo_order_service.remove_order(algo_id)
        
        elif status == 'FINISHED':
            avg_price = float(order_info.get('ap', 0))
            aq = float(order_info.get('aq', 0))
            
            logger.info(f"[反向] 条件单已完成: {symbol} algoId={algo_id} avgPrice={avg_price} filledQty={aq}")
            
            if algo_id in self.algo_order_service.pending_orders:
                if avg_price > 0:
                    self.algo_order_service.mark_order_triggered(algo_id, avg_price)
                    
                    record = self.trade_record_service.create_record(algo_order, avg_price)
                    if record:
                        logger.info(f"[反向] 📗 开仓记录已创建 (FINISHED): {symbol} {record.side} @ {avg_price}")
                
                self.algo_order_service.remove_order(algo_id)
        
        elif status == 'CANCELED':
            logger.info(f"[反向] 条件单已取消: {symbol} algoId={algo_id}")
            self.algo_order_service.remove_order(algo_id)
        
        elif status == 'EXPIRED':
            logger.info(f"[反向] 条件单已过期: {symbol} algoId={algo_id}")
            self.algo_order_service.remove_order(algo_id)
        
        elif status == 'REJECTED':
            reason = order_info.get('rm', '')
            logger.warning(f"[反向] ⚠️ 条件单被拒绝: {symbol} algoId={algo_id} reason={reason}")
            self.algo_order_service.remove_order(algo_id)
        
        elif status == 'NEW':
            logger.info(f"[反向] 条件单已创建: {symbol} algoId={algo_id}")
        
        elif status == 'TRIGGERING':
            logger.info(f"[反向] 条件单正在触发: {symbol} algoId={algo_id}")
    
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
