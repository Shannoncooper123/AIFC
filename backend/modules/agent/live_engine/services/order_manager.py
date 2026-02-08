"""统一订单管理器

提供所有类型订单的下单、撤销、查询能力，供 live_engine 和 reverse_engine 共用。

支持订单类型：
- 市价单 (MARKET)
- 限价单 (LIMIT)
- 条件单 (STOP_MARKET / TAKE_PROFIT_MARKET)
- 策略单 (Binance Algo Orders)
"""

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from modules.agent.live_engine.core import ExchangeInfoCache
from modules.agent.live_engine.core.models import OrderType
from modules.monitor.utils.logger import get_logger

if TYPE_CHECKING:
    from modules.monitor.clients.binance_rest import BinanceRestClient

logger = get_logger('live_engine.order_manager')


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


class OrderManager:
    """统一订单管理器

    集中管理所有订单操作，包括：
    - 开仓/平仓市价单
    - 限价单（Maker 低手续费）
    - 条件单（止盈止损）
    - 策略条件单（Algo Orders）
    """

    def __init__(self, rest_client: 'BinanceRestClient'):
        """初始化

        Args:
            rest_client: Binance REST 客户端
        """
        self.rest_client = rest_client
        self._dual_mode_checked = False
        self._symbol_leverage_set: set = set()

    def ensure_dual_position_mode(self) -> bool:
        """确保账户为双向持仓模式

        Returns:
            是否成功设置/确认双向持仓模式
        """
        if self._dual_mode_checked:
            return True

        try:
            mode_info = self.rest_client.get_position_mode()
            is_dual = mode_info.get('dualSidePosition', False)

            if not is_dual:
                logger.info("[OrderManager] 当前为单向持仓模式，尝试切换为双向持仓模式...")
                try:
                    self.rest_client.change_position_mode(dual_side_position=True)
                    logger.info("[OrderManager] 已成功切换为双向持仓模式")
                except Exception as e:
                    error_msg = str(e)
                    if 'No need to change position side' in error_msg or '-4059' in error_msg:
                        logger.info("[OrderManager] 已经是双向持仓模式，无需切换")
                    elif 'position or open order' in error_msg.lower() or '-4068' in error_msg:
                        logger.warning("[OrderManager] 无法切换持仓模式：存在持仓或挂单")
                        return False
                    else:
                        logger.error(f"[OrderManager] 切换持仓模式失败: {e}")
                        return False
            else:
                logger.debug("[OrderManager] 已确认为双向持仓模式")

            self._dual_mode_checked = True
            return True

        except Exception as e:
            logger.error(f"[OrderManager] 检查持仓模式失败: {e}")
            return False

    def ensure_leverage(self, symbol: str, leverage: int) -> bool:
        """确保指定币种的杠杆已设置

        Args:
            symbol: 交易对
            leverage: 目标杠杆

        Returns:
            是否成功
        """
        cache_key = f"{symbol}_{leverage}"
        if cache_key in self._symbol_leverage_set:
            return True

        try:
            self.rest_client.set_leverage(symbol, leverage)
            logger.info(f"[OrderManager] {symbol} 杠杆已设置为 {leverage}x")
            self._symbol_leverage_set.add(cache_key)
            return True
        except Exception as e:
            error_msg = str(e)
            if 'No need to change leverage' in error_msg or '-4028' in error_msg:
                logger.debug(f"[OrderManager] {symbol} 杠杆已经是 {leverage}x")
                self._symbol_leverage_set.add(cache_key)
                return True
            else:
                logger.warning(f"[OrderManager] 设置 {symbol} 杠杆失败: {e}")
                return False

    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        position_side: Optional[str] = None,
        reduce_only: bool = False
    ) -> Dict[str, Any]:
        """下市价单

        Args:
            symbol: 交易对
            side: 方向（BUY/SELL）
            quantity: 数量
            position_side: 持仓方向（LONG/SHORT），不传则自动推断
            reduce_only: 是否只减仓

        Returns:
            订单结果
        """
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

            if reduce_only:
                params['reduce_only'] = True

            result = self.rest_client.place_order(**params)

            logger.info(f"[OrderManager] 市价单成功: {symbol} {side} qty={qty} positionSide={pos_side}")
            return {'success': True, 'order': result, 'order_id': result.get('orderId')}

        except Exception as e:
            logger.error(f"[OrderManager] 市价单失败: {symbol} {side} error={e}")
            return {'success': False, 'error': str(e)}

    def place_limit_order(
        self,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        position_side: Optional[str] = None,
        time_in_force: str = 'GTC',
        reduce_only: bool = False
    ) -> Dict[str, Any]:
        """下限价单（Maker 低手续费）

        Args:
            symbol: 交易对
            side: 方向（BUY/SELL）
            price: 限价
            quantity: 数量
            position_side: 持仓方向
            time_in_force: 有效期（GTC/IOC/FOK）
            reduce_only: 是否只减仓

        Returns:
            订单结果
        """
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

            if reduce_only:
                params['reduce_only'] = True

            result = self.rest_client.place_order(**params)
            order_id = result.get('orderId')

            logger.info(f"[OrderManager] 限价单成功: {symbol} {side} price={formatted_price} "
                       f"qty={qty} orderId={order_id} (Maker)")
            return {'success': True, 'order': result, 'order_id': order_id}

        except Exception as e:
            logger.error(f"[OrderManager] 限价单失败: {symbol} {side} price={price} error={e}")
            return {'success': False, 'error': str(e)}

    def place_algo_order(
        self,
        symbol: str,
        side: str,
        trigger_price: float,
        quantity: float,
        order_type: str = 'STOP_MARKET',  # 使用字符串，因为需要传给 Binance API
        position_side: Optional[str] = None,
        working_type: str = 'CONTRACT_PRICE',
        expiration_days: int = 7,
        reduce_only: bool = False
    ) -> Dict[str, Any]:
        """下策略条件单 (Algo Order)

        使用 Binance 策略订单 API，支持更长的有效期。

        Args:
            symbol: 交易对
            side: 方向
            trigger_price: 触发价格
            quantity: 数量
            order_type: 订单类型（STOP_MARKET/TAKE_PROFIT_MARKET）
            position_side: 持仓方向
            working_type: 触发价类型
            expiration_days: 过期天数
            reduce_only: 是否只减仓

        Returns:
            订单结果，包含 algo_id
        """
        try:
            formatted_price = ExchangeInfoCache.format_price(symbol, trigger_price)
            qty = ExchangeInfoCache.format_quantity(symbol, quantity)
            pos_side = position_side or get_position_side(side)

            expiration_ms = int((datetime.now() + timedelta(days=expiration_days)).timestamp() * 1000)

            result = self.rest_client.place_algo_order(
                symbol=symbol,
                side=side.upper(),
                algo_type='CONDITIONAL',
                trigger_price=formatted_price,
                quantity=qty,
                order_type=order_type,
                working_type=working_type,
                good_till_date=expiration_ms,
                position_side=pos_side,
                reduce_only=reduce_only
            )

            algo_id = str(result.get('algoId', ''))

            logger.info(f"[OrderManager] 策略单成功: {symbol} {side} trigger={formatted_price} "
                       f"algoId={algo_id} type={order_type}")
            return {'success': True, 'result': result, 'algo_id': algo_id}

        except Exception as e:
            logger.error(f"[OrderManager] 策略单失败: {symbol} trigger={trigger_price} error={e}")
            return {'success': False, 'error': str(e)}

    def cancel_order(self, symbol: str, order_id: int) -> bool:
        """撤销普通订单

        Args:
            symbol: 交易对
            order_id: 订单ID

        Returns:
            是否成功
        """
        try:
            self.rest_client.cancel_order(symbol=symbol, order_id=order_id)
            logger.info(f"[OrderManager] 订单已撤销: {symbol} orderId={order_id}")
            return True
        except Exception as e:
            logger.warning(f"[OrderManager] 撤销订单失败: {symbol} orderId={order_id} error={e}")
            return False

    def cancel_algo_order(self, symbol: str, algo_id: str) -> bool:
        """撤销策略条件单

        Args:
            symbol: 交易对
            algo_id: 策略单ID

        Returns:
            是否成功
        """
        try:
            self.rest_client.cancel_algo_order(symbol, algo_id)
            logger.info(f"[OrderManager] 策略单已撤销: {symbol} algoId={algo_id}")
            return True
        except Exception as e:
            logger.warning(f"[OrderManager] 撤销策略单失败: {symbol} algoId={algo_id} error={e}")
            return False

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """获取未成交订单

        Args:
            symbol: 交易对（可选）

        Returns:
            订单列表
        """
        try:
            if symbol:
                return self.rest_client.get_open_orders(symbol)
            return self.rest_client.get_open_orders()
        except Exception as e:
            logger.error(f"[OrderManager] 获取订单失败: {e}")
            return []

    def get_algo_open_orders(self) -> List[Dict]:
        """获取未触发的策略条件单

        Returns:
            策略单列表
        """
        try:
            result = self.rest_client.get_algo_open_orders()
            return result if result else []
        except Exception as e:
            logger.error(f"[OrderManager] 获取策略单失败: {e}")
            return []

    def get_mark_price(self, symbol: str) -> Optional[float]:
        """获取标记价格

        Args:
            symbol: 交易对

        Returns:
            标记价格，失败返回 None
        """
        try:
            data = self.rest_client.get_mark_price(symbol)
            return float(data.get('markPrice', 0))
        except Exception as e:
            logger.warning(f"[OrderManager] 获取 {symbol} 标记价格失败: {e}")
            return None

    def place_tp_sl_for_position(
        self,
        symbol: str,
        side: str,
        quantity: float,
        tp_price: Optional[float] = None,
        sl_price: Optional[float] = None,
        use_limit_for_tp: bool = True
    ) -> Dict[str, Any]:
        """为持仓下止盈止损单

        Args:
            symbol: 交易对
            side: 持仓方向（long/short）
            quantity: 数量
            tp_price: 止盈价
            sl_price: 止损价
            use_limit_for_tp: 止盈是否使用限价单（Maker 低手续费）

        Returns:
            结果，包含 tp_order_id/tp_algo_id 和 sl_order_id
        """
        position_side = get_position_side(side)
        close_side = get_close_side(position_side)

        logger.info(f"[OrderManager] 📦 下 TP/SL 单: {symbol} side={side} qty={quantity} "
                   f"tp={tp_price} sl={sl_price} position_side={position_side} close_side={close_side}")

        result = {
            'tp_order_id': None,
            'tp_algo_id': None,
            'sl_order_id': None,
            'sl_algo_id': None,
            'success': True
        }

        tp_failed = False
        sl_failed = False

        if tp_price:
            if use_limit_for_tp:
                tp_result = self.place_limit_order(
                    symbol=symbol,
                    side=close_side,
                    price=tp_price,
                    quantity=quantity,
                    position_side=position_side,
                    reduce_only=True
                )
                if tp_result.get('success'):
                    result['tp_order_id'] = tp_result.get('order_id')
                else:
                    tp_algo = self.place_algo_order(
                        symbol=symbol,
                        side=close_side,
                        trigger_price=tp_price,
                        quantity=quantity,
                        order_type=OrderType.TAKE_PROFIT_MARKET.value,
                        position_side=position_side,
                        reduce_only=True
                    )
                    if tp_algo.get('success'):
                        result['tp_algo_id'] = tp_algo.get('algo_id')
                    else:
                        tp_failed = True
            else:
                tp_algo = self.place_algo_order(
                    symbol=symbol,
                    side=close_side,
                    trigger_price=tp_price,
                    quantity=quantity,
                    order_type=OrderType.TAKE_PROFIT_MARKET.value,
                    position_side=position_side,
                    reduce_only=True
                )
                if tp_algo.get('success'):
                    result['tp_algo_id'] = tp_algo.get('algo_id')
                else:
                    tp_failed = True

        if sl_price:
            sl_algo = self.place_algo_order(
                symbol=symbol,
                side=close_side,
                trigger_price=sl_price,
                quantity=quantity,
                order_type=OrderType.STOP_MARKET.value,
                position_side=position_side,
                reduce_only=True
            )
            if sl_algo.get('success'):
                result['sl_algo_id'] = sl_algo.get('algo_id')
            else:
                sl_failed = True

        if tp_failed or sl_failed:
            result['success'] = False

        logger.info(f"[OrderManager] TP/SL 结果: {result}")
        return result
