"""ORDER_TRADE_UPDATE 事件处理器"""
from typing import Dict, Any
from monitor_module.utils.logger import get_logger

logger = get_logger('live_engine.order_handler')


class OrderUpdateHandler:
    """ORDER_TRADE_UPDATE 事件处理器
    
    职责：
    - 处理订单取消事件
    - 清理本地订单记录
    """
    
    def __init__(self, order_service):
        """初始化
        
        Args:
            order_service: 订单服务
        """
        self.order_service = order_service
    
    def handle(self, data: Dict[str, Any]):
        """处理 ORDER_TRADE_UPDATE 事件
        
        主要用于处理订单取消事件，清理本地订单记录。
        平仓记录由 ACCOUNT_UPDATE 触发的 API 查询来处理。
        
        Args:
            data: 订单更新事件数据
        """
        try:
            order_data = data.get('o', {})
            symbol = order_data.get('s')
            order_status = order_data.get('X')  # 订单状态
            order_type = order_data.get('o')  # 当前订单类型
            orig_type = order_data.get('ot')  # 原始订单类型
            order_id = int(order_data.get('i', 0))  # 订单ID
            
            # TP/SL 订单被取消（如更新止盈止损时）
            is_tpsl_order = (
                order_type in ['TAKE_PROFIT_MARKET', 'STOP_MARKET'] or
                orig_type in ['TAKE_PROFIT_MARKET', 'STOP_MARKET']
            )
            
            if is_tpsl_order and order_status == 'CANCELED':
                # 订单被取消（如手动撤销或更新TP/SL时）
                if symbol in self.order_service.tpsl_orders:
                    orders = self.order_service.tpsl_orders[symbol]
                    # 移除已取消的订单ID
                    if orders.get('tp_order_id') == order_id:
                        orders['tp_order_id'] = None
                    elif orders.get('sl_order_id') == order_id:
                        orders['sl_order_id'] = None
                    
                    # 如果两个订单都已清空，删除该 symbol 的记录
                    if not orders.get('tp_order_id') and not orders.get('sl_order_id'):
                        del self.order_service.tpsl_orders[symbol]
                        logger.debug(f"{symbol} TP/SL 订单记录已完全清除")
        
        except Exception as e:
            logger.error(f"处理订单更新事件失败: {e}")

