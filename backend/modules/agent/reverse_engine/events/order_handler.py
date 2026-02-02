"""反向交易订单事件处理器

职责说明：
- 处理来自 Binance User Data Stream 的订单更新事件
- 监听条件单 (Algo Order) 的状态变化
- 监听 TP/SL 订单的成交事件

工作流程：
1. 条件单触发 -> 创建持仓 -> 下 TP/SL 订单
2. TP/SL 成交 -> 记录历史 -> 移除持仓

事件字段说明（参考币安文档）：
- o.ot: 原始订单类型 (STOP_MARKET, TAKE_PROFIT_MARKET 等)
- o.X: 订单当前状态 (NEW, FILLED, CANCELED, EXPIRED 等)
- o.x: 本次事件执行类型 (NEW, TRADE, CANCELED 等)
- o.i: 订单ID
- o.s: 交易对
- o.ap: 订单平均价格
- o.L: 订单末次成交价格
"""

from typing import Dict, Any, Optional
from modules.monitor.utils.logger import get_logger
from ..services.algo_order_service import AlgoOrderService
from ..services.position_service import ReversePositionService
from ..services.history_writer import ReverseHistoryWriter
from ..models import AlgoOrderStatus

logger = get_logger('reverse_engine.order_handler')


class ReverseOrderHandler:
    """反向交易订单事件处理器
    
    职责：
    - 处理条件单 (STOP_MARKET) 状态变化
    - 处理 TP/SL 订单成交事件
    - 协调 AlgoOrderService、PositionService、HistoryWriter
    
    事件类型：
    - ORDER_TRADE_UPDATE: 订单状态更新
    - ACCOUNT_UPDATE: 账户状态更新（用于检测持仓变化）
    """
    
    def __init__(self, algo_order_service: AlgoOrderService,
                 position_service: ReversePositionService,
                 history_writer: ReverseHistoryWriter):
        """初始化
        
        Args:
            algo_order_service: 条件单服务
            position_service: 持仓服务
            history_writer: 历史记录写入器
        """
        self.algo_order_service = algo_order_service
        self.position_service = position_service
        self.history_writer = history_writer
    
    def handle_event(self, event_type: str, data: Dict[str, Any]):
        """处理事件
        
        Args:
            event_type: 事件类型
            data: 事件数据
        """
        try:
            if event_type == 'ORDER_TRADE_UPDATE':
                self._handle_order_update(data)
            elif event_type == 'ACCOUNT_UPDATE':
                self._handle_account_update(data)
        except Exception as e:
            logger.error(f"[反向] 处理事件失败: {e}", exc_info=True)
    
    def _handle_order_update(self, data: Dict[str, Any]):
        """处理订单更新事件
        
        Args:
            data: 订单更新数据
        """
        order_info = data.get('o', {})
        
        order_type = order_info.get('ot', '')  # 原始订单类型
        order_status = order_info.get('X', '')  # 订单当前状态
        execution_type = order_info.get('x', '')  # 本次事件执行类型
        symbol = order_info.get('s', '')
        order_id = str(order_info.get('i', ''))
        
        # 打印所有订单更新事件，便于调试
        logger.info(f"[反向] 📥 ORDER_TRADE_UPDATE: {symbol} | type={order_type} | status={order_status} | exec={execution_type} | orderId={order_id}")
        
        # 检查是否是我们的条件单（通过 order_id 匹配 algo_id）
        # 注意：条件单触发后，会生成一个新的订单，但我们通过 algo_id 跟踪
        # 币安的条件单 WebSocket 事件中，订单ID 就是 algoId
        algo_order = self.algo_order_service.get_order(order_id)
        
        # 打印当前跟踪的条件单列表，便于调试
        pending_algo_ids = list(self.algo_order_service.pending_orders.keys())
        if pending_algo_ids:
            logger.debug(f"[反向] 当前跟踪的条件单: {pending_algo_ids}")
        
        if algo_order:
            # 这是我们的条件单
            self._handle_algo_order_update(order_info, algo_order)
        elif order_type in ['TAKE_PROFIT_MARKET', 'STOP_MARKET']:
            # 可能是我们的 TP/SL 订单
            if order_status == 'FILLED':
                self._handle_tpsl_filled(order_info)
    
    def _handle_algo_order_update(self, order_info: Dict[str, Any], algo_order):
        """处理条件单更新
        
        Args:
            order_info: 订单信息
            algo_order: 条件单对象
        """
        status = order_info.get('X', '')
        symbol = order_info.get('s', '')
        algo_id = algo_order.algo_id
        
        if status == 'FILLED':
            # 条件单已成交
            avg_price = float(order_info.get('ap', 0))
            if avg_price == 0:
                avg_price = float(order_info.get('L', 0))  # 末次成交价格
            if avg_price == 0:
                avg_price = algo_order.trigger_price  # 使用触发价作为兜底
            
            logger.info(f"[反向] 条件单已成交: {symbol} algoId={algo_id} price={avg_price}")
            
            self.algo_order_service.mark_order_triggered(algo_id, avg_price)
            
            position = self.position_service.create_position_from_algo_order(algo_order, avg_price)
            
            if position:
                logger.info(f"[反向] 持仓已创建: {symbol} {position.side} @ {avg_price}")
                logger.info(f"[反向] TP={position.tp_price} SL={position.sl_price}")
            
            self.algo_order_service.remove_order(algo_id)
        
        elif status == 'EXPIRED':
            logger.info(f"[反向] 条件单已过期: {symbol} algoId={algo_id}")
            self.algo_order_service.remove_order(algo_id)
        
        elif status == 'CANCELED':
            logger.info(f"[反向] 条件单已取消: {symbol} algoId={algo_id}")
            self.algo_order_service.remove_order(algo_id)
        
        elif status == 'NEW':
            logger.info(f"[反向] 条件单状态更新: {symbol} algoId={algo_id} status={status}")
    
    def _handle_tpsl_filled(self, order_info: Dict[str, Any]):
        """处理 TP/SL 成交（平仓）
        
        Args:
            order_info: 订单信息
        """
        symbol = order_info.get('s', '')
        order_type = order_info.get('ot', '')
        avg_price = float(order_info.get('ap', 0)) or float(order_info.get('L', 0))
        order_id = order_info.get('i')
        
        position = self.position_service.get_position(symbol)
        if not position:
            logger.debug(f"[反向] {symbol} TP/SL 成交但无对应持仓，可能不是反向交易")
            return
        
        tpsl_orders = self.position_service.tpsl_orders.get(symbol, {})
        tp_order_id = tpsl_orders.get('tp_order_id')
        sl_order_id = tpsl_orders.get('sl_order_id')
        
        is_our_order = (order_id == tp_order_id or order_id == sl_order_id)
        if not is_our_order:
            logger.debug(f"[反向] {symbol} TP/SL 订单 {order_id} 不是反向交易的订单")
            return
        
        if order_type == 'TAKE_PROFIT_MARKET':
            close_reason = '止盈'
            if order_id == tp_order_id and sl_order_id:
                self._cancel_order_safe(symbol, sl_order_id)
        else:
            close_reason = '止损'
            if order_id == sl_order_id and tp_order_id:
                self._cancel_order_safe(symbol, tp_order_id)
        
        logger.info(f"[反向] {symbol} 平仓: {close_reason} price={avg_price}")
        
        self.history_writer.record_closed_position(
            position=position,
            close_reason=close_reason,
            close_price=avg_price,
            close_order_id=order_id
        )
        
        self.position_service.remove_position(symbol)
    
    def _cancel_order_safe(self, symbol: str, order_id: int):
        """安全撤销订单
        
        Args:
            symbol: 交易对
            order_id: 订单ID
        """
        try:
            self.position_service.rest_client.cancel_order(symbol, order_id=order_id)
            logger.info(f"[反向] {symbol} 对立订单已撤销: orderId={order_id}")
        except Exception as e:
            logger.warning(f"[反向] {symbol} 撤销对立订单失败: {e}")
    
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
            
            if symbol in self.position_service.positions:
                if position_amt == 0:
                    logger.info(f"[反向] {symbol} 持仓已被平仓（账户更新检测）")
                else:
                    self.position_service.update_mark_price(symbol, mark_price)
