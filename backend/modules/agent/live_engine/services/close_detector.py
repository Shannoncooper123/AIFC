"""平仓检测服务：检测持仓平仓并记录历史"""
from typing import Any, Optional
from modules.monitor.utils.logger import get_logger

logger = get_logger('live_engine.close_detector')


class CloseDetectorService:
    """平仓检测服务
    
    职责：
    - 通过查询 API 检测持仓平仓
    - 判断平仓原因（止盈/止损/手动）
    - 记录平仓历史
    - 撤销对立方向的订单（止盈触发→撤止损，止损触发→撤止盈）
    """
    
    def __init__(self, rest_client, order_service, history_writer):
        """初始化
        
        Args:
            rest_client: REST API 客户端
            order_service: 订单服务
            history_writer: 历史记录写入器
        """
        self.rest_client = rest_client
        self.order_service = order_service
        self.history_writer = history_writer
    
    def _cancel_opposite_order(self, symbol: str, triggered_type: str):
        """撤销对立方向的订单
        
        当止盈或止损触发后，另一方向的订单已无意义，应立即撤销避免成为孤儿订单。
        
        Args:
            symbol: 交易对
            triggered_type: 触发类型（'止盈' or '止损'）
        """
        try:
            orders = self.order_service.tpsl_orders.get(symbol, {})
            
            if triggered_type == "止盈":
                # 止盈触发，撤销止损订单
                sl_order_id = orders.get('sl_order_id')
                if sl_order_id:
                    logger.info(f"🎯 {symbol} 止盈触发，主动撤销止损订单 orderId={sl_order_id}")
                    success = self.order_service.cancel_single_order(symbol, sl_order_id)
                    if success:
                        logger.info(f"✓ {symbol} 止损订单已撤销")
                    else:
                        logger.warning(f"✗ {symbol} 止损订单撤销失败（可能已自动撤销）")
                else:
                    logger.debug(f"{symbol} 止盈触发，但未找到止损订单记录")
            
            elif triggered_type == "止损":
                # 止损触发，撤销止盈订单
                tp_order_id = orders.get('tp_order_id')
                if tp_order_id:
                    logger.info(f"🎯 {symbol} 止损触发，主动撤销止盈订单 orderId={tp_order_id}")
                    success = self.order_service.cancel_single_order(symbol, tp_order_id)
                    if success:
                        logger.info(f"✓ {symbol} 止盈订单已撤销")
                    else:
                        logger.warning(f"✗ {symbol} 止盈订单撤销失败（可能已自动撤销）")
                else:
                    logger.debug(f"{symbol} 止损触发，但未找到止盈订单记录")
        
        except Exception as e:
            logger.error(f"{symbol} 撤销对立订单失败: {e}")
            # 不抛出异常，避免影响历史记录
    
    def detect_and_record_close(self, symbol: str, position: Any):
        """检测平仓并记录历史
        
        当检测到持仓被平掉时，主动查询订单状态来确定平仓原因和价格。
        
        Args:
            symbol: 交易对
            position: Position 对象
        """
        try:
            orders = self.order_service.tpsl_orders.get(symbol, {})
            tp_order_id = orders.get('tp_order_id')
            sl_order_id = orders.get('sl_order_id')
            
            if not tp_order_id and not sl_order_id:
                logger.warning(f"{symbol} 平仓但未找到 TP/SL 订单ID")
                return
            
            close_order_id = None
            close_reason = "unknown"
            close_price = position.latest_mark_price or position.entry_price
            
            # 查询止盈订单状态
            if tp_order_id:
                try:
                    tp_order = self.rest_client.get_order(symbol, order_id=tp_order_id)
                    if tp_order.get('status') == 'FILLED':
                        close_order_id = tp_order_id
                        close_reason = "止盈"
                        close_price = float(tp_order.get('avgPrice', close_price))
                        logger.info(f"{symbol} 止盈触发，订单ID={close_order_id}, 价格={close_price}")
                        
                        # 🆕 立即撤销止损订单
                        self._cancel_opposite_order(symbol, "止盈")
                except Exception as e:
                    logger.warning(f"{symbol} 查询止盈订单失败: {e}")
            
            # 如果止盈未触发，查询止损订单
            if close_reason == "unknown" and sl_order_id:
                try:
                    sl_order = self.rest_client.get_order(symbol, order_id=sl_order_id)
                    if sl_order.get('status') == 'FILLED':
                        close_order_id = sl_order_id
                        close_reason = "止损"
                        close_price = float(sl_order.get('avgPrice', close_price))
                        logger.info(f"{symbol} 止损触发，订单ID={close_order_id}, 价格={close_price}")
                        
                        # 🆕 立即撤销止盈订单
                        self._cancel_opposite_order(symbol, "止损")
                except Exception as e:
                    logger.warning(f"{symbol} 查询止损订单失败: {e}")
            
            # 记录历史
            self.history_writer.record_closed_position(
                position,
                close_reason=close_reason,
                close_price=close_price,
                close_order_id=close_order_id
            )
            
            logger.info(f"{symbol} 平仓记录已保存: 原因={close_reason}, 价格={close_price}")
        
        except Exception as e:
            logger.error(f"{symbol} 检测平仓失败: {e}", exc_info=True)

