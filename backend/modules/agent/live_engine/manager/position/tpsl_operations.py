"""TP/SL 操作模块

负责止盈止损订单的管理：放置、更新、取消、同步、清理。
"""
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from modules.agent.live_engine.core.models import OrderType
from modules.agent.live_engine.manager.order import get_close_side, get_position_side
from modules.monitor.utils.logger import get_logger

if TYPE_CHECKING:
    from modules.agent.live_engine.manager.position.position_manager import PositionManager

logger = get_logger('live_engine.tpsl_operations')


def place_tp_sl_for_position(
    pm: 'PositionManager',
    symbol: str,
    side: str,
    quantity: float,
    tp_price: Optional[float] = None,
    sl_price: Optional[float] = None,
    use_limit_for_tp: bool = True
) -> Dict[str, Any]:
    """为持仓下止盈止损单

    Args:
        pm: PositionManager 实例
        symbol: 交易对
        side: 持仓方向（long/short）
        quantity: 数量
        tp_price: 止盈价
        sl_price: 止损价
        use_limit_for_tp: 止盈是否使用限价单（Maker 低手续费）

    Returns:
        结果，包含 tp_order_id/tp_algo_id 和 sl_algo_id
    """
    position_side = get_position_side(side)
    close_side = get_close_side(position_side)

    logger.info(f"[TPSL] 📦 下 TP/SL 单: {symbol} side={side} qty={quantity} "
               f"tp={tp_price} sl={sl_price}")

    result = {
        'tp_order_id': None,
        'tp_algo_id': None,
        'sl_algo_id': None,
        'success': True
    }

    tp_failed = False
    sl_failed = False

    if tp_price:
        if use_limit_for_tp:
            tp_result = pm.order_executor.place_limit_order(
                symbol=symbol,
                side=close_side,
                price=tp_price,
                quantity=quantity,
                position_side=position_side
            )
            if tp_result.get('success'):
                result['tp_order_id'] = tp_result.get('order_id')
            else:
                tp_algo = pm.order_executor.place_algo_order(
                    symbol=symbol,
                    side=close_side,
                    trigger_price=tp_price,
                    quantity=quantity,
                    order_type=OrderType.TAKE_PROFIT_MARKET.value,
                    position_side=position_side
                )
                if tp_algo.get('success'):
                    result['tp_algo_id'] = tp_algo.get('algo_id')
                else:
                    tp_failed = True
        else:
            tp_algo = pm.order_executor.place_algo_order(
                symbol=symbol,
                side=close_side,
                trigger_price=tp_price,
                quantity=quantity,
                order_type=OrderType.TAKE_PROFIT_MARKET.value,
                position_side=position_side
            )
            if tp_algo.get('success'):
                result['tp_algo_id'] = tp_algo.get('algo_id')
            else:
                tp_failed = True

    if sl_price:
        sl_algo = pm.order_executor.place_algo_order(
            symbol=symbol,
            side=close_side,
            trigger_price=sl_price,
            quantity=quantity,
            order_type=OrderType.STOP_MARKET.value,
            position_side=position_side
        )
        if sl_algo.get('success'):
            result['sl_algo_id'] = sl_algo.get('algo_id')
        else:
            sl_failed = True

    if tp_failed or sl_failed:
        result['success'] = False

    logger.info(f"[TPSL] TP/SL 结果: {result}")
    return result


def update_tp_sl(
    pm: 'PositionManager',
    symbol: str,
    tp_price: Optional[float] = None,
    sl_price: Optional[float] = None
) -> Dict[str, Any]:
    """更新止盈止损价格"""
    try:
        records = pm.get_open_records_by_symbol(symbol)
        if not records:
            return {'success': False, 'error': f'未找到 {symbol} 的开仓记录'}

        record = records[0]

        cancel_tpsl_orders(pm, symbol)

        tpsl_result = place_tp_sl_for_position(
            pm,
            symbol=symbol,
            side=record.side,
            quantity=record.qty,
            tp_price=tp_price,
            sl_price=sl_price
        )

        pm._repository.update_tpsl_ids(
            record.id,
            tp_order_id=tpsl_result.get('tp_order_id'),
            tp_algo_id=tpsl_result.get('tp_algo_id'),
            sl_algo_id=tpsl_result.get('sl_algo_id')
        )

        logger.info(f"[TPSL] ✅ TP/SL 更新成功: {symbol} tp={tp_price} sl={sl_price}")

        return {
            'success': True,
            'symbol': symbol,
            'record_id': record.id,
            'tp_price': tp_price,
            'sl_price': sl_price,
            'tp_order_id': tpsl_result.get('tp_order_id'),
            'tp_algo_id': tpsl_result.get('tp_algo_id'),
            'sl_algo_id': tpsl_result.get('sl_algo_id')
        }

    except Exception as e:
        logger.error(f"[TPSL] 更新 TP/SL 失败: {symbol} error={e}", exc_info=True)
        return {'success': False, 'error': str(e)}


def cancel_tpsl_orders(pm: 'PositionManager', symbol: str):
    """撤销指定币种的 TP/SL 订单"""
    if symbol not in pm.tpsl_orders:
        return

    orders = pm.tpsl_orders[symbol]

    if orders.get('tp_order_id'):
        pm.order_executor.cancel_order(symbol, orders['tp_order_id'])

    if orders.get('sl_order_id'):
        pm.order_executor.cancel_order(symbol, orders['sl_order_id'])

    pm.tpsl_orders.pop(symbol, None)


def sync_tpsl_orders(pm: 'PositionManager'):
    """同步 TP/SL 订单状态（从 API 查询）并清理多余订单"""
    try:
        open_orders = pm.order_executor.get_open_orders()

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

        new_tpsl = {}
        canceled_count = 0

        for symbol, orders_dict in symbol_orders.items():
            tp_orders = orders_dict['tp_orders']
            sl_orders = orders_dict['sl_orders']

            local_record = pm.tpsl_orders.get(symbol, {})
            local_tp_id = local_record.get('tp_order_id')
            local_sl_id = local_record.get('sl_order_id')

            tp_order_id = None
            if tp_orders:
                if local_tp_id:
                    tp_ids = [o['order_id'] for o in tp_orders]
                    if local_tp_id in tp_ids:
                        tp_order_id = local_tp_id

                if not tp_order_id:
                    tp_orders_sorted = sorted(tp_orders, key=lambda x: x['order_id'], reverse=True)
                    tp_order_id = tp_orders_sorted[0]['order_id']

                for order_info in tp_orders:
                    if order_info['order_id'] != tp_order_id:
                        old_id = order_info['order_id']
                        logger.warning(f"发现 {symbol} 多余的止盈订单 {old_id}，撤销")
                        if pm.order_executor.cancel_order(symbol, old_id):
                            canceled_count += 1

            sl_order_id = None
            if sl_orders:
                if local_sl_id:
                    sl_ids = [o['order_id'] for o in sl_orders]
                    if local_sl_id in sl_ids:
                        sl_order_id = local_sl_id

                if not sl_order_id:
                    sl_orders_sorted = sorted(sl_orders, key=lambda x: x['order_id'], reverse=True)
                    sl_order_id = sl_orders_sorted[0]['order_id']

                for order_info in sl_orders:
                    if order_info['order_id'] != sl_order_id:
                        old_id = order_info['order_id']
                        logger.warning(f"发现 {symbol} 多余的止损订单 {old_id}，撤销")
                        if pm.order_executor.cancel_order(symbol, old_id):
                            canceled_count += 1

            new_tpsl[symbol] = {
                'tp_order_id': tp_order_id,
                'sl_order_id': sl_order_id
            }

        if canceled_count > 0:
            logger.info(f"🧹 同步订单时清理了 {canceled_count} 个多余的 TP/SL 订单")

        pm.tpsl_orders = new_tpsl
        logger.info(f"TP/SL 订单状态已同步: {len(new_tpsl)} 个币种")

    except Exception as e:
        logger.error(f"同步 TP/SL 订单失败: {e}")


def cleanup_orphan_orders(pm: 'PositionManager', active_symbols: Set[str]) -> int:
    """清理孤儿订单（有 TP/SL 订单但无持仓的 symbol）"""
    cleaned_count = 0

    for symbol in list(pm.tpsl_orders.keys()):
        if symbol not in active_symbols:
            logger.warning(f"发现孤儿订单（本地记录）: {symbol} 有 TP/SL 订单但无持仓，自动清理")
            cancel_tpsl_orders(pm, symbol)
            cleaned_count += 1

    try:
        all_open_orders = pm.order_executor.get_open_orders()
        for order in all_open_orders:
            symbol = order['symbol']
            order_type = order['type']
            order_id = order['orderId']

            if order_type in [OrderType.TAKE_PROFIT_MARKET.value, OrderType.STOP_MARKET.value] and symbol not in active_symbols:
                logger.warning(f"发现孤儿订单（API 查询）: {symbol} {order_type} orderId={order_id}，无持仓，自动撤销")
                if pm.order_executor.cancel_order(symbol, order_id):
                    cleaned_count += 1
    except Exception as e:
        logger.error(f"查询 API 订单失败: {e}")

    if cleaned_count > 0:
        logger.info(f"🧹 已清理 {cleaned_count} 个孤儿订单")

    return cleaned_count


def get_tpsl_prices(pm: 'PositionManager', symbol: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """查询当前挂单中的 TP/SL 价格和订单 ID"""
    try:
        open_orders = pm.order_executor.get_open_orders(symbol)
        algo_orders = pm.order_executor.get_algo_open_orders(symbol)

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


def update_local_tracking(pm: 'PositionManager', symbol: str, tp_order_id: int = None, sl_order_id: int = None):
    """更新本地跟踪记录"""
    if symbol not in pm.tpsl_orders:
        pm.tpsl_orders[symbol] = {'tp_order_id': None, 'sl_order_id': None}

    if tp_order_id is not None:
        pm.tpsl_orders[symbol]['tp_order_id'] = tp_order_id
    if sl_order_id is not None:
        pm.tpsl_orders[symbol]['sl_order_id'] = sl_order_id


def clear_local_tracking(pm: 'PositionManager', symbol: str):
    """清除本地跟踪记录"""
    pm.tpsl_orders.pop(symbol, None)


def handle_order_cancelled(pm: 'PositionManager', symbol: str, order_id: int):
    """处理订单取消事件"""
    if symbol in pm.tpsl_orders:
        orders = pm.tpsl_orders[symbol]
        if orders.get('tp_order_id') == order_id:
            orders['tp_order_id'] = None
        elif orders.get('sl_order_id') == order_id:
            orders['sl_order_id'] = None

        if not orders.get('tp_order_id') and not orders.get('sl_order_id'):
            del pm.tpsl_orders[symbol]


def clear_tpsl_ids(pm: 'PositionManager', record_id: str):
    """清除记录的 TP/SL 订单 ID"""
    pm._repository.update(record_id, tp_order_id=None, tp_algo_id=None, sl_algo_id=None)


def restore_from_state(pm: 'PositionManager'):
    """从 trade_state.json 恢复订单 ID 记录"""
    import json
    import os

    try:
        state_path = pm.config.get('agent', {}).get('trade_state_path', 'agent/trade_state.json')
        if not os.path.exists(state_path):
            return

        with open(state_path, 'r', encoding='utf-8') as f:
            state_data = json.load(f)

        positions = state_data.get('positions', {})
        restored_count = 0

        for symbol, pos_data in positions.items():
            tp_id = pos_data.get('tp_order_id')
            sl_id = pos_data.get('sl_order_id')

            if tp_id or sl_id:
                pm.tpsl_orders[symbol] = {
                    'tp_order_id': tp_id,
                    'sl_order_id': sl_id
                }
                restored_count += 1
                logger.info(f"恢复订单 ID 记录: {symbol} tp={tp_id}, sl={sl_id}")

        if restored_count > 0:
            logger.info(f"✓ 从 trade_state.json 恢复了 {restored_count} 个币种的订单 ID 记录")

    except Exception as e:
        logger.warning(f"从 trade_state.json 恢复订单 ID 失败: {e}")
