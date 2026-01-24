"""订单服务：管理市价单、止盈止损单等订单操作"""
from typing import Dict, Optional, Any, List
from modules.monitor.utils.logger import get_logger

logger = get_logger('live_engine.order_service')


class OrderService:
    """订单服务"""
    
    def __init__(self, rest_client, config: Dict):
        """初始化
        
        Args:
            rest_client: REST API 客户端
            config: 配置字典
        """
        self.rest_client = rest_client
        self.config = config
        
        # 订单跟踪：{symbol: {tp_order_id, sl_order_id}}
        self.tpsl_orders: Dict[str, Dict[str, Optional[int]]] = {}
        
        # 尝试从 trade_state.json 恢复订单ID记录
        self._restore_tpsl_from_state()
    
    def open_position_with_tpsl(self, symbol: str, side: str, quantity: float,
                                 leverage: int, tp_price: Optional[float] = None,
                                 sl_price: Optional[float] = None) -> Dict[str, Any]:
        """开仓并设置TP/SL
        
        Args:
            symbol: 交易对
            side: 方向（long/short）
            quantity: 数量
            leverage: 杠杆
            tp_price: 止盈价
            sl_price: 止损价
            
        Returns:
            结果字典
        """
        try:
            # 0. 获取价格精度
            price_precision = self._get_price_precision(symbol)
            
            # 1. 设置杠杆
            try:
                self.rest_client.set_leverage(symbol, leverage)
                logger.info(f"{symbol} 杠杆已设置为 {leverage}x")
            except Exception as e:
                logger.warning(f"设置杠杆失败（可能已设置）: {e}")
            
            # 2. 下市价单
            order_side = 'BUY' if side == 'long' else 'SELL'
            market_order = self.rest_client.place_order(
                symbol=symbol,
                side=order_side,
                order_type='MARKET',
                quantity=quantity
            )
            
            logger.info(f"市价单已下: {symbol} {side} 数量={quantity}")
            
            # 3. 下 TP/SL 条件单（格式化价格精度）
            tp_order_id = None
            sl_order_id = None
            
            if tp_price:
                tp_side = 'SELL' if side == 'long' else 'BUY'
                # 格式化价格精度
                tp_price_formatted = round(tp_price, price_precision)
                tp_order = self.rest_client.place_order(
                    symbol=symbol,
                    side=tp_side,
                    order_type='TAKE_PROFIT_MARKET',
                    stop_price=tp_price_formatted,
                    close_position=True,
                    working_type='MARK_PRICE'
                )
                tp_order_id = tp_order.get('orderId')
                logger.info(f"止盈单已下: {symbol} 价格={tp_price_formatted}")
            
            if sl_price:
                sl_side = 'SELL' if side == 'long' else 'BUY'
                # 格式化价格精度
                sl_price_formatted = round(sl_price, price_precision)
                sl_order = self.rest_client.place_order(
                    symbol=symbol,
                    side=sl_side,
                    order_type='STOP_MARKET',
                    stop_price=sl_price_formatted,
                    close_position=True,
                    working_type='MARK_PRICE'
                )
                sl_order_id = sl_order.get('orderId')
                logger.info(f"止损单已下: {symbol} 价格={sl_price_formatted}")
            
            # 记录订单ID
            self.tpsl_orders[symbol] = {
                'tp_order_id': tp_order_id,
                'sl_order_id': sl_order_id
            }
            
            return {
                'success': True,
                'market_order': market_order,
                'tp_order_id': tp_order_id,
                'sl_order_id': sl_order_id
            }
        
        except Exception as e:
            logger.error(f"开仓失败: {e}")
            return {'error': str(e)}
    
    def close_position_market(self, symbol: str, side: str, quantity: float, 
                              position_obj=None, close_reason: str = 'Agent主动平仓') -> Dict[str, Any]:
        """市价平仓
        
        Args:
            symbol: 交易对
            side: 原持仓方向（long/short）
            quantity: 数量
            position_obj: Position对象（用于记录历史）
            close_reason: 平仓原因
            
        Returns:
            结果字典
        """
        try:
            # 1. 撤销 TP/SL 订单
            self._cancel_tpsl_orders(symbol)
            
            # 2. 下市价平仓单
            close_side = 'SELL' if side == 'long' else 'BUY'
            order = self.rest_client.place_order(
                symbol=symbol,
                side=close_side,
                order_type='MARKET',
                quantity=quantity,
                reduce_only=True
            )
            
            logger.info(f"市价平仓: {symbol} 数量={quantity} 原因={close_reason}")
            
            return {'success': True, 'order': order, 'close_reason': close_reason}
        
        except Exception as e:
            logger.error(f"平仓失败: {e}")
            return {'error': str(e)}
    
    def update_tpsl(self, symbol: str, tp_price: Optional[float] = None,
                    sl_price: Optional[float] = None, side: str = 'long') -> Dict[str, Any]:
        """更新止盈止损
        
        Args:
            symbol: 交易对
            tp_price: 新止盈价
            sl_price: 新止损价
            side: 持仓方向
            
        Returns:
            结果字典
        """
        try:
            # 1. 撤销旧的 TP/SL 订单
            self._cancel_tpsl_orders(symbol)
            
            # 2. 下新的 TP/SL 订单
            tp_order_id = None
            sl_order_id = None
            
            if tp_price:
                tp_side = 'SELL' if side == 'long' else 'BUY'
                tp_order = self.rest_client.place_order(
                    symbol=symbol,
                    side=tp_side,
                    order_type='TAKE_PROFIT_MARKET',
                    stop_price=tp_price,
                    close_position=True,
                    working_type='MARK_PRICE'
                )
                tp_order_id = tp_order.get('orderId')
                logger.info(f"止盈单已更新: {symbol} 价格={tp_price}")
            
            if sl_price:
                sl_side = 'SELL' if side == 'long' else 'BUY'
                sl_order = self.rest_client.place_order(
                    symbol=symbol,
                    side=sl_side,
                    order_type='STOP_MARKET',
                    stop_price=sl_price,
                    close_position=True,
                    working_type='MARK_PRICE'
                )
                sl_order_id = sl_order.get('orderId')
                logger.info(f"止损单已更新: {symbol} 价格={sl_price}")
            
            # 更新订单ID
            self.tpsl_orders[symbol] = {
                'tp_order_id': tp_order_id,
                'sl_order_id': sl_order_id
            }
            
            return {'success': True, 'tp_order_id': tp_order_id, 'sl_order_id': sl_order_id}
        
        except Exception as e:
            logger.error(f"更新TP/SL失败: {e}")
            return {'error': str(e)}
    
    def _restore_tpsl_from_state(self):
        """从 trade_state.json 恢复订单ID记录（启动时调用）"""
        try:
            import json
            import os
            
            state_path = self.config.get('agent', {}).get('trade_state_path', 'agent/trade_state.json')
            if not os.path.exists(state_path):
                logger.info("trade_state.json 不存在，跳过恢复订单ID")
                return
            
            with open(state_path, 'r', encoding='utf-8') as f:
                state_data = json.load(f)
            
            positions = state_data.get('positions', {})
            restored_count = 0
            
            for symbol, pos_data in positions.items():
                tp_id = pos_data.get('tp_order_id')
                sl_id = pos_data.get('sl_order_id')
                
                if tp_id or sl_id:
                    self.tpsl_orders[symbol] = {
                        'tp_order_id': tp_id,
                        'sl_order_id': sl_id
                    }
                    restored_count += 1
                    logger.info(f"恢复订单ID记录: {symbol} tp={tp_id}, sl={sl_id}")
            
            if restored_count > 0:
                logger.info(f"✓ 从 trade_state.json 恢复了 {restored_count} 个币种的订单ID记录")
            else:
                logger.info("trade_state.json 中无订单ID记录")
        
        except Exception as e:
            logger.warning(f"从 trade_state.json 恢复订单ID失败（将从API同步）: {e}")
    
    def _cancel_tpsl_orders(self, symbol: str):
        """撤销指定币种的TP/SL订单
        
        Args:
            symbol: 交易对
        """
        if symbol not in self.tpsl_orders:
            return
        
        orders = self.tpsl_orders[symbol]
        
        # 撤销止盈单
        if orders.get('tp_order_id'):
            try:
                self.rest_client.cancel_order(symbol, order_id=orders['tp_order_id'])
                logger.info(f"已撤销止盈单: {symbol}")
            except Exception as e:
                logger.warning(f"撤销止盈单失败: {e}")
        
        # 撤销止损单
        if orders.get('sl_order_id'):
            try:
                self.rest_client.cancel_order(symbol, order_id=orders['sl_order_id'])
                logger.info(f"已撤销止损单: {symbol}")
            except Exception as e:
                logger.warning(f"撤销止损单失败: {e}")
        
        # 清除记录
        if symbol in self.tpsl_orders:
            self.tpsl_orders.pop(symbol, None)
        
    def sync_tpsl_orders(self):
        """同步 TP/SL 订单状态（从API查询）并清理多余订单"""
        try:
            open_orders = self.rest_client.get_open_orders()
            
            # 收集每个币种的所有 TP/SL 订单（可能有多个）
            symbol_orders: Dict[str, Dict[str, List[Dict]]] = {}
            for order in open_orders:
                symbol = order['symbol']
                order_type = order['type']
                order_id = order['orderId']
                
                if order_type in ['TAKE_PROFIT_MARKET', 'STOP_MARKET']:
                    if symbol not in symbol_orders:
                        symbol_orders[symbol] = {'tp_orders': [], 'sl_orders': []}
                    
                    if order_type == 'TAKE_PROFIT_MARKET':
                        symbol_orders[symbol]['tp_orders'].append({'order_id': order_id, 'order': order})
                    elif order_type == 'STOP_MARKET':
                        symbol_orders[symbol]['sl_orders'].append({'order_id': order_id, 'order': order})
            
            # 清理多余订单：优先保留本地记录的订单ID，其他的全部撤销
            new_tpsl = {}
            canceled_count = 0
            
            for symbol, orders_dict in symbol_orders.items():
                tp_orders = orders_dict['tp_orders']
                sl_orders = orders_dict['sl_orders']
                
                # 获取本地记录的订单ID（如果有）
                local_record = self.tpsl_orders.get(symbol, {})
                local_tp_id = local_record.get('tp_order_id')
                local_sl_id = local_record.get('sl_order_id')
                
                # 处理止盈订单
                tp_order_id = None
                if len(tp_orders) > 0:
                    # 优先：如果本地有记录，且该订单在API返回的列表中，保留它
                    if local_tp_id:
                        tp_ids = [o['order_id'] for o in tp_orders]
                        if local_tp_id in tp_ids:
                            tp_order_id = local_tp_id
                            logger.debug(f"{symbol} 止盈订单: 保留本地记录的 orderId={local_tp_id}")
                        else:
                            logger.warning(f"{symbol} 本地记录的止盈订单 {local_tp_id} 已不存在（可能被触发），从API订单中选择")
                    
                    # 如果本地没有记录，或本地记录的订单已不存在，则按 orderId 最大选择
                    if not tp_order_id:
                        tp_orders_sorted = sorted(tp_orders, key=lambda x: x['order_id'], reverse=True)
                        tp_order_id = tp_orders_sorted[0]['order_id']
                        logger.info(f"{symbol} 止盈订单: 未找到本地记录，选择最新的 orderId={tp_order_id}")
                    
                    # 撤销所有其他止盈订单
                    for order_info in tp_orders:
                        if order_info['order_id'] != tp_order_id:
                            old_id = order_info['order_id']
                            logger.warning(f"发现 {symbol} 多余的止盈订单 {old_id}（保留 {tp_order_id}），撤销")
                            try:
                                self.rest_client.cancel_order(symbol, order_id=old_id)
                                logger.info(f"✓ 已撤销多余止盈订单: {symbol} orderId={old_id}")
                                canceled_count += 1
                            except Exception as e:
                                logger.error(f"✗ 撤销止盈订单失败 {symbol} orderId={old_id}: {e}")
                
                # 处理止损订单
                sl_order_id = None
                if len(sl_orders) > 0:
                    # 优先：如果本地有记录，且该订单在API返回的列表中，保留它
                    if local_sl_id:
                        sl_ids = [o['order_id'] for o in sl_orders]
                        if local_sl_id in sl_ids:
                            sl_order_id = local_sl_id
                            logger.debug(f"{symbol} 止损订单: 保留本地记录的 orderId={local_sl_id}")
                        else:
                            logger.warning(f"{symbol} 本地记录的止损订单 {local_sl_id} 已不存在（可能被触发），从API订单中选择")
                    
                    # 如果本地没有记录，或本地记录的订单已不存在，则按 orderId 最大选择
                    if not sl_order_id:
                        sl_orders_sorted = sorted(sl_orders, key=lambda x: x['order_id'], reverse=True)
                        sl_order_id = sl_orders_sorted[0]['order_id']
                        logger.info(f"{symbol} 止损订单: 未找到本地记录，选择最新的 orderId={sl_order_id}")
                    
                    # 撤销所有其他止损订单
                    for order_info in sl_orders:
                        if order_info['order_id'] != sl_order_id:
                            old_id = order_info['order_id']
                            logger.warning(f"发现 {symbol} 多余的止损订单 {old_id}（保留 {sl_order_id}），撤销")
                            try:
                                self.rest_client.cancel_order(symbol, order_id=old_id)
                                logger.info(f"✓ 已撤销多余止损订单: {symbol} orderId={old_id}")
                                canceled_count += 1
                            except Exception as e:
                                logger.error(f"✗ 撤销止损订单失败 {symbol} orderId={old_id}: {e}")
                
                # 记录最终的订单ID
                new_tpsl[symbol] = {
                    'tp_order_id': tp_order_id,
                    'sl_order_id': sl_order_id
                }
            
            # 记录清理结果
            if canceled_count > 0:
                logger.info(f"🧹 同步订单时清理了 {canceled_count} 个多余的 TP/SL 订单")
            
            # 对比本地和API状态，记录差异
            if self.tpsl_orders != new_tpsl:
                logger.info(f"检测到 TP/SL 订单状态变化")
                # 找出新增的
                for symbol in new_tpsl:
                    if symbol not in self.tpsl_orders:
                        logger.info(f"  新增: {symbol} -> {new_tpsl[symbol]}")
                # 找出删除的
                for symbol in self.tpsl_orders:
                    if symbol not in new_tpsl:
                        logger.info(f"  删除: {symbol}")
            
            self.tpsl_orders = new_tpsl
            logger.info(f"TP/SL 订单状态已同步: {len(new_tpsl)} 个币种")
        
        except Exception as e:
            logger.error(f"同步 TP/SL 订单失败: {e}")
    
    def cancel_single_order(self, symbol: str, order_id: int) -> bool:
        """撤销单个订单（供外部调用）
        
        Args:
            symbol: 交易对
            order_id: 订单ID
            
        Returns:
            是否成功
        """
        try:
            self.rest_client.cancel_order(symbol, order_id=order_id)
            logger.info(f"成功撤销订单: {symbol} orderId={order_id}")
            return True
        except Exception as e:
            logger.warning(f"撤销订单失败 {symbol} orderId={order_id}: {e}")
            return False
    
    def cleanup_orphan_orders(self, active_symbols: set) -> int:
        """清理孤儿订单（有TP/SL订单但无持仓的symbol）
        
        Args:
            active_symbols: 当前有持仓的symbol集合
            
        Returns:
            清理的订单数量
        """
        cleaned_count = 0
        
        # 方法1：清理本地记录中的孤儿订单
        for symbol in list(self.tpsl_orders.keys()):
            if symbol not in active_symbols:
                logger.warning(f"发现孤儿订单（本地记录）: {symbol} 有TP/SL订单但无持仓，自动清理")
                self._cancel_tpsl_orders(symbol)
                cleaned_count += 1
        
        # 方法2：直接从API查询所有挂单，清理无持仓的TP/SL订单（更彻底）
        try:
            all_open_orders = self.rest_client.get_open_orders()
            for order in all_open_orders:
                symbol = order['symbol']
                order_type = order['type']
                order_id = order['orderId']
                
                # 如果是 TP/SL 订单，但该币种没有持仓
                if order_type in ['TAKE_PROFIT_MARKET', 'STOP_MARKET'] and symbol not in active_symbols:
                    logger.warning(f"发现孤儿订单（API查询）: {symbol} {order_type} orderId={order_id}，无持仓，自动撤销")
                    try:
                        self.rest_client.cancel_order(symbol, order_id=order_id)
                        logger.info(f"✓ 已撤销孤儿订单: {symbol} orderId={order_id}")
                        cleaned_count += 1
                    except Exception as e:
                        logger.error(f"✗ 撤销孤儿订单失败 {symbol} orderId={order_id}: {e}")
        except Exception as e:
            logger.error(f"查询API订单失败: {e}")
        
        if cleaned_count > 0:
            logger.info(f"🧹 已清理 {cleaned_count} 个孤儿订单")
        
        return cleaned_count
    
    def validate_tpsl_consistency(self, positions: dict) -> bool:
        """验证 TP/SL 订单与持仓的一致性
        
        Args:
            positions: 持仓字典 {symbol: Position}
            
        Returns:
            是否一致
        """
        inconsistent = False
        
        # 检查：有持仓但没有 TP/SL 订单记录
        for symbol in positions:
            if symbol not in self.tpsl_orders:
                logger.warning(f"⚠️  持仓一致性问题: {symbol} 有持仓但无 TP/SL 订单记录")
                inconsistent = True
        
        # 检查：有 TP/SL 订单但没有持仓
        for symbol in self.tpsl_orders:
            if symbol not in positions:
                logger.warning(f"⚠️  订单一致性问题: {symbol} 有 TP/SL 订单但无持仓")
                inconsistent = True
        
        if not inconsistent:
            logger.debug("TP/SL 订单与持仓状态一致")
        
        return not inconsistent

    def get_tpsl_prices(self, symbol: Optional[str] = None) -> Dict[str, Dict[str, Optional[float]]]:
        """查询当前挂单中的 TP/SL 价格
        
        Args:
            symbol: 指定交易对（可选）。不传则返回所有交易对的映射。
        
        Returns:
            {symbol: {tp_price: float|None, sl_price: float|None}}
        """
        try:
            open_orders = self.rest_client.get_open_orders(symbol) if symbol else self.rest_client.get_open_orders()
            result: Dict[str, Dict[str, Optional[float]]] = {}
            for order in open_orders:
                s = order.get('symbol')
                typ = order.get('type')
                sp = order.get('stopPrice')
                # stopPrice 可能是字符串，尝试转为 float
                price: Optional[float] = None
                if sp is not None:
                    try:
                        price = float(sp)
                    except Exception:
                        price = None
                
                if typ in ['TAKE_PROFIT_MARKET', 'STOP_MARKET']:
                    if s not in result:
                        result[s] = {'tp_price': None, 'sl_price': None}
                    if typ == 'TAKE_PROFIT_MARKET':
                        result[s]['tp_price'] = price
                    elif typ == 'STOP_MARKET':
                        result[s]['sl_price'] = price
            return result
        except Exception as e:
            logger.error(f"获取 TP/SL 订单价格失败: {e}")
            return {}

    def get_tpsl_price_for_symbol(self, symbol: str) -> Dict[str, Optional[float]]:
        """获取指定交易对的 TP/SL 价格（从挂单中）
        
        Returns:
            {tp_price: float|None, sl_price: float|None}
        """
        data = self.get_tpsl_prices(symbol)
        return data.get(symbol, {'tp_price': None, 'sl_price': None})
    
    def _get_price_precision(self, symbol: str) -> int:
        """获取交易对的价格精度
        
        Args:
            symbol: 交易对
            
        Returns:
            价格精度（小数位数）
        """
        try:
            exchange_info = self.rest_client.get_exchange_info()
            for s in exchange_info.get('symbols', []):
                if s['symbol'] == symbol:
                    return s.get('pricePrecision', 2)
            return 2  # 默认精度
        except Exception as e:
            logger.warning(f"获取 {symbol} 价格精度失败，使用默认值2: {e}")
            return 2

