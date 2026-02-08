"""订单服务：管理市价单、止盈止损单等订单操作

双向持仓模式说明：
- 开多仓：side='BUY', position_side='LONG'
- 开空仓：side='SELL', position_side='SHORT'
- 平多仓：side='SELL', position_side='LONG'
- 平空仓：side='BUY', position_side='SHORT'
"""
from typing import Any, Dict, List, Optional

from modules.agent.live_engine.core.models import OrderType
from modules.monitor.utils.logger import get_logger

logger = get_logger('live_engine.order_service')


def _get_position_side(side: str) -> str:
    """根据持仓方向获取 positionSide 参数

    Args:
        side: 持仓方向（long/short）

    Returns:
        positionSide 参数（LONG/SHORT）
    """
    return 'LONG' if side == 'long' else 'SHORT'


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

            # 2. 下市价单（双向持仓模式）
            order_side = 'BUY' if side == 'long' else 'SELL'
            position_side = _get_position_side(side)

            market_order = self.rest_client.place_order(
                symbol=symbol,
                side=order_side,
                order_type='MARKET',
                quantity=quantity,
                position_side=position_side
            )

            logger.info(f"市价单已下: {symbol} {side} 数量={quantity} positionSide={position_side}")

            # 3. 下 TP/SL 条件单（格式化价格精度）
            tp_order_id = None
            sl_order_id = None

            if tp_price:
                tp_side = 'SELL' if side == 'long' else 'BUY'
                tp_price_formatted = round(tp_price, price_precision)
                tp_order = self.rest_client.place_order(
                    symbol=symbol,
                    side=tp_side,
                    order_type='TAKE_PROFIT_MARKET',
                    stop_price=tp_price_formatted,
                    close_position=True,
                    working_type='MARK_PRICE',
                    position_side=position_side
                )
                tp_order_id = tp_order.get('orderId')
                logger.info(f"止盈单已下: {symbol} 价格={tp_price_formatted} positionSide={position_side}")

            if sl_price:
                sl_side = 'SELL' if side == 'long' else 'BUY'
                sl_price_formatted = round(sl_price, price_precision)
                sl_order = self.rest_client.place_order(
                    symbol=symbol,
                    side=sl_side,
                    order_type=OrderType.STOP_MARKET.value,
                    stop_price=sl_price_formatted,
                    close_position=True,
                    working_type='MARK_PRICE',
                    position_side=position_side
                )
                sl_order_id = sl_order.get('orderId')
                logger.info(f"止损单已下: {symbol} 价格={sl_price_formatted} positionSide={position_side}")

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

            # 2. 下市价平仓单（双向持仓模式）
            close_side = 'SELL' if side == 'long' else 'BUY'
            position_side = _get_position_side(side)

            order = self.rest_client.place_order(
                symbol=symbol,
                side=close_side,
                order_type=OrderType.MARKET.value,
                quantity=quantity,
                reduce_only=True,
                position_side=position_side
            )

            logger.info(f"市价平仓: {symbol} 数量={quantity} 原因={close_reason} positionSide={position_side}")

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

            # 2. 下新的 TP/SL 订单（双向持仓模式）
            tp_order_id = None
            sl_order_id = None
            position_side = _get_position_side(side)

            if tp_price:
                tp_side = 'SELL' if side == 'long' else 'BUY'
                tp_order = self.rest_client.place_order(
                    symbol=symbol,
                    side=tp_side,
                    order_type=OrderType.TAKE_PROFIT_MARKET.value,
                    stop_price=tp_price,
                    close_position=True,
                    working_type='MARK_PRICE',
                    position_side=position_side
                )
                tp_order_id = tp_order.get('orderId')
                logger.info(f"止盈单已更新: {symbol} 价格={tp_price} positionSide={position_side}")

            if sl_price:
                sl_side = 'SELL' if side == 'long' else 'BUY'
                sl_order = self.rest_client.place_order(
                    symbol=symbol,
                    side=sl_side,
                    order_type=OrderType.STOP_MARKET.value,
                    stop_price=sl_price,
                    close_position=True,
                    working_type='MARK_PRICE',
                    position_side=position_side
                )
                sl_order_id = sl_order.get('orderId')
                logger.info(f"止损单已更新: {symbol} 价格={sl_price} positionSide={position_side}")

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

                if order_type in [OrderType.TAKE_PROFIT_MARKET.value, OrderType.STOP_MARKET.value]:
                    if symbol not in symbol_orders:
                        symbol_orders[symbol] = {'tp_orders': [], 'sl_orders': []}

                    if order_type == OrderType.TAKE_PROFIT_MARKET.value:
                        symbol_orders[symbol]['tp_orders'].append({'order_id': order_id, 'order': order})
                    elif order_type == OrderType.STOP_MARKET.value:
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

                tp_order_id = None
                if tp_orders:
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

                sl_order_id = None
                if sl_orders:
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
                logger.info("检测到 TP/SL 订单状态变化")
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
                if order_type in [OrderType.TAKE_PROFIT_MARKET.value, OrderType.STOP_MARKET.value] and symbol not in active_symbols:
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

    def get_tpsl_prices(self, symbol: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """查询当前挂单中的 TP/SL 价格和订单ID

        Args:
            symbol: 指定交易对（可选）。不传则返回所有交易对的映射。

        Returns:
            {symbol: {tp_price, sl_price, tp_order_id, tp_algo_id, sl_algo_id}}
        """
        try:
            open_orders = self.rest_client.get_open_orders(symbol) if symbol else self.rest_client.get_open_orders()
            algo_orders = self.rest_client.get_algo_open_orders(symbol)

            result: Dict[str, Dict[str, Any]] = {}

            for order in open_orders:
                s = order.get('symbol')
                typ = order.get('type')
                order_id = order.get('orderId')
                sp = order.get('stopPrice')
                lp = order.get('price')

                price: Optional[float] = None
                if sp is not None:
                    try:
                        price = float(sp)
                    except Exception:
                        price = None

                if lp is not None and (price is None or price == 0):
                    try:
                        price = float(lp)
                    except Exception:
                        pass

                if s not in result:
                    result[s] = {
                        'tp_price': None, 'sl_price': None,
                        'tp_order_id': None, 'tp_algo_id': None, 'sl_algo_id': None
                    }

                if typ in [OrderType.TAKE_PROFIT_MARKET.value, OrderType.TAKE_PROFIT.value]:
                    result[s]['tp_price'] = price
                    result[s]['tp_order_id'] = order_id
                elif typ in [OrderType.STOP_MARKET.value, OrderType.STOP.value]:
                    result[s]['sl_price'] = price
                elif typ == OrderType.LIMIT.value:
                    result[s]['tp_price'] = price
                    result[s]['tp_order_id'] = order_id

            if algo_orders:
                for algo in algo_orders:
                    s = algo.get('symbol')
                    algo_id = str(algo.get('algoId', ''))
                    algo_type = algo.get('type')
                    sp = algo.get('stopPrice')

                    price: Optional[float] = None
                    if sp is not None:
                        try:
                            price = float(sp)
                        except Exception:
                            price = None

                    if s not in result:
                        result[s] = {
                            'tp_price': None, 'sl_price': None,
                            'tp_order_id': None, 'tp_algo_id': None, 'sl_algo_id': None
                        }

                    if algo_type == OrderType.TAKE_PROFIT_MARKET.value:
                        result[s]['tp_price'] = price
                        result[s]['tp_algo_id'] = algo_id
                    elif algo_type == OrderType.STOP_MARKET.value:
                        result[s]['sl_price'] = price
                        result[s]['sl_algo_id'] = algo_id

            return result
        except Exception as e:
            logger.error(f"获取 TP/SL 订单价格失败: {e}")
            return {}

    def create_smart_limit_order(
        self,
        symbol: str,
        side: str,
        limit_price: float,
        quantity: float,
        tp_price: float,
        sl_price: float,
        source: str = 'live',
        expiration_days: int = 10
    ) -> Dict[str, Any]:
        """智能创建限价单（根据当前价格自动选择限价单或条件单）

        判断逻辑：
        - BUY (做多): 当前价格 > 触发价 → 限价单 (Maker)，否则 → 条件单 (Taker)
        - SELL (做空): 当前价格 < 触发价 → 限价单 (Maker)，否则 → 条件单 (Taker)

        Args:
            symbol: 交易对
            side: 方向 ('BUY'/'SELL' 或 'long'/'short')
            limit_price: 挂单/触发价格
            quantity: 数量
            tp_price: 止盈价格
            sl_price: 止损价格
            source: 订单来源 ('live'/'reverse'/'agent')
            expiration_days: 条件单过期天数

        Returns:
            结果字典，包含订单信息或错误
        """
        from modules.agent.live_engine.core import ExchangeInfoCache

        try:
            side_upper = side.upper()
            if side_upper in ('LONG', 'BUY'):
                order_side = 'BUY'
                position_side = 'LONG'
            else:
                order_side = 'SELL'
                position_side = 'SHORT'

            current_price = self._get_last_price(symbol)
            if not current_price:
                current_price = limit_price

            limit_price = ExchangeInfoCache.format_price(symbol, limit_price)
            tp_price = ExchangeInfoCache.format_price(symbol, tp_price) if tp_price else None
            sl_price = ExchangeInfoCache.format_price(symbol, sl_price) if sl_price else None

            use_limit_order = False
            if order_side == 'BUY' and current_price > limit_price:
                use_limit_order = True
                logger.info(f"[SmartOrder] 当前价格 {current_price} > 触发价 {limit_price}，使用限价单 (Maker)")
            elif order_side == 'SELL' and current_price < limit_price:
                use_limit_order = True
                logger.info(f"[SmartOrder] 当前价格 {current_price} < 触发价 {limit_price}，使用限价单 (Maker)")
            else:
                logger.info("[SmartOrder] 使用条件单 (Taker)")

            if use_limit_order:
                return self._place_limit_entry_order(
                    symbol=symbol,
                    side=order_side,
                    price=limit_price,
                    quantity=quantity,
                    position_side=position_side,
                    tp_price=tp_price,
                    sl_price=sl_price,
                    source=source
                )
            else:
                return self._place_algo_entry_order(
                    symbol=symbol,
                    side=order_side,
                    trigger_price=limit_price,
                    quantity=quantity,
                    position_side=position_side,
                    tp_price=tp_price,
                    sl_price=sl_price,
                    source=source,
                    expiration_days=expiration_days,
                    current_price=current_price
                )

        except Exception as e:
            logger.error(f"[SmartOrder] 创建订单失败: {e}", exc_info=True)
            return {'error': str(e)}

    def _place_limit_entry_order(
        self,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        position_side: str,
        tp_price: float,
        sl_price: float,
        source: str
    ) -> Dict[str, Any]:
        """下限价单（开仓）"""
        try:
            result = self.rest_client.place_order(
                symbol=symbol,
                side=side,
                order_type=OrderType.LIMIT.value,
                quantity=quantity,
                price=price,
                time_in_force='GTC',
                position_side=position_side
            )

            order_id = result.get('orderId')

            logger.info(f"[SmartOrder] ✅ 限价单创建成功: {symbol} {side} @ {price} orderId={order_id}")

            return {
                'success': True,
                'order_id': order_id,
                'order_kind': OrderType.LIMIT.value,
                'symbol': symbol,
                'side': side.lower(),
                'price': price,
                'quantity': quantity,
                'tp_price': tp_price,
                'sl_price': sl_price,
                'source': source,
                'position_side': position_side
            }

        except Exception as e:
            logger.error(f"[SmartOrder] 限价单下单失败: {e}")
            return {'error': str(e)}

    def _place_algo_entry_order(
        self,
        symbol: str,
        side: str,
        trigger_price: float,
        quantity: float,
        position_side: str,
        tp_price: float,
        sl_price: float,
        source: str,
        expiration_days: int,
        current_price: float
    ) -> Dict[str, Any]:
        """下条件单（开仓）
        
        使用 Binance Algo Order API 创建条件单。
        
        Binance 条件单触发规则：
        - STOP_MARKET (BUY): 价格 >= trigger 时触发 → 触发价需在当前价上方
        - STOP_MARKET (SELL): 价格 <= trigger 时触发 → 触发价需在当前价下方
        - TAKE_PROFIT_MARKET (BUY): 价格 <= trigger 时触发 → 触发价需在当前价下方
        - TAKE_PROFIT_MARKET (SELL): 价格 >= trigger 时触发 → 触发价需在当前价上方
        """
        try:
            if side == 'BUY':
                order_type = 'STOP_MARKET' if trigger_price > current_price else 'TAKE_PROFIT_MARKET'
            else:
                order_type = 'STOP_MARKET' if trigger_price < current_price else 'TAKE_PROFIT_MARKET'

            from datetime import datetime, timedelta, timezone
            expire_time = datetime.now(timezone.utc) + timedelta(days=expiration_days)
            good_till_date = int(expire_time.timestamp() * 1000)

            logger.info(f"[SmartOrder] 当前价格: {current_price}, 触发价: {trigger_price}")
            logger.info(f"[SmartOrder] 条件单类型: {order_type} ({side} {position_side})")

            result = self.rest_client.place_algo_order(
                symbol=symbol,
                side=side,
                algo_type='CONDITIONAL',
                trigger_price=trigger_price,
                quantity=quantity,
                order_type='MARKET',
                working_type='CONTRACT_PRICE',
                good_till_date=good_till_date,
                position_side=position_side
            )

            algo_id = str(result.get('algoId'))

            logger.info(f"[SmartOrder] ✅ 条件单创建成功: {symbol} {side} {order_type} @ {trigger_price} algoId={algo_id}")

            return {
                'success': True,
                'algo_id': algo_id,
                'order_kind': 'CONDITIONAL',
                'symbol': symbol,
                'side': side.lower(),
                'trigger_price': trigger_price,
                'quantity': quantity,
                'tp_price': tp_price,
                'sl_price': sl_price,
                'source': source,
                'position_side': position_side,
                'order_type': order_type
            }

        except Exception as e:
            logger.error(f"[SmartOrder] 条件单下单失败: {e}")
            return {'error': str(e)}

    def _get_last_price(self, symbol: str) -> Optional[float]:
        """获取当前最新成交价格

        优先使用 WebSocket API（连接复用，权重低），
        失败时回退到 REST API。
        """
        try:
            from modules.agent.live_engine.core.exchange_utils import get_latest_price
            price = get_latest_price(symbol)
            if price:
                return price
        except Exception as e:
            logger.debug(f"WebSocket API 获取价格失败，回退到 REST: {e}")

        try:
            ticker = self.rest_client.get_ticker_price(symbol)
            if isinstance(ticker, list) and len(ticker) > 0:
                ticker = ticker[0]
            return float(ticker.get('price', 0))
        except Exception as e:
            logger.warning(f"获取 {symbol} 最新价格失败: {e}")
            return None
