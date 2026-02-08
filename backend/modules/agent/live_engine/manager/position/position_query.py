"""持仓查询模块

负责持仓数据的汇总、统计、历史查询。
"""
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from modules.agent.live_engine.core import RecordStatus

if TYPE_CHECKING:
    from modules.agent.live_engine.manager.position.position_manager import PositionManager


def get_summary(pm: 'PositionManager', source: Optional[str] = None) -> List[Dict[str, Any]]:
    """获取开仓记录汇总"""
    records = pm._repository.get_open_records(source)
    result = []

    for record in records:
        result.append({
            'id': record.id,
            'symbol': record.symbol,
            'side': record.side.upper(),
            'size': record.qty,
            'entry_price': record.entry_price,
            'mark_price': record.latest_mark_price or record.entry_price,
            'take_profit': record.tp_price,
            'stop_loss': record.sl_price,
            'tp_order_id': record.tp_order_id,
            'tp_algo_id': record.tp_algo_id,
            'sl_algo_id': record.sl_algo_id,
            'unrealized_pnl': round(record.unrealized_pnl(), 4),
            'roe': round(record.roe() * 100, 2),
            'leverage': record.leverage,
            'margin': round(record.margin_usdt, 4),
            'opened_at': record.open_time,
            'source': record.source
        })

    return result


def get_statistics(pm: 'PositionManager', source: Optional[str] = None) -> Dict[str, Any]:
    """获取统计信息"""
    all_records = pm._repository.get_all()

    if source:
        all_records = [r for r in all_records if r.source == source]

    open_records = [r for r in all_records if r.status == RecordStatus.OPEN]
    closed_records = [r for r in all_records if r.status != RecordStatus.OPEN]

    pnl_list = [r.realized_pnl or 0 for r in closed_records]
    total_pnl = sum(pnl_list)
    win_count = sum(1 for pnl in pnl_list if pnl > 0)
    loss_count = sum(1 for pnl in pnl_list if pnl < 0)
    total_commission = sum(r.total_commission for r in closed_records)

    return {
        'total_trades': len(closed_records),
        'winning_trades': win_count,
        'losing_trades': loss_count,
        'win_rate': round(win_count / len(closed_records) * 100, 2) if closed_records else 0,
        'total_pnl': round(total_pnl, 4),
        'avg_pnl': round(total_pnl / len(closed_records), 4) if closed_records else 0,
        'max_profit': round(max(pnl_list), 4) if pnl_list else 0,
        'max_loss': round(min(pnl_list), 4) if pnl_list else 0,
        'open_count': len(open_records),
        'total_commission': round(total_commission, 6)
    }


def get_history(pm: 'PositionManager', source: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """获取已关闭的交易记录历史"""
    all_records = pm._repository.get_all()
    closed_records = [r for r in all_records if r.status != RecordStatus.OPEN]

    if source:
        closed_records = [r for r in closed_records if r.source == source]

    closed_records.sort(key=lambda r: r.close_time or '', reverse=True)
    closed_records = closed_records[:limit]

    result = []
    for record in closed_records:
        result.append({
            'id': record.id,
            'symbol': record.symbol,
            'side': record.side.upper(),
            'qty': record.qty,
            'entry_price': record.entry_price,
            'exit_price': record.close_price,
            'leverage': record.leverage,
            'margin_usdt': round(record.margin_usdt, 4),
            'realized_pnl': round(record.realized_pnl or 0, 4),
            'pnl_percent': round(record.pnl_percent() * 100, 2) if record.pnl_percent() else 0,
            'open_time': record.open_time,
            'close_time': record.close_time,
            'close_reason': record.close_reason,
            'source': record.source,
            'entry_commission': round(record.entry_commission, 6),
            'exit_commission': round(record.exit_commission, 6),
            'total_commission': round(record.total_commission, 6)
        })

    return result


def get_open_symbols(pm: 'PositionManager', source: Optional[str] = None) -> Set[str]:
    """获取当前持仓的交易对集合"""
    open_records = pm._repository.get_open_records(source)
    return {record.symbol for record in open_records}


def get_pending_orders_summary(pm: 'PositionManager', order_repository, source: Optional[str] = None) -> Dict[str, Any]:
    """获取待处理订单汇总"""
    if source:
        orders = order_repository.get_orders_by_source(source)
    else:
        orders = order_repository.get_all()

    conditional_orders = []
    limit_orders = []

    for order in orders:
        order_dict = order.to_dict() if hasattr(order, 'to_dict') else vars(order)
        order_kind = getattr(order, 'order_kind', None) or order_dict.get('order_kind', '')

        if order_kind == 'conditional':
            conditional_orders.append(order_dict)
        else:
            limit_orders.append(order_dict)

    return {
        'total_conditional': len(conditional_orders),
        'total_limit': len(limit_orders),
        'conditional_orders': conditional_orders,
        'limit_orders': limit_orders
    }
