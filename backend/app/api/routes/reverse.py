"""反向交易 API 路由"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reverse", tags=["reverse"])


class ReverseConfigUpdate(BaseModel):
    """反向交易配置更新请求"""
    enabled: Optional[bool] = None
    fixed_margin_usdt: Optional[float] = Field(None, ge=10, le=10000)
    fixed_leverage: Optional[int] = Field(None, ge=1, le=125)
    expiration_days: Optional[int] = Field(None, ge=1, le=30)
    max_positions: Optional[int] = Field(None, ge=1, le=100)


class ReversePosition(BaseModel):
    """反向交易持仓"""
    symbol: str
    side: str
    size: float
    entry_price: float
    mark_price: Optional[float] = None
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    roe: Optional[float] = None
    leverage: int
    margin: float
    opened_at: Optional[str] = None
    algo_order_id: Optional[str] = None
    agent_order_id: Optional[str] = None


class ReversePendingOrder(BaseModel):
    """反向交易待触发条件单"""
    algo_id: str
    symbol: str
    side: str
    trigger_price: float
    quantity: float
    status: str
    tp_price: Optional[float] = None
    sl_price: Optional[float] = None
    leverage: int
    margin_usdt: float
    created_at: str
    expires_at: Optional[str] = None
    agent_order_id: Optional[str] = None
    agent_side: Optional[str] = None


class ReverseHistoryEntry(BaseModel):
    """反向交易历史记录"""
    id: str
    symbol: str
    side: str
    qty: float
    entry_price: float
    exit_price: float
    leverage: int
    margin_usdt: float
    realized_pnl: float
    pnl_percent: float
    open_time: str
    close_time: str
    close_reason: str
    algo_order_id: Optional[str] = None
    agent_order_id: Optional[str] = None


def _get_reverse_engine():
    """获取反向交易引擎实例"""
    from modules.agent.engine import get_reverse_engine
    engine = get_reverse_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="反向交易引擎未初始化")
    return engine


@router.get("/config")
async def get_reverse_config() -> Dict[str, Any]:
    """获取反向交易配置"""
    try:
        engine = _get_reverse_engine()
        return engine.get_config()
    except HTTPException:
        from modules.agent.reverse_engine.config import ConfigManager
        config_manager = ConfigManager()
        return config_manager.get_dict()


@router.post("/config")
async def update_reverse_config(config: ReverseConfigUpdate) -> Dict[str, Any]:
    """更新反向交易配置"""
    try:
        engine = _get_reverse_engine()
        update_data = {k: v for k, v in config.model_dump().items() if v is not None}
        return engine.update_config(**update_data)
    except HTTPException:
        from modules.agent.reverse_engine.config import ConfigManager
        config_manager = ConfigManager()
        update_data = {k: v for k, v in config.model_dump().items() if v is not None}
        updated = config_manager.update(**update_data)
        return updated.to_dict()


@router.get("/positions")
async def get_reverse_positions() -> Dict[str, Any]:
    """获取反向交易持仓"""
    try:
        engine = _get_reverse_engine()
        positions = engine.get_positions_summary()
        return {
            "positions": positions,
            "total": len(positions)
        }
    except HTTPException:
        return {"positions": [], "total": 0}


@router.get("/pending-orders")
async def get_reverse_pending_orders() -> Dict[str, Any]:
    """获取待触发的条件单"""
    try:
        engine = _get_reverse_engine()
        return engine.get_pending_orders_summary()
    except HTTPException:
        return {"total": 0, "orders": []}


@router.delete("/pending-orders/{algo_id}")
async def cancel_reverse_pending_order(algo_id: str) -> Dict[str, Any]:
    """撤销待触发的条件单"""
    engine = _get_reverse_engine()
    success = engine.cancel_pending_order(algo_id)
    if success:
        return {"success": True, "message": f"条件单 {algo_id} 已撤销"}
    else:
        raise HTTPException(status_code=400, detail=f"撤销条件单 {algo_id} 失败")


@router.get("/history")
async def get_reverse_history(
    limit: int = Query(default=50, ge=1, le=500, description="返回的记录数量")
) -> Dict[str, Any]:
    """获取反向交易历史"""
    try:
        engine = _get_reverse_engine()
        history = engine.get_history(limit)
        return {
            "history": history,
            "total": len(history)
        }
    except HTTPException:
        return {"history": [], "total": 0}


@router.get("/statistics")
async def get_reverse_statistics() -> Dict[str, Any]:
    """获取反向交易统计信息"""
    try:
        engine = _get_reverse_engine()
        return engine.get_statistics()
    except HTTPException:
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "avg_pnl": 0.0,
            "max_profit": 0.0,
            "max_loss": 0.0
        }


@router.get("/summary")
async def get_reverse_summary() -> Dict[str, Any]:
    """获取反向交易引擎汇总信息"""
    try:
        engine = _get_reverse_engine()
        return engine.get_summary()
    except HTTPException:
        from modules.agent.reverse_engine.config import ConfigManager
        config_manager = ConfigManager()
        return {
            "enabled": config_manager.enabled,
            "config": config_manager.get_dict(),
            "pending_orders_count": 0,
            "positions_count": 0,
            "statistics": {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0,
                "avg_pnl": 0.0,
                "max_profit": 0.0,
                "max_loss": 0.0
            }
        }


@router.post("/start")
async def start_reverse_engine_api() -> Dict[str, Any]:
    """启动反向交易引擎"""
    try:
        from modules.agent.engine import get_reverse_engine, init_reverse_engine, start_reverse_engine
        from modules.config.settings import get_config
        
        engine = get_reverse_engine()
        if engine is None:
            config = get_config()
            engine = init_reverse_engine(config)
        
        if engine:
            start_reverse_engine()
            return {"success": True, "message": "反向交易引擎已启动"}
        else:
            raise HTTPException(status_code=400, detail="反向交易引擎未启用")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"启动反向交易引擎失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop")
async def stop_reverse_engine_api() -> Dict[str, Any]:
    """停止反向交易引擎"""
    try:
        from modules.agent.engine import stop_reverse_engine
        stop_reverse_engine()
        return {"success": True, "message": "反向交易引擎已停止"}
    except Exception as e:
        logger.error(f"停止反向交易引擎失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _get_or_init_reverse_engine():
    """获取或初始化反向交易引擎实例"""
    from modules.agent.engine import get_reverse_engine, init_reverse_engine
    from modules.config.settings import get_config
    
    engine = get_reverse_engine()
    if engine is None:
        config = get_config()
        engine = init_reverse_engine(config)
    return engine


@router.post("/workflow/start/{symbol}")
async def start_symbol_workflow(symbol: str, interval: str = "15m") -> Dict[str, Any]:
    """启动指定币种的 workflow 分析
    
    每根K线收盘时触发 workflow 分析，Agent 开仓后自动创建反向条件单。
    
    Args:
        symbol: 交易对（如 BTCUSDT）
        interval: K线周期（如 15m, 1h, 4h）
    """
    try:
        engine = _get_or_init_reverse_engine()
        if engine is None:
            raise HTTPException(status_code=503, detail="反向交易引擎初始化失败")
        
        success = engine.start_symbol_workflow(symbol.upper(), interval)
        
        if success:
            return {
                "success": True,
                "message": f"已启动 {symbol} @ {interval} 的 workflow 分析",
                "symbol": symbol.upper(),
                "interval": interval,
            }
        else:
            raise HTTPException(status_code=400, detail=f"启动 {symbol} workflow 失败，请先在配置中启用反向交易引擎")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"启动 {symbol} workflow 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workflow/stop/{symbol}")
async def stop_symbol_workflow(symbol: str) -> Dict[str, Any]:
    """停止指定币种的 workflow 分析
    
    Args:
        symbol: 交易对
    """
    try:
        engine = _get_or_init_reverse_engine()
        if engine is None:
            raise HTTPException(status_code=400, detail=f"{symbol} workflow 未在运行")
        
        success = engine.stop_symbol_workflow(symbol.upper())
        
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
    """获取 workflow 运行状态
    
    Args:
        symbol: 指定币种，不传则获取所有
    """
    try:
        from modules.agent.engine import get_reverse_engine
        engine = get_reverse_engine()
        if engine is None:
            return {
                "running_count": 0,
                "symbols": {},
            }
        return engine.get_workflow_status(symbol.upper() if symbol else None)
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
        from modules.agent.engine import get_reverse_engine
        engine = get_reverse_engine()
        if engine is None:
            return {
                "count": 0,
                "symbols": [],
            }
        symbols = engine.get_running_workflows()
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
