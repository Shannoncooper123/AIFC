"""ALGO_UPDATE 事件处理器

处理 Binance 条件单（Algo Order）的状态变化事件。

职责：
- 监听 ALGO_UPDATE 事件（条件单状态变化）
- 区分三种条件单：开仓条件单、止盈条件单、止损条件单
- 止盈/止损触发后自动关闭记录并取消另一个条件单

事件流程：
1. 开仓条件单触发 (TRIGGERED/FILLED) -> RecordService.create_record
2. TP 条件单触发 -> 关闭记录 (TP_CLOSED) -> 取消 SL 条件单
3. SL 条件单触发 -> 关闭记录 (SL_CLOSED) -> 取消 TP 条件单

ALGO_UPDATE 事件格式：
{
    "e": "ALGO_UPDATE",
    "o": {
        "s": "BTCUSDT",       # symbol
        "aid": "123456",      # algo_id
        "X": "FILLED",        # status: NEW/TRIGGERED/TRIGGERING/FILLED/CANCELLED/EXPIRED/REJECTED
        "ap": "50000.0",      # avg_price
        "ai": "789",          # 触发后生成的市价单 order_id
        "S": "BUY",           # side
        "o": "STOP_MARKET",   # order_type
        "aq": "0.1",          # filled_qty
        "rm": "reason"        # reject_reason（仅 REJECTED 状态）
    }
}
"""

from typing import Dict, Any, Optional, TYPE_CHECKING, Callable
from modules.monitor.utils.logger import get_logger

if TYPE_CHECKING:
    from ..services.record_service import RecordService
    from ..services.order_manager import OrderManager

logger = get_logger('live_engine.algo_order_handler')


class AlgoOrderHandler:
    """ALGO_UPDATE 事件处理器
    
    职责：
    - 处理条件单状态变化事件
    - 区分开仓条件单和 TP/SL 条件单
    - 止盈止损触发后自动关闭记录
    """
    
    def __init__(
        self,
        record_service: 'RecordService',
        order_manager: 'OrderManager' = None,
        pending_orders_getter: Callable[[], Dict[str, Any]] = None
    ):
        """初始化
        
        Args:
            record_service: 记录服务
            order_manager: 订单管理器（用于取消订单）
            pending_orders_getter: 获取待触发开仓条件单的回调函数
        """
        self.record_service = record_service
        self.order_manager = order_manager
        self._pending_orders_getter = pending_orders_getter
        
        self._entry_order_callback: Optional[Callable[[str, Any, str, Dict], None]] = None
    
    def set_entry_order_callback(self, callback: Callable[[str, Any, str, Dict], None]):
        """设置开仓条件单触发的回调
        
        用于 ReverseEngine 处理其自己的开仓条件单。
        
        Args:
            callback: 回调函数 (algo_id, order, status, order_info)
        """
        self._entry_order_callback = callback
    
    def handle(self, data: Dict[str, Any]):
        """处理 ALGO_UPDATE 事件
        
        Args:
            data: 事件数据
        """
        try:
            order_info = data.get('o', {})
            
            status = order_info.get('X', '')
            algo_id = str(order_info.get('aid', ''))
            symbol = order_info.get('s', '')
            
            if not algo_id:
                logger.debug(f"[AlgoOrderHandler] 收到无效的 ALGO_UPDATE 事件: 缺少 algo_id")
                return
            
            logger.debug(f"[AlgoOrderHandler] ALGO_UPDATE: {symbol} status={status} algoId={algo_id}")
            
            if self._pending_orders_getter:
                pending_orders = self._pending_orders_getter()
                if algo_id in pending_orders:
                    if self._entry_order_callback:
                        self._entry_order_callback(algo_id, pending_orders[algo_id], status, order_info)
                    return
            
            tp_record = self.record_service.find_record_by_tp_algo_id(algo_id)
            if tp_record:
                self._handle_tp_order_update(algo_id, tp_record, status, order_info)
                return
            
            tp_record_by_order = self.record_service.find_record_by_tp_order_id(
                int(order_info.get('ai', 0)) if order_info.get('ai') else 0
            )
            if tp_record_by_order:
                self._handle_tp_order_update(algo_id, tp_record_by_order, status, order_info)
                return
            
            sl_record = self.record_service.find_record_by_sl_algo_id(algo_id)
            if sl_record:
                self._handle_sl_order_update(algo_id, sl_record, status, order_info)
                return
            
            logger.debug(f"[AlgoOrderHandler] algoId={algo_id} 不在任何跟踪列表中")
            
        except Exception as e:
            logger.error(f"[AlgoOrderHandler] 处理事件失败: {e}", exc_info=True)
    
    def _extract_order_id(self, order_info: Dict) -> Optional[int]:
        """从 ALGO_UPDATE 事件中提取触发后生成的市价单 ID
        
        Args:
            order_info: ALGO_UPDATE 事件的订单信息
            
        Returns:
            订单ID，如果无法获取则返回 None
        """
        ai = order_info.get('ai', '')
        if ai and ai != '':
            try:
                return int(ai)
            except (ValueError, TypeError):
                pass
        return None
    
    def _handle_tp_order_update(self, algo_id: str, record, status: str, order_info: Dict):
        """处理止盈条件单状态更新
        
        Args:
            algo_id: 条件单ID
            record: 关联的开仓记录
            status: 状态
            order_info: 订单信息
        """
        symbol = record.symbol
        
        if status in ('TRIGGERED', 'FILLED'):
            avg_price = float(order_info.get('ap', 0))
            if avg_price == 0:
                avg_price = record.tp_price or record.entry_price
            
            order_id = self._extract_order_id(order_info)
            logger.info(f"[AlgoOrderHandler] 🎯 {symbol} 止盈触发 @ {avg_price} orderId={order_id}")
            
            self.record_service.cancel_remaining_tpsl(record, 'TP')
            
            self.record_service.close_record(
                record_id=record.id,
                close_price=avg_price,
                close_reason='TP_CLOSED'
            )
        
        elif status == 'CANCELLED':
            logger.info(f"[AlgoOrderHandler] 止盈单已取消: {symbol} algoId={algo_id}")
            self.record_service.update_record_tpsl_ids(record.id, tp_algo_id=None)
        
        elif status == 'EXPIRED':
            logger.info(f"[AlgoOrderHandler] 止盈单已过期: {symbol} algoId={algo_id}")
            self.record_service.update_record_tpsl_ids(record.id, tp_algo_id=None)
        
        elif status == 'REJECTED':
            reason = order_info.get('rm', '')
            logger.warning(f"[AlgoOrderHandler] ⚠️ 止盈单被拒绝: {symbol} algoId={algo_id} reason={reason}")
            self.record_service.update_record_tpsl_ids(record.id, tp_algo_id=None)
    
    def _handle_sl_order_update(self, algo_id: str, record, status: str, order_info: Dict):
        """处理止损条件单状态更新
        
        Args:
            algo_id: 条件单ID
            record: 关联的开仓记录
            status: 状态
            order_info: 订单信息
        """
        symbol = record.symbol
        
        if status in ('TRIGGERED', 'FILLED'):
            avg_price = float(order_info.get('ap', 0))
            if avg_price == 0:
                avg_price = record.sl_price or record.entry_price
            
            order_id = self._extract_order_id(order_info)
            logger.info(f"[AlgoOrderHandler] 🛑 {symbol} 止损触发 @ {avg_price} orderId={order_id}")
            
            self.record_service.cancel_remaining_tpsl(record, 'SL')
            
            self.record_service.close_record(
                record_id=record.id,
                close_price=avg_price,
                close_reason='SL_CLOSED'
            )
        
        elif status == 'CANCELLED':
            logger.info(f"[AlgoOrderHandler] 止损单已取消: {symbol} algoId={algo_id}")
            self.record_service.update_record_tpsl_ids(record.id, sl_algo_id=None)
        
        elif status == 'EXPIRED':
            logger.info(f"[AlgoOrderHandler] 止损单已过期: {symbol} algoId={algo_id}")
            self.record_service.update_record_tpsl_ids(record.id, sl_algo_id=None)
        
        elif status == 'REJECTED':
            reason = order_info.get('rm', '')
            logger.warning(f"[AlgoOrderHandler] ⚠️ 止损单被拒绝: {symbol} algoId={algo_id} reason={reason}")
            self.record_service.update_record_tpsl_ids(record.id, sl_algo_id=None)
