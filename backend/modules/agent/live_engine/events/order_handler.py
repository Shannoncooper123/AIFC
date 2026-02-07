"""ORDER_TRADE_UPDATE 事件处理器

处理 Binance 普通订单的状态变化事件。

职责：
- 监听限价单成交事件
- 当 pending limit order 成交时，创建开仓记录并下 TP/SL 订单
- 处理 TP/SL 订单取消事件

事件流程：
1. 限价单成交 (FILLED) -> 查找 pending_orders -> 创建 TradeRecord -> 下 TP/SL
2. TP/SL 订单取消 -> 清理本地记录
"""
from typing import Dict, Any, Optional, TYPE_CHECKING
from modules.monitor.utils.logger import get_logger

if TYPE_CHECKING:
    from modules.agent.live_engine.core.repositories import OrderRepository
    from ..services.record_service import RecordService

logger = get_logger('live_engine.order_handler')


class OrderUpdateHandler:
    """ORDER_TRADE_UPDATE 事件处理器
    
    职责：
    - 处理限价单成交事件（创建开仓记录、下 TP/SL）
    - 处理订单取消事件（清理本地记录）
    """
    
    def __init__(
        self,
        order_service,
        order_repository: 'OrderRepository' = None,
        record_service: 'RecordService' = None
    ):
        """初始化
        
        Args:
            order_service: 订单服务（用于 TP/SL 订单状态管理）
            order_repository: 订单仓库（用于查找 pending orders）
            record_service: 记录服务（用于创建开仓记录和下 TP/SL）
        """
        self.order_service = order_service
        self.order_repository = order_repository
        self.record_service = record_service
    
    def handle(self, data: Dict[str, Any]):
        """处理 ORDER_TRADE_UPDATE 事件
        
        Args:
            data: 订单更新事件数据
        """
        try:
            order_data = data.get('o', {})
            symbol = order_data.get('s')
            order_status = order_data.get('X')
            order_type = order_data.get('o')
            orig_type = order_data.get('ot')
            order_id = int(order_data.get('i', 0))
            
            if order_status == 'FILLED':
                self._handle_order_filled(order_data)
            
            is_tpsl_order = (
                order_type in ['TAKE_PROFIT_MARKET', 'STOP_MARKET', 'TAKE_PROFIT', 'STOP'] or
                orig_type in ['TAKE_PROFIT_MARKET', 'STOP_MARKET', 'TAKE_PROFIT', 'STOP']
            )
            
            if is_tpsl_order and order_status == 'CANCELED':
                self._handle_tpsl_cancelled(symbol, order_id)
        
        except Exception as e:
            logger.error(f"处理订单更新事件失败: {e}", exc_info=True)
    
    def _handle_order_filled(self, order_data: Dict):
        """处理订单成交事件
        
        检查是否是 pending limit order，如果是则创建开仓记录并下 TP/SL。
        
        Args:
            order_data: 订单数据
        """
        if not self.order_repository or not self.record_service:
            return
        
        order_id = int(order_data.get('i', 0))
        symbol = order_data.get('s', '')
        
        pending_order = self.order_repository.find_by_order_id(order_id)
        if not pending_order:
            return
        
        if pending_order.order_kind != 'LIMIT':
            return
        
        filled_price = float(order_data.get('ap', 0))
        if filled_price == 0:
            filled_price = pending_order.trigger_price
        
        logger.info(f"[OrderHandler] 📦 限价单成交: {symbol} orderId={order_id} price={filled_price}")
        
        entry_commission = 0.0
        if order_id:
            entry_commission = self.record_service.fetch_entry_commission(symbol, order_id)
            if entry_commission > 0:
                logger.info(f"[OrderHandler] 💰 开仓手续费: {entry_commission:.6f} USDT")
        
        self.record_service.create_record(
            symbol=pending_order.symbol,
            side=pending_order.side,
            qty=pending_order.quantity,
            entry_price=filled_price,
            leverage=pending_order.leverage,
            tp_price=pending_order.tp_price,
            sl_price=pending_order.sl_price,
            source=pending_order.source,
            entry_order_id=order_id,
            agent_order_id=pending_order.agent_order_id,
            entry_commission=entry_commission,
            auto_place_tpsl=True
        )
        
        self.order_repository.remove(pending_order.id)
        logger.info(f"[OrderHandler] ✅ 开仓记录已创建，pending order 已移除: {pending_order.id}")
    
    def _handle_tpsl_cancelled(self, symbol: str, order_id: int):
        """处理 TP/SL 订单取消事件
        
        Args:
            symbol: 交易对
            order_id: 订单ID
        """
        if symbol in self.order_service.tpsl_orders:
            orders = self.order_service.tpsl_orders[symbol]
            if orders.get('tp_order_id') == order_id:
                orders['tp_order_id'] = None
            elif orders.get('sl_order_id') == order_id:
                orders['sl_order_id'] = None
            
            if not orders.get('tp_order_id') and not orders.get('sl_order_id'):
                del self.order_service.tpsl_orders[symbol]
                logger.debug(f"{symbol} TP/SL 订单记录已完全清除")
