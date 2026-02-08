"""持仓操作模块

负责开仓、平仓等核心操作。
"""
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from modules.agent.live_engine.core import ExchangeInfoCache, RecordRepository, RecordStatus, TradeRecord
from modules.agent.live_engine.core.models import OrderPurpose
from modules.agent.live_engine.manager.order import get_close_side, get_position_side
from modules.monitor.utils.logger import get_logger

if TYPE_CHECKING:
    from modules.agent.live_engine.manager.position.position_manager import PositionManager

logger = get_logger('live_engine.position_operations')


def open_position(
    pm: 'PositionManager',
    symbol: str,
    side: str,
    quote_notional_usdt: float,
    leverage: int,
    tp_price: Optional[float] = None,
    sl_price: Optional[float] = None,
    source: str = 'live'
) -> Dict[str, Any]:
    """市价开仓

    Args:
        pm: PositionManager 实例
        symbol: 交易对
        side: 方向（long/short 或 BUY/SELL）
        quote_notional_usdt: 开仓金额（USDT）
        leverage: 杠杆倍数
        tp_price: 止盈价格（可选）
        sl_price: 止损价格（可选）
        source: 来源标识

    Returns:
        开仓结果字典
    """
    try:
        ticker = pm.rest_client.get_24hr_ticker(symbol)
        current_price = float(ticker.get('lastPrice', 0))
        if current_price <= 0:
            return {'success': False, 'error': f'无法获取 {symbol} 当前价格'}

        quantity = quote_notional_usdt / current_price
        quantity = ExchangeInfoCache.format_quantity(symbol, quantity)

        pm.order_executor.ensure_dual_position_mode()
        pm.order_executor.ensure_leverage(symbol, leverage)

        position_side = get_position_side(side)
        order_side = 'BUY' if side.upper() in ('LONG', 'BUY') else 'SELL'

        market_result = pm.order_executor.place_market_order(
            symbol=symbol,
            side=order_side,
            quantity=quantity,
            position_side=position_side
        )

        if not market_result.get('success'):
            return {'success': False, 'error': market_result.get('error', '市价单下单失败')}

        order_data = market_result.get('order', {})
        entry_price = float(order_data.get('avgPrice', current_price))
        filled_qty = float(order_data.get('executedQty', quantity))
        order_id = order_data.get('orderId')

        entry_commission = 0.0
        if order_id:
            entry_info = pm.trade_info_service.get_entry_info(symbol, order_id)
            if entry_info.avg_price and entry_info.avg_price > 0:
                entry_price = entry_info.avg_price
            entry_commission = entry_info.commission

        record = create_record(
            pm,
            symbol=symbol,
            side=side,
            qty=filled_qty,
            entry_price=entry_price,
            leverage=leverage,
            tp_price=tp_price,
            sl_price=sl_price,
            source=source,
            entry_order_id=order_id,
            entry_commission=entry_commission,
            auto_place_tpsl=True
        )

        logger.info(f"[PositionOps] ✅ 开仓成功: {symbol} {side} qty={filled_qty} "
                   f"price={entry_price} leverage={leverage}x")

        return {
            'success': True,
            'record_id': record.id if record else None,
            'symbol': symbol,
            'side': side,
            'quantity': filled_qty,
            'entry_price': entry_price,
            'leverage': leverage,
            'tp_price': tp_price,
            'sl_price': sl_price,
            'order_id': order_id
        }

    except Exception as e:
        logger.error(f"[PositionOps] 开仓失败: {symbol} error={e}", exc_info=True)
        return {'success': False, 'error': str(e)}


def close_position(
    pm: 'PositionManager',
    position_id: Optional[str] = None,
    symbol: Optional[str] = None,
    close_reason: Optional[str] = None
) -> Dict[str, Any]:
    """市价平仓

    Args:
        pm: PositionManager 实例
        position_id: 持仓记录 ID（可选）
        symbol: 交易对（可选，与 position_id 二选一）
        close_reason: 平仓原因（可选）

    Returns:
        平仓结果字典
    """
    try:
        record = None
        if position_id:
            record = pm._repository.get(position_id)
        elif symbol:
            records = pm.get_open_records_by_symbol(symbol)
            if records:
                record = records[0]

        if not record:
            return {'success': False, 'error': '未找到持仓记录'}

        if record.status != RecordStatus.OPEN:
            return {'success': False, 'error': '持仓已关闭'}

        position_side = get_position_side(record.side)
        close_side = get_close_side(position_side)

        market_result = pm.order_executor.place_market_order(
            symbol=record.symbol,
            side=close_side,
            quantity=record.qty,
            position_side=position_side
        )

        if not market_result.get('success'):
            return {'success': False, 'error': market_result.get('error', '平仓订单失败')}

        order_data = market_result.get('order', {})
        close_price = float(order_data.get('avgPrice', record.entry_price))
        order_id = order_data.get('orderId')

        exit_commission = 0.0
        realized_pnl = None
        if order_id:
            exit_info = pm.trade_info_service.get_exit_info(record.symbol, order_id)
            if exit_info.close_price:
                close_price = exit_info.close_price
            exit_commission = exit_info.exit_commission
            realized_pnl = exit_info.realized_pnl

        reason = close_reason or RecordStatus.MANUAL_CLOSED.value
        _cancel_remaining_tpsl(pm, record, None)

        close_record(
            pm,
            record_id=record.id,
            close_price=close_price,
            close_reason=reason,
            exit_commission=exit_commission,
            realized_pnl=realized_pnl
        )

        logger.info(f"[PositionOps] ✅ 平仓成功: {record.symbol} @ {close_price}")

        return {
            'success': True,
            'record_id': record.id,
            'symbol': record.symbol,
            'close_price': close_price,
            'realized_pnl': realized_pnl,
            'close_reason': reason
        }

    except Exception as e:
        logger.error(f"[PositionOps] 平仓失败: error={e}", exc_info=True)
        return {'success': False, 'error': str(e)}


def close_single_record(pm: 'PositionManager', record_id: str, source: Optional[str] = None) -> bool:
    """关闭指定的交易记录"""
    try:
        record = pm._repository.get(record_id)
        if not record:
            logger.warning(f"[PositionOps] 未找到记录: {record_id}")
            return False

        if record.status != RecordStatus.OPEN:
            logger.warning(f"[PositionOps] 记录已关闭: {record_id}")
            return True

        mark_price = pm.price_service.get_mark_price(record.symbol)

        position_side = get_position_side(record.side)
        close_side = get_close_side(position_side)

        market_result = pm.order_executor.place_market_order(
            symbol=record.symbol,
            side=close_side,
            quantity=record.qty,
            position_side=position_side
        )

        if not market_result.get('success'):
            logger.error(f"[PositionOps] 平仓订单失败: {record.symbol}")
            return False

        order_data = market_result.get('order', {})
        close_price = float(order_data.get('avgPrice', mark_price or record.entry_price))
        order_id = order_data.get('orderId')

        exit_commission = 0.0
        realized_pnl = None
        if order_id:
            exit_info = pm.trade_info_service.get_exit_info(record.symbol, order_id)
            if exit_info.close_price:
                close_price = exit_info.close_price
            exit_commission = exit_info.exit_commission
            realized_pnl = exit_info.realized_pnl

        _cancel_remaining_tpsl(pm, record, None)

        close_record(
            pm,
            record_id=record.id,
            close_price=close_price,
            close_reason=RecordStatus.MANUAL_CLOSED.value,
            exit_commission=exit_commission,
            realized_pnl=realized_pnl
        )

        logger.info(f"[PositionOps] ✅ 关闭记录成功: {record_id} {record.symbol} @ {close_price}")
        return True

    except Exception as e:
        logger.error(f"[PositionOps] 关闭记录失败: {record_id} error={e}", exc_info=True)
        return False


def close_all_by_symbol(pm: 'PositionManager', symbol: str, source: Optional[str] = None) -> int:
    """关闭指定交易对的所有开仓记录"""
    try:
        records = pm.get_open_records_by_symbol(symbol)
        if not records:
            logger.info(f"[PositionOps] {symbol} 无开仓记录")
            return 0

        closed_count = 0
        for record in records:
            if close_single_record(pm, record.id, source):
                closed_count += 1

        logger.info(f"[PositionOps] ✅ 批量关闭完成: {symbol} 共关闭 {closed_count}/{len(records)} 条记录")
        return closed_count

    except Exception as e:
        logger.error(f"[PositionOps] 批量关闭失败: {symbol} error={e}", exc_info=True)
        return 0


def create_record(
    pm: 'PositionManager',
    symbol: str,
    side: str,
    qty: float,
    entry_price: float,
    leverage: int = 10,
    tp_price: Optional[float] = None,
    sl_price: Optional[float] = None,
    source: str = 'live',
    entry_order_id: Optional[int] = None,
    entry_algo_id: Optional[str] = None,
    agent_order_id: Optional[str] = None,
    entry_commission: float = 0.0,
    auto_place_tpsl: bool = True,
    extra_data: Optional[Dict] = None
) -> TradeRecord:
    """创建开仓记录"""
    from modules.agent.live_engine.manager.position.tpsl_operations import place_tp_sl_for_position

    record = pm._repository.create(
        symbol=symbol,
        side=side,
        qty=qty,
        entry_price=entry_price,
        leverage=leverage,
        tp_price=tp_price,
        sl_price=sl_price,
        source=source,
        entry_order_id=entry_order_id,
        entry_algo_id=entry_algo_id,
        agent_order_id=agent_order_id,
        extra_data=extra_data,
    )

    if entry_commission > 0:
        pm._repository.update(record.id, entry_commission=entry_commission)

    if pm.linked_order_repo and entry_order_id:
        position_side = 'LONG' if side.upper() in ('LONG', 'BUY') else 'SHORT'
        order_side = 'BUY' if side.upper() in ('LONG', 'BUY') else 'SELL'
        pm.linked_order_repo.create_order(
            record_id=record.id,
            symbol=symbol,
            purpose=OrderPurpose.ENTRY,
            side=order_side,
            position_side=position_side,
            quantity=qty,
            price=entry_price,
            binance_order_id=entry_order_id,
            binance_algo_id=entry_algo_id,
        )

    logger.info(f"[PositionOps] ✅ 创建记录: {symbol} {side} qty={qty} "
               f"entry={entry_price} source={source}")

    if auto_place_tpsl and (tp_price or sl_price):
        position_side = 'LONG' if side.upper() in ('LONG', 'BUY') else 'SHORT'
        close_side = 'SELL' if position_side == 'LONG' else 'BUY'

        tpsl_result = place_tp_sl_for_position(
            pm,
            symbol=symbol,
            side=side,
            quantity=qty,
            tp_price=tp_price,
            sl_price=sl_price,
            use_limit_for_tp=True
        )

        pm._repository.update_tpsl_ids(
            record.id,
            tp_order_id=tpsl_result.get('tp_order_id'),
            tp_algo_id=tpsl_result.get('tp_algo_id'),
            sl_algo_id=tpsl_result.get('sl_algo_id')
        )

        if pm.linked_order_repo:
            if tpsl_result.get('tp_order_id'):
                pm.linked_order_repo.create_order(
                    record_id=record.id,
                    symbol=symbol,
                    purpose=OrderPurpose.TAKE_PROFIT,
                    side=close_side,
                    position_side=position_side,
                    quantity=qty,
                    price=tp_price,
                    binance_order_id=tpsl_result['tp_order_id'],
                    reduce_only=True
                )

            if tpsl_result.get('tp_algo_id'):
                pm.linked_order_repo.create_order(
                    record_id=record.id,
                    symbol=symbol,
                    purpose=OrderPurpose.TAKE_PROFIT,
                    side=close_side,
                    position_side=position_side,
                    quantity=qty,
                    stop_price=tp_price,
                    binance_algo_id=tpsl_result['tp_algo_id'],
                    reduce_only=True
                )

            if tpsl_result.get('sl_algo_id'):
                pm.linked_order_repo.create_order(
                    record_id=record.id,
                    symbol=symbol,
                    purpose=OrderPurpose.STOP_LOSS,
                    side=close_side,
                    position_side=position_side,
                    quantity=qty,
                    stop_price=sl_price,
                    binance_algo_id=tpsl_result['sl_algo_id'],
                    reduce_only=True
                )

        if sl_price and tpsl_result.get('sl_algo_id') is None:
            logger.critical(f"[PositionOps] ❌ SL 订单下单失败！{symbol} {side} "
                          f"sl_price={sl_price} - 仓位无止损保护！")

        record = pm._repository.get(record.id)
        logger.info(f"[PositionOps] TP/SL 已下单: tp_order={record.tp_order_id} "
                   f"tp_algo={record.tp_algo_id} sl_algo={record.sl_algo_id}")

    return record


def close_record(
    pm: 'PositionManager',
    record_id: str,
    close_price: float,
    close_reason: str,
    exit_commission: float = 0.0,
    realized_pnl: Optional[float] = None
) -> Optional[TradeRecord]:
    """关闭记录"""
    record = pm._repository.get(record_id)
    if not record:
        return None

    if record.status != RecordStatus.OPEN:
        return record

    total_commission = record.entry_commission + exit_commission

    if realized_pnl is None:
        if record.side.upper() in ('LONG', 'BUY'):
            pnl = (close_price - record.entry_price) * record.qty
        else:
            pnl = (record.entry_price - close_price) * record.qty
        realized_pnl = pnl - total_commission

    pm._repository.update(record_id,
                           exit_commission=exit_commission,
                           total_commission=total_commission)

    record = pm._repository.close(record_id, close_price, close_reason, realized_pnl)

    if record:
        pnl_sign = '+' if (record.realized_pnl or 0) >= 0 else ''
        logger.info(f"[PositionOps] 📕 关闭记录: {record.symbol} {record.side} "
                   f"PnL={pnl_sign}{record.realized_pnl:.4f} reason={close_reason}")

    return record


def _cancel_remaining_tpsl(pm: 'PositionManager', record: TradeRecord, triggered_type: Optional[str]):
    """取消剩余的 TP/SL 订单"""
    try:
        if triggered_type == 'TP':
            if record.sl_algo_id:
                pm.order_executor.cancel_algo_order(record.symbol, record.sl_algo_id)
                logger.info(f"[PositionOps] 🚫 取消止损单: {record.symbol} algoId={record.sl_algo_id}")
                pm._repository.update(record.id, sl_algo_id=None)
        elif triggered_type == 'SL':
            if record.tp_order_id:
                pm.order_executor.cancel_order(record.symbol, record.tp_order_id)
                logger.info(f"[PositionOps] 🚫 取消止盈限价单: {record.symbol} orderId={record.tp_order_id}")
                pm._repository.update(record.id, tp_order_id=None)
            if record.tp_algo_id:
                pm.order_executor.cancel_algo_order(record.symbol, record.tp_algo_id)
                logger.info(f"[PositionOps] 🚫 取消止盈策略单: {record.symbol} algoId={record.tp_algo_id}")
                pm._repository.update(record.id, tp_algo_id=None)
        else:
            if record.tp_order_id:
                pm.order_executor.cancel_order(record.symbol, record.tp_order_id)
                pm._repository.update(record.id, tp_order_id=None)
            if record.tp_algo_id:
                pm.order_executor.cancel_algo_order(record.symbol, record.tp_algo_id)
                pm._repository.update(record.id, tp_algo_id=None)
            if record.sl_algo_id:
                pm.order_executor.cancel_algo_order(record.symbol, record.sl_algo_id)
                pm._repository.update(record.id, sl_algo_id=None)
    except Exception as e:
        logger.error(f"[PositionOps] 取消订单失败: {e}")
