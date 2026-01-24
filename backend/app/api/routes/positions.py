"""持仓 API 路由"""
import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Query

from app.core.config import BASE_DIR, get_config
from modules.agent.trade_simulator.storage import load_position_history
from app.models.schemas import (
    AccountSummary,
    Position,
    PositionHistoryEntry,
    PositionHistoryResponse,
    PositionsResponse,
    TradeStateResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/positions", tags=["positions"])


def _load_json_file_sync(file_path: Path) -> Dict[str, Any]:
    """同步加载 JSON 文件"""
    if not file_path.exists():
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"加载JSON文件失败 {file_path}: {e}")
        return {}


async def load_json_file(file_path: Path) -> Dict[str, Any]:
    """异步加载 JSON 文件（在线程池中执行）"""
    return await asyncio.to_thread(_load_json_file_sync, file_path)


def parse_position(data: Dict[str, Any]) -> Position:
    """解析持仓数据 - 字段名与前端 types/positions.ts 对齐"""
    side_raw = data.get("side", "long").lower()
    side = side_raw.upper()
    
    size = float(data.get("qty", 0) or data.get("size", 0) or 0)
    mark_price = data.get("mark_price") or data.get("latest_mark_price")
    take_profit = data.get("tp_price") or data.get("take_profit")
    stop_loss = data.get("sl_price") or data.get("stop_loss")
    opened_at = data.get("open_time") or data.get("opened_at")
    margin = data.get("margin_used") or data.get("margin")
    
    entry_price = float(data.get("entry_price", 0))
    if mark_price is not None:
        mark_price = float(mark_price)
        if side_raw == "long":
            unrealized_pnl = (mark_price - entry_price) * size
        else:
            unrealized_pnl = (entry_price - mark_price) * size
    else:
        unrealized_pnl = data.get("unrealized_pnl")
    
    return Position(
        symbol=data.get("symbol", ""),
        side=side,
        size=size,
        entry_price=entry_price,
        mark_price=mark_price,
        unrealized_pnl=unrealized_pnl,
        leverage=int(data.get("leverage", 1)),
        margin=float(margin) if margin else None,
        liquidation_price=data.get("liquidation_price"),
        take_profit=float(take_profit) if take_profit else None,
        stop_loss=float(stop_loss) if stop_loss else None,
        opened_at=opened_at,
        open_run_id=data.get("open_run_id"),
    )


def parse_account(account_data: Dict[str, Any]) -> AccountSummary:
    """解析账户数据，兼容多种字段命名格式"""
    total_balance = float(
        account_data.get("total_balance", 0) or 
        account_data.get("balance", 0) or 
        account_data.get("equity", 0) or 0
    )
    
    available_balance = float(
        account_data.get("available_balance", 0) or 
        account_data.get("equity", 0) or 
        account_data.get("balance", 0) or 0
    )
    
    unrealized_pnl = float(account_data.get("unrealized_pnl", 0) or 0)
    
    margin_used = float(
        account_data.get("margin_used", 0) or 
        account_data.get("reserved_margin_sum", 0) or 0
    )
    
    margin_ratio = account_data.get("margin_ratio")
    if margin_ratio is None and total_balance > 0 and margin_used > 0:
        margin_ratio = margin_used / total_balance
    
    return AccountSummary(
        total_balance=total_balance,
        available_balance=available_balance,
        unrealized_pnl=unrealized_pnl,
        margin_used=margin_used,
        margin_ratio=margin_ratio,
    )


@router.get("", response_model=PositionsResponse)
async def get_positions():
    """获取当前持仓"""
    agent_config = get_config("agent")
    trade_state_path = BASE_DIR / agent_config.get("trade_state_path", "modules/data/trade_state.json")
    
    data = await load_json_file(trade_state_path)
    positions_data = data.get("positions", [])
    
    open_positions = [p for p in positions_data if p.get("status") == "open"]
    positions = [parse_position(p) for p in open_positions]
    
    return PositionsResponse(positions=positions, total=len(positions))


@router.get("/history", response_model=PositionHistoryResponse)
async def get_position_history(
    limit: int = Query(default=50, ge=1, le=500, description="返回的记录数量"),
):
    """获取历史持仓"""
    agent_config = get_config("agent")
    history_path = BASE_DIR / agent_config.get("position_history_path", "modules/data/position_history.json")
    
    data = load_position_history(str(history_path))
    positions_data = data.get("positions", [])
    
    sorted_positions = sorted(
        positions_data,
        key=lambda x: x.get("close_time", ""),
        reverse=True
    )[:limit]
    
    positions = []
    total_pnl = 0.0
    
    for p in sorted_positions:
        side = p.get("side", "long").upper()
        realized_pnl = float(p.get("realized_pnl", 0))
        total_pnl += realized_pnl
        
        positions.append(PositionHistoryEntry(
            symbol=p.get("symbol", ""),
            side=side,
            size=float(p.get("qty", p.get("size", 0))),
            entry_price=float(p.get("entry_price", 0)),
            exit_price=float(p.get("close_price", p.get("exit_price", 0))),
            realized_pnl=realized_pnl,
            pnl_percent=float(p.get("pnl_percent", 0)),
            opened_at=p.get("open_time", p.get("opened_at", "")),
            closed_at=p.get("close_time", p.get("closed_at", "")),
            close_reason=p.get("close_reason"),
            open_run_id=p.get("open_run_id"),
            close_run_id=p.get("close_run_id"),
        ))
    
    return PositionHistoryResponse(
        positions=positions,
        total=len(positions),
        total_pnl=total_pnl,
    )


@router.get("/trade-state", response_model=TradeStateResponse)
async def get_trade_state():
    """获取完整交易状态"""
    agent_config = get_config("agent")
    trade_state_path = BASE_DIR / agent_config.get("trade_state_path", "modules/data/trade_state.json")
    
    data = await load_json_file(trade_state_path)
    
    account_data = data.get("account", {})
    account = parse_account(account_data)
    
    positions_data = data.get("positions", [])
    open_positions = [p for p in positions_data if p.get("status") == "open"]
    positions = [parse_position(p) for p in open_positions]
    
    pending_orders = data.get("pending_orders", [])
    
    return TradeStateResponse(
        account=account,
        positions=positions,
        pending_orders=pending_orders,
    )


@router.get("/summary")
async def get_positions_summary():
    """获取持仓摘要统计"""
    agent_config = get_config("agent")
    trade_state_path = BASE_DIR / agent_config.get("trade_state_path", "modules/data/trade_state.json")
    history_path = BASE_DIR / agent_config.get("position_history_path", "modules/data/position_history.json")
    
    trade_data, history_data = await asyncio.gather(
        load_json_file(trade_state_path),
        load_json_file(history_path),
    )
    
    positions_data = trade_data.get("positions", [])
    open_positions = [p for p in positions_data if p.get("status") == "open"]
    history = history_data.get("positions", [])
    
    total_unrealized_pnl = 0.0
    for p in open_positions:
        entry_price = float(p.get("entry_price", 0))
        mark_price = float(p.get("latest_mark_price", 0) or p.get("mark_price", 0) or entry_price)
        size = float(p.get("qty", 0) or p.get("size", 0))
        side = p.get("side", "long").lower()
        
        if side == "long":
            pnl = (mark_price - entry_price) * size
        else:
            pnl = (entry_price - mark_price) * size
        total_unrealized_pnl += pnl
    
    total_realized_pnl = sum(float(p.get("realized_pnl", 0)) for p in history)
    
    win_count = sum(1 for p in history if float(p.get("realized_pnl", 0)) > 0)
    loss_count = sum(1 for p in history if float(p.get("realized_pnl", 0)) < 0)
    total_trades = len(history)
    win_rate = (win_count / total_trades) if total_trades > 0 else 0
    
    return {
        "open_positions": len(open_positions),
        "total_trades": total_trades,
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": round(win_rate, 4),
        "total_unrealized_pnl": round(total_unrealized_pnl, 4),
        "total_realized_pnl": round(total_realized_pnl, 4),
    }
