"""订单执行器：纯订单操作

职责：
- 执行下单操作（市价单、限价单、条件单）
- 执行撤单操作
- 确保持仓模式和杠杆设置

不包含业务逻辑，只负责与交易所 API 交互。
"""
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from modules.agent.live_engine.core import ExchangeInfoCache
from modules.agent.live_engine.core.models import OrderType
from modules.monitor.utils.logger import get_logger

if TYPE_CHECKING:
    from modules.agent.live_engine.services.price_service import PriceService
    from modules.monitor.clients.binance_rest import BinanceRestClient

logger = get_logger('live_engine.order_executor')


def get_position_side(side: str) -> str:
    """根据交易方向获取 positionSide 参数

    Args:
        side: 交易方向（long/short 或 BUY/SELL）

    Returns:
        positionSide 参数（LONG/SHORT）
    """
    side_upper = side.upper()
    if side_upper in ('LONG', 'BUY'):
        return 'LONG'
    return 'SHORT'


def get_close_side(position_side: str) -> str:
    """获取平仓方向

    Args:
        position_side: 持仓方向（LONG/SHORT）

    Returns:
        平仓方向（BUY/SELL）
    """
    return 'SELL' if position_side == 'LONG' else 'BUY'


class OrderExecutor:
    """订单执行器

    纯粹的订单执行，不包含业务逻辑。
    """

    def __init__(
        self,
        rest_client: 'BinanceRestClient',
        price_service: 'PriceService'
    ):
        """初始化

        Args:
            rest_client: Binance REST 客户端
            price_service: 价格服务
        """
        self.rest_client = rest_client
        self.price_service = price_service

        self._dual_mode_checked = False
        self._symbol_leverage_set: set = set()

    def ensure_dual_position_mode(self) -> bool:
        """确保账户为双向持仓模式"""
        if self._dual_mode_checked:
            return True

        try:
            mode_info = self.rest_client.get_position_mode()
            is_dual = mode_info.get('dualSidePosition', False)

            if not is_dual:
                logger.info("[OrderExecutor] 当前为单向持仓模式，尝试切换为双向持仓模式...")
                try:
                    self.rest_client.change_position_mode(dual_side_position=True)
                    logger.info("[OrderExecutor] 已成功切换为双向持仓模式")
                except Exception as e:
                    error_msg = str(e)
                    if 'No need to change position side' in error_msg or '-4059' in error_msg:
                        logger.info("[OrderExecutor] 已经是双向持仓模式，无需切换")
                    elif 'position or open order' in error_msg.lower() or '-4068' in error_msg:
                        logger.warning("[OrderExecutor] 无法切换持仓模式：存在持仓或挂单")
                        return False
                    else:
                        logger.error(f"[OrderExecutor] 切换持仓模式失败: {e}")
                        return False
            else:
                logger.debug("[OrderExecutor] 已确认为双向持仓模式")

            self._dual_mode_checked = True
            return True

        except Exception as e:
            logger.error(f"[OrderExecutor] 检查持仓模式失败: {e}")
            return False

    def ensure_leverage(self, symbol: str, leverage: int) -> bool:
        """确保指定币种的杠杆已设置"""
        cache_key = f"{symbol}_{leverage}"
        if cache_key in self._symbol_leverage_set:
            return True

        try:
            self.rest_client.set_leverage(symbol, leverage)
            logger.info(f"[OrderExecutor] {symbol} 杠杆已设置为 {leverage}x")
            self._symbol_leverage_set.add(cache_key)
            return True
        except Exception as e:
            error_msg = str(e)
            if 'No need to change leverage' in error_msg or '-4028' in error_msg:
                logger.debug(f"[OrderExecutor] {symbol} 杠杆已经是 {leverage}x")
                self._symbol_leverage_set.add(cache_key)
                return True
            else:
                logger.warning(f"[OrderExecutor] 设置 {symbol} 杠杆失败: {e}")
                return False

    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        position_side: Optional[str] = None
    ) -> Dict[str, Any]:
        """下市价单"""
        try:
            qty = ExchangeInfoCache.format_quantity(symbol, quantity)
            pos_side = position_side or get_position_side(side)

            params = {
                'symbol': symbol,
                'side': side.upper(),
                'order_type': OrderType.MARKET.value,
                'quantity': qty,
                'position_side': pos_side
            }

            result = self.rest_client.place_order(**params)

            logger.info(f"[OrderExecutor] 市价单成功: {symbol} {side} qty={qty} positionSide={pos_side}")
            return {'success': True, 'order': result, 'order_id': result.get('orderId')}

        except Exception as e:
            logger.error(f"[OrderExecutor] 市价单失败: {symbol} {side} error={e}")
            return {'success': False, 'error': str(e)}

    def place_limit_order(
        self,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        position_side: Optional[str] = None,
        time_in_force: str = 'GTC'
    ) -> Dict[str, Any]:
        """下限价单（Maker 低手续费）"""
        try:
            formatted_price = ExchangeInfoCache.format_price(symbol, price)
            qty = ExchangeInfoCache.format_quantity(symbol, quantity)
            pos_side = position_side or get_position_side(side)

            params = {
                'symbol': symbol,
                'side': side.upper(),
                'order_type': OrderType.LIMIT.value,
                'quantity': qty,
                'price': formatted_price,
                'time_in_force': time_in_force,
                'position_side': pos_side
            }

            result = self.rest_client.place_order(**params)
            order_id = result.get('orderId')

            logger.info(f"[OrderExecutor] 限价单成功: {symbol} {side} price={formatted_price} "
                       f"qty={qty} orderId={order_id} (Maker)")
            return {'success': True, 'order': result, 'order_id': order_id}

        except Exception as e:
            logger.error(f"[OrderExecutor] 限价单失败: {symbol} {side} price={price} error={e}")
            return {'success': False, 'error': str(e)}

    def place_algo_order(
        self,
        symbol: str,
        side: str,
        trigger_price: float,
        quantity: float,
        order_type: str = 'STOP_MARKET',
        position_side: Optional[str] = None,
        working_type: str = 'CONTRACT_PRICE',
        expiration_days: int = 7
    ) -> Dict[str, Any]:
        """下策略条件单 (Algo Order)"""
        try:
            formatted_price = ExchangeInfoCache.format_price(symbol, trigger_price)
            qty = ExchangeInfoCache.format_quantity(symbol, quantity)
            pos_side = position_side or get_position_side(side)

            expiration_ms = int((datetime.now(timezone.utc) + timedelta(days=expiration_days)).timestamp() * 1000)

            result = self.rest_client.place_algo_order(
                symbol=symbol,
                side=side.upper(),
                algo_type='CONDITIONAL',
                trigger_price=formatted_price,
                quantity=qty,
                order_type=order_type,
                working_type=working_type,
                good_till_date=expiration_ms,
                position_side=pos_side
            )

            algo_id = str(result.get('algoId', ''))

            logger.info(f"[OrderExecutor] 策略单成功: {symbol} {side} trigger={formatted_price} "
                       f"algoId={algo_id} type={order_type}")
            return {'success': True, 'result': result, 'algo_id': algo_id}

        except Exception as e:
            logger.error(f"[OrderExecutor] 策略单失败: {symbol} trigger={trigger_price} error={e}")
            return {'success': False, 'error': str(e)}

    def cancel_order(self, symbol: str, order_id: int) -> bool:
        """撤销普通订单"""
        try:
            self.rest_client.cancel_order(symbol=symbol, order_id=order_id)
            logger.info(f"[OrderExecutor] 订单已撤销: {symbol} orderId={order_id}")
            return True
        except Exception as e:
            logger.warning(f"[OrderExecutor] 撤销订单失败: {symbol} orderId={order_id} error={e}")
            return False

    def cancel_algo_order(self, symbol: str, algo_id: str) -> bool:
        """撤销策略条件单"""
        try:
            self.rest_client.cancel_algo_order(symbol, algo_id)
            logger.info(f"[OrderExecutor] 策略单已撤销: {symbol} algoId={algo_id}")
            return True
        except Exception as e:
            logger.warning(f"[OrderExecutor] 撤销策略单失败: {symbol} algoId={algo_id} error={e}")
            return False

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """获取未成交订单"""
        try:
            if symbol:
                return self.rest_client.get_open_orders(symbol)
            return self.rest_client.get_open_orders()
        except Exception as e:
            logger.error(f"[OrderExecutor] 获取订单失败: {e}")
            return []

    def get_algo_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """获取未触发的策略条件单"""
        try:
            result = self.rest_client.get_algo_open_orders(symbol)
            return result if result else []
        except Exception as e:
            logger.error(f"[OrderExecutor] 获取策略单失败: {e}")
            return []

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
        """
        try:
            side_upper = side.upper()
            if side_upper in ('LONG', 'BUY'):
                order_side = 'BUY'
                position_side = 'LONG'
            else:
                order_side = 'SELL'
                position_side = 'SHORT'

            current_price = self.price_service.get_last_price(symbol)
            if not current_price:
                current_price = limit_price

            formatted_limit_price = ExchangeInfoCache.format_price(symbol, limit_price)
            formatted_quantity = ExchangeInfoCache.format_quantity(symbol, quantity)
            formatted_tp_price = ExchangeInfoCache.format_price(symbol, tp_price) if tp_price else None
            formatted_sl_price = ExchangeInfoCache.format_price(symbol, sl_price) if sl_price else None

            use_limit_order = False
            if order_side == 'BUY' and current_price > float(formatted_limit_price):
                use_limit_order = True
                logger.info(f"[SmartOrder] 当前价格 {current_price} > 触发价 {formatted_limit_price}，使用限价单 (Maker)")
            elif order_side == 'SELL' and current_price < float(formatted_limit_price):
                use_limit_order = True
                logger.info(f"[SmartOrder] 当前价格 {current_price} < 触发价 {formatted_limit_price}，使用限价单 (Maker)")
            else:
                logger.info("[SmartOrder] 使用条件单 (Taker)")

            if use_limit_order:
                return self._place_limit_entry_order(
                    symbol=symbol,
                    side=order_side,
                    price=formatted_limit_price,
                    quantity=formatted_quantity,
                    position_side=position_side,
                    tp_price=formatted_tp_price,
                    sl_price=formatted_sl_price,
                    source=source
                )
            else:
                return self._place_algo_entry_order(
                    symbol=symbol,
                    side=order_side,
                    trigger_price=formatted_limit_price,
                    quantity=formatted_quantity,
                    position_side=position_side,
                    tp_price=formatted_tp_price,
                    sl_price=formatted_sl_price,
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
        price: str,
        quantity: str,
        position_side: str,
        tp_price: Optional[str],
        sl_price: Optional[str],
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
        trigger_price: str,
        quantity: str,
        position_side: str,
        tp_price: Optional[str],
        sl_price: Optional[str],
        source: str,
        expiration_days: int,
        current_price: float
    ) -> Dict[str, Any]:
        """下条件单（开仓）"""
        try:
            trigger_float = float(trigger_price)
            if side == 'BUY':
                order_type = OrderType.STOP_MARKET if trigger_float > current_price else OrderType.TAKE_PROFIT_MARKET
            else:
                order_type = OrderType.STOP_MARKET if trigger_float < current_price else OrderType.TAKE_PROFIT_MARKET

            expire_time = datetime.now(timezone.utc) + timedelta(days=expiration_days)
            good_till_date = int(expire_time.timestamp() * 1000)

            logger.info(f"[SmartOrder] 当前价格: {current_price}, 触发价: {trigger_price}")
            logger.info(f"[SmartOrder] 条件单类型: {order_type.value} ({side} {position_side})")

            result = self.rest_client.place_algo_order(
                symbol=symbol,
                side=side,
                algo_type='CONDITIONAL',
                trigger_price=trigger_price,
                quantity=quantity,
                order_type=order_type.value,
                working_type='CONTRACT_PRICE',
                good_till_date=good_till_date,
                position_side=position_side
            )

            algo_id = str(result.get('algoId'))

            logger.info(f"[SmartOrder] ✅ 条件单创建成功: {symbol} {side} {order_type.value} @ {trigger_price} algoId={algo_id}")

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
                'order_type': order_type.value
            }

        except Exception as e:
            logger.error(f"[SmartOrder] 条件单下单失败: {e}")
            return {'error': str(e)}
