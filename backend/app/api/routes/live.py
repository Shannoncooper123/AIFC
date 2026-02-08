"""实盘交易 API 路由

提供实盘交易引擎的 API 接口：
- 交易配置管理（保证金、杠杆、反向模式开关等）
- 持仓查询和管理
- 挂单查询和撤销
- 交易历史和统计
- Workflow 管理（K线触发的自动分析）
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/live", tags=["live"])


class TradingConfigUpdate(BaseModel):
    """交易配置更新请求"""
    reverse_enabled: Optional[bool] = Field(None, description="是否启用反向模式")
    fixed_margin_usdt: Optional[float] = Field(None, ge=1, le=100000, description="固定保证金(USDT)")
    fixed_leverage: Optional[int] = Field(None, ge=1, le=125, description="固定杠杆倍数")
    expiration_days: Optional[int] = Field(None, ge=1, le=30, description="条件单过期天数")
    max_positions: Optional[int] = Field(None, ge=1, le=100, description="最大持仓数")


def _ensure_live_engine_initialized():
    """确保 live_engine 已初始化"""
    from modules.agent.engine import get_engine, set_engine
    from modules.config.settings import get_config

    live_engine = get_engine()
    if live_engine is None:
        cfg = get_config()
        from modules.agent.live_engine import BinanceLiveEngine
        live_engine = BinanceLiveEngine(cfg)
        set_engine(live_engine)
        live_engine.start()
        logger.info("[LiveAPI] 已自动初始化 live_engine")
    return live_engine


def _get_live_engine(raise_if_none: bool = True):
    """获取实盘交易引擎实例

    Args:
        raise_if_none: 如果引擎未初始化是否抛出异常，默认 True

    Returns:
        引擎实例或 None
    """
    from modules.agent.engine import get_engine
    engine = get_engine()
    if engine is None and raise_if_none:
        raise HTTPException(status_code=503, detail="交易引擎未初始化，请先启动引擎")
    return engine


@router.get("/config")
async def get_trading_config() -> Dict[str, Any]:
    """获取交易配置"""
    from modules.agent.live_engine.config import get_trading_config_manager
    config_mgr = get_trading_config_manager()
    return config_mgr.get_dict()


@router.post("/config")
async def update_trading_config(config: TradingConfigUpdate) -> Dict[str, Any]:
    """更新交易配置"""
    from modules.agent.live_engine.config import get_trading_config_manager
    config_mgr = get_trading_config_manager()
    update_data = {k: v for k, v in config.model_dump().items() if v is not None}
    config_mgr.update(**update_data)
    return config_mgr.get_dict()


@router.get("/positions")
async def get_positions(source: Optional[str] = Query(None, description="数据来源过滤: live/reverse")) -> Dict[str, Any]:
    """获取持仓列表"""
    try:
        engine = _get_live_engine(raise_if_none=False)
        if engine is None:
            return {"positions": [], "total": 0, "engine_running": False}

        if source:
            positions = engine.get_positions_summary_by_source(source)
        else:
            positions = engine.get_positions_summary()
        return {
            "positions": positions,
            "total": len(positions),
            "engine_running": True
        }
    except Exception as e:
        logger.error(f"获取持仓失败: {e}")
        return {"positions": [], "total": 0, "engine_running": False}


@router.delete("/positions/{record_id}")
async def close_position(record_id: str) -> Dict[str, Any]:
    """关闭指定持仓"""
    engine = _get_live_engine()
    success = engine.close_record(record_id)
    if success:
        return {"success": True, "message": f"持仓 {record_id} 已关闭"}
    else:
        raise HTTPException(status_code=400, detail=f"关闭持仓 {record_id} 失败")


@router.delete("/positions/symbol/{symbol}")
async def close_positions_by_symbol(symbol: str, source: Optional[str] = None) -> Dict[str, Any]:
    """关闭指定交易对的所有持仓"""
    engine = _get_live_engine()
    count = engine.close_all_records_by_symbol(symbol.upper(), source=source)
    return {
        "success": True,
        "message": f"已关闭 {symbol} 的 {count} 条持仓",
        "closed_count": count
    }


@router.get("/pending-orders")
async def get_pending_orders(source: Optional[str] = Query(None, description="数据来源过滤: live/reverse")) -> Dict[str, Any]:
    """获取待触发订单（条件单和限价单）"""
    try:
        engine = _get_live_engine(raise_if_none=False)
        if engine is None:
            return {"orders": [], "total": 0, "total_conditional": 0, "total_limit": 0, "engine_running": False}

        summary = engine.get_pending_orders_summary(source=source)
        all_orders = summary.get('conditional_orders', []) + summary.get('limit_orders', [])
        return {
            "orders": all_orders,
            "total": len(all_orders),
            "total_conditional": summary.get('total_conditional', 0),
            "total_limit": summary.get('total_limit', 0),
            "engine_running": True
        }
    except Exception as e:
        logger.error(f"获取挂单失败: {e}")
        return {"orders": [], "total": 0, "total_conditional": 0, "total_limit": 0, "engine_running": False}


@router.delete("/pending-orders/{order_id}")
async def cancel_pending_order(order_id: str) -> Dict[str, Any]:
    """撤销待触发订单"""
    engine = _get_live_engine()
    success = engine.cancel_pending_order(order_id)
    if success:
        order_type = "限价单" if order_id.startswith('LIMIT_') else "条件单"
        return {"success": True, "message": f"{order_type} {order_id} 已撤销"}
    else:
        raise HTTPException(status_code=400, detail=f"撤销订单 {order_id} 失败")


@router.get("/history")
async def get_history(
    limit: int = Query(default=50, ge=1, le=1000, description="返回的记录数量"),
    source: Optional[str] = Query(None, description="数据来源过滤: live/reverse")
) -> Dict[str, Any]:
    """获取交易历史"""
    try:
        engine = _get_live_engine(raise_if_none=False)
        if engine is None:
            return {"history": [], "total": 0, "engine_running": False}

        if source:
            history = engine.get_history_by_source(source, limit)
        else:
            history = engine.get_history(limit)
        return {
            "history": history,
            "total": len(history),
            "engine_running": True
        }
    except Exception as e:
        logger.error(f"获取历史失败: {e}")
        return {"history": [], "total": 0, "engine_running": False}


@router.get("/statistics")
async def get_statistics(source: Optional[str] = Query(None, description="数据来源过滤: live/reverse")) -> Dict[str, Any]:
    """获取交易统计"""
    empty_stats = {
        "total_trades": 0,
        "winning_trades": 0,
        "losing_trades": 0,
        "win_rate": 0.0,
        "total_pnl": 0.0,
        "avg_pnl": 0.0,
        "max_profit": 0.0,
        "max_loss": 0.0,
        "open_count": 0,
        "total_commission": 0.0,
        "engine_running": False
    }
    try:
        engine = _get_live_engine(raise_if_none=False)
        if engine is None:
            return empty_stats

        if source:
            stats = engine.get_statistics_by_source(source)
        else:
            stats = engine.get_statistics()
        stats["engine_running"] = True
        return stats
    except Exception as e:
        logger.error(f"获取统计失败: {e}")
        return empty_stats


@router.get("/summary")
async def get_summary() -> Dict[str, Any]:
    """获取实盘交易汇总信息"""
    from modules.agent.live_engine.config import get_trading_config_manager
    config_mgr = get_trading_config_manager()

    try:
        engine = _get_live_engine(raise_if_none=False)
        if engine is None:
            return {
                "engine_running": False,
                "reverse_enabled": config_mgr.reverse_enabled,
                "config": config_mgr.get_dict(),
                "pending_orders_count": 0,
                "positions_count": 0,
                "statistics": {}
            }

        open_records = engine.position_manager.get_open_records()
        pending_summary = engine.get_pending_orders_summary()

        return {
            "engine_running": True,
            "reverse_enabled": config_mgr.reverse_enabled,
            "config": config_mgr.get_dict(),
            "pending_orders_count": pending_summary.get('total_conditional', 0) + pending_summary.get('total_limit', 0),
            "positions_count": len(open_records),
            "statistics": engine.get_statistics()
        }
    except Exception as e:
        logger.error(f"获取汇总失败: {e}")
        from modules.agent.live_engine.config import get_trading_config_manager
        config_mgr = get_trading_config_manager()
        return {
            "engine_running": False,
            "reverse_enabled": config_mgr.reverse_enabled,
            "config": config_mgr.get_dict(),
            "pending_orders_count": 0,
            "positions_count": 0,
            "statistics": {}
        }


@router.post("/start")
async def start_engine() -> Dict[str, Any]:
    """启动实盘交易引擎"""
    try:
        _ensure_live_engine_initialized()
        return {"success": True, "message": "实盘交易引擎已启动"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"启动引擎失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop")
async def stop_engine() -> Dict[str, Any]:
    """停止实盘交易引擎"""
    try:
        from modules.agent.engine import get_engine
        engine = get_engine()
        if engine:
            engine.stop()
        return {"success": True, "message": "实盘交易引擎已停止"}
    except Exception as e:
        logger.error(f"停止引擎失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workflow/start/{symbol}")
async def start_symbol_workflow(symbol: str, interval: str = "15m") -> Dict[str, Any]:
    """启动指定币种的 workflow 分析

    每根K线收盘时触发 workflow 分析。
    """
    try:
        _ensure_live_engine_initialized()

        from modules.agent.workflow_runner import get_workflow_manager
        workflow_mgr = get_workflow_manager()

        success = workflow_mgr.start_symbol(symbol.upper(), interval)

        if success:
            return {
                "success": True,
                "message": f"已启动 {symbol} @ {interval} 的 workflow 分析",
                "symbol": symbol.upper(),
                "interval": interval,
            }
        else:
            raise HTTPException(status_code=400, detail=f"启动 {symbol} workflow 失败，可能已在运行")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"启动 {symbol} workflow 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workflow/stop/{symbol}")
async def stop_symbol_workflow(symbol: str) -> Dict[str, Any]:
    """停止指定币种的 workflow 分析"""
    try:
        from modules.agent.workflow_runner import get_workflow_manager
        workflow_mgr = get_workflow_manager()

        success = workflow_mgr.stop_symbol(symbol.upper())

        if success:
            return {
                "success": True,
                "message": f"已停止 {symbol} 的 workflow 分析",
                "symbol": symbol.upper(),
            }
        else:
            raise HTTPException(status_code=400, detail=f"{symbol} workflow 未在运行")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"停止 {symbol} workflow 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workflow/status")
async def get_workflow_status(symbol: Optional[str] = None) -> Dict[str, Any]:
    """获取 workflow 运行状态"""
    try:
        from modules.agent.workflow_runner import get_workflow_manager
        workflow_mgr = get_workflow_manager()
        return workflow_mgr.get_status(symbol.upper() if symbol else None)
    except Exception as e:
        logger.error(f"获取 workflow 状态失败: {e}", exc_info=True)
        return {
            "running_count": 0,
            "symbols": {},
        }


@router.get("/workflow/running")
async def get_running_workflows() -> Dict[str, Any]:
    """获取正在运行 workflow 的币种列表"""
    try:
        from modules.agent.workflow_runner import get_workflow_manager
        workflow_mgr = get_workflow_manager()
        symbols = workflow_mgr.get_running_symbols()
        return {
            "count": len(symbols),
            "symbols": symbols,
        }
    except Exception as e:
        logger.error(f"获取运行中的 workflow 失败: {e}", exc_info=True)
        return {
            "count": 0,
            "symbols": [],
        }
