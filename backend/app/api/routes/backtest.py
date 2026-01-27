"""回测 API 路由"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.core.config import BASE_DIR, get_config
from modules.backtest.engine.backtest_engine import (
    BacktestEngine,
    get_active_backtest,
    register_backtest,
    unregister_backtest,
    list_active_backtests,
)
from modules.backtest.models import BacktestConfig, BacktestProgress, BacktestStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


class BacktestStartRequest(BaseModel):
    """启动回测请求"""
    symbols: List[str] = Field(default=["BTCUSDT", "ETHUSDT"], description="回测币种列表")
    start_time: str = Field(..., description="开始时间 (ISO格式)")
    end_time: str = Field(..., description="结束时间 (ISO格式)")
    interval: str = Field(default="15m", description="K线周期")
    initial_balance: float = Field(default=10000.0, description="初始资金")
    concurrency: int = Field(default=5, ge=1, le=50, description="并发数量")


class BacktestStartResponse(BaseModel):
    """启动回测响应"""
    backtest_id: str
    status: str
    message: str


class BacktestStatusResponse(BaseModel):
    """回测状态响应"""
    backtest_id: str
    status: str
    progress: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None


class BacktestListItem(BaseModel):
    """回测列表项"""
    backtest_id: str
    status: str
    config: Dict[str, Any]
    start_timestamp: str
    end_timestamp: Optional[str] = None
    total_trades: int = 0
    total_pnl: float = 0.0
    win_rate: float = 0.0


class BacktestListResponse(BaseModel):
    """回测列表响应"""
    backtests: List[BacktestListItem]
    total: int


_progress_subscribers: Dict[str, List[asyncio.Queue]] = {}


def _on_progress(backtest_id: str, progress: BacktestProgress) -> None:
    """进度回调 - 通知所有订阅者"""
    if backtest_id in _progress_subscribers:
        for queue in _progress_subscribers[backtest_id]:
            try:
                queue.put_nowait(progress.to_dict())
            except asyncio.QueueFull:
                pass


def _on_complete(backtest_id: str, result) -> None:
    """完成回调 - 通知所有订阅者并清理"""
    if backtest_id in _progress_subscribers:
        for queue in _progress_subscribers[backtest_id]:
            try:
                queue.put_nowait({"type": "complete", "result": result.to_dict()})
            except asyncio.QueueFull:
                pass
    
    unregister_backtest(backtest_id)


@router.post("/start", response_model=BacktestStartResponse)
async def start_backtest(request: BacktestStartRequest):
    """启动回测"""
    try:
        start_time = datetime.fromisoformat(request.start_time.replace('Z', '+00:00'))
        end_time = datetime.fromisoformat(request.end_time.replace('Z', '+00:00'))
        
        if start_time >= end_time:
            raise HTTPException(status_code=400, detail="开始时间必须早于结束时间")
        
        if (end_time - start_time).days > 730:
            raise HTTPException(status_code=400, detail="回测时间范围不能超过2年（730天）")
        
        config = BacktestConfig(
            symbols=request.symbols,
            start_time=start_time,
            end_time=end_time,
            interval=request.interval,
            initial_balance=request.initial_balance,
            concurrency=request.concurrency,
        )
        
        engine = BacktestEngine(
            config=config,
            on_progress=lambda p: _on_progress(engine.backtest_id, p),
            on_complete=lambda r: _on_complete(engine.backtest_id, r),
        )
        
        register_backtest(engine)
        backtest_id = engine.start()
        
        logger.info(f"回测已启动: backtest_id={backtest_id}")
        
        return BacktestStartResponse(
            backtest_id=backtest_id,
            status="running",
            message="回测已启动",
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"时间格式错误: {str(e)}")
    except Exception as e:
        logger.error(f"启动回测失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"启动回测失败: {str(e)}")


@router.get("/{backtest_id}/status", response_model=BacktestStatusResponse)
async def get_backtest_status(backtest_id: str):
    """获取回测状态"""
    engine = get_active_backtest(backtest_id)
    
    if engine:
        result = engine.get_result()
        progress_data = None
        
        if result.status == BacktestStatus.RUNNING:
            total_steps = result.total_klines_analyzed or 1
            completed_steps = len(result.workflow_runs)
            progress_percent = min((completed_steps / total_steps) * 100, 100) if total_steps > 0 else 0
            
            progress_data = {
                "current_time": result.trades[-1].kline_time.isoformat() if result.trades else None,
                "total_steps": total_steps,
                "completed_steps": completed_steps,
                "progress_percent": round(progress_percent, 2),
                "current_step_info": f"已完成 {completed_steps}/{total_steps} 步, 交易 {len(result.trades)} 笔",
                "completed_batches": completed_steps,
                "total_batches": total_steps,
                "total_trades": len(result.trades),
                "winning_trades": sum(1 for t in result.trades if t.realized_pnl > 0),
                "losing_trades": sum(1 for t in result.trades if t.realized_pnl < 0),
                "total_pnl": round(sum(t.realized_pnl for t in result.trades), 2),
                "win_rate": round(sum(1 for t in result.trades if t.realized_pnl > 0) / len(result.trades), 4) if result.trades else 0,
            }
        
        return BacktestStatusResponse(
            backtest_id=backtest_id,
            status=result.status.value,
            progress=progress_data,
            result=result.to_dict() if result.status != BacktestStatus.RUNNING else None,
        )
    
    agent_config = get_config("agent")
    base_dir = BASE_DIR / agent_config.get("data_dir", "modules/data")
    result_path = base_dir / "backtest" / backtest_id / "result.json"
    
    if result_path.exists():
        try:
            with open(result_path, 'r', encoding='utf-8') as f:
                result_data = json.load(f)
            return BacktestStatusResponse(
                backtest_id=backtest_id,
                status=result_data.get("status", "unknown"),
                result=result_data,
            )
        except Exception as e:
            logger.error(f"读取回测结果失败: {e}")
    
    raise HTTPException(status_code=404, detail=f"回测不存在: {backtest_id}")


@router.post("/{backtest_id}/stop")
async def stop_backtest(backtest_id: str):
    """停止回测"""
    engine = get_active_backtest(backtest_id)
    
    if not engine:
        raise HTTPException(status_code=404, detail=f"回测不存在或已完成: {backtest_id}")
    
    engine.stop()
    
    return {"message": "已请求停止回测", "backtest_id": backtest_id}


@router.get("/list", response_model=BacktestListResponse)
async def list_backtests(
    limit: int = Query(default=20, ge=1, le=100),
    status_filter: Optional[str] = Query(default=None),
):
    """列出所有回测"""
    backtests: List[BacktestListItem] = []
    
    for bt_id in list_active_backtests():
        engine = get_active_backtest(bt_id)
        if engine:
            result = engine.get_result()
            backtests.append(BacktestListItem(
                backtest_id=bt_id,
                status=result.status.value,
                config=result.config.to_dict(),
                start_timestamp=result.start_timestamp.isoformat(),
                end_timestamp=result.end_timestamp.isoformat() if result.end_timestamp else None,
                total_trades=result.total_trades,
                total_pnl=result.total_pnl,
                win_rate=result.win_rate,
            ))
    
    agent_config = get_config("agent")
    base_dir = BASE_DIR / agent_config.get("data_dir", "modules/data")
    backtest_dir = base_dir / "backtest"
    
    if backtest_dir.exists():
        for item in sorted(backtest_dir.iterdir(), reverse=True):
            if item.is_dir() and item.name.startswith("bt_"):
                if item.name in [b.backtest_id for b in backtests]:
                    continue
                
                result_path = item / "result.json"
                if result_path.exists():
                    try:
                        with open(result_path, 'r', encoding='utf-8') as f:
                            result_data = json.load(f)
                        
                        if status_filter and result_data.get("status") != status_filter:
                            continue
                        
                        backtests.append(BacktestListItem(
                            backtest_id=item.name,
                            status=result_data.get("status", "unknown"),
                            config=result_data.get("config", {}),
                            start_timestamp=result_data.get("start_timestamp", ""),
                            end_timestamp=result_data.get("end_timestamp"),
                            total_trades=result_data.get("total_trades", 0),
                            total_pnl=result_data.get("total_pnl", 0),
                            win_rate=result_data.get("win_rate", 0),
                        ))
                    except Exception as e:
                        logger.warning(f"读取回测结果失败 {item.name}: {e}")
            
            if len(backtests) >= limit:
                break
    
    return BacktestListResponse(
        backtests=backtests[:limit],
        total=len(backtests),
    )


@router.get("/{backtest_id}/positions")
async def get_backtest_positions(backtest_id: str):
    """获取回测的当前持仓"""
    agent_config = get_config("agent")
    base_dir = BASE_DIR / agent_config.get("data_dir", "modules/data")
    state_path = base_dir / "backtest" / backtest_id / "trade_state.json"
    
    if not state_path.exists():
        raise HTTPException(status_code=404, detail=f"回测不存在: {backtest_id}")
    
    try:
        with open(state_path, 'r', encoding='utf-8') as f:
            state_data = json.load(f)
        
        positions = state_data.get("positions", [])
        open_positions = [p for p in positions if p.get("status") == "open"]
        
        return {
            "backtest_id": backtest_id,
            "positions": open_positions,
            "total": len(open_positions),
        }
    except Exception as e:
        logger.error(f"读取回测持仓失败: {e}")
        raise HTTPException(status_code=500, detail=f"读取回测持仓失败: {str(e)}")


@router.get("/{backtest_id}/history")
async def get_backtest_history(
    backtest_id: str,
    limit: int = Query(default=50, ge=1, le=500),
):
    """获取回测的历史交易记录"""
    agent_config = get_config("agent")
    base_dir = BASE_DIR / agent_config.get("data_dir", "modules/data")
    history_path = base_dir / "backtest" / backtest_id / "position_history.jsonl"
    
    if not history_path.exists():
        return {
            "backtest_id": backtest_id,
            "positions": [],
            "total": 0,
            "total_pnl": 0,
        }
    
    try:
        positions = []
        total_pnl = 0.0
        
        with open(history_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    positions.append(record)
                    total_pnl += record.get("realized_pnl", 0)
                except json.JSONDecodeError:
                    continue
        
        positions.sort(key=lambda x: x.get("close_time", ""), reverse=True)
        
        return {
            "backtest_id": backtest_id,
            "positions": positions[:limit],
            "total": len(positions),
            "total_pnl": round(total_pnl, 4),
        }
    except Exception as e:
        logger.error(f"读取回测历史失败: {e}")
        raise HTTPException(status_code=500, detail=f"读取回测历史失败: {str(e)}")


@router.get("/{backtest_id}/trades")
async def get_backtest_trades(
    backtest_id: str,
    limit: int = Query(default=100, ge=1, le=500),
):
    """获取回测的交易记录（独立执行模式）"""
    engine = get_active_backtest(backtest_id)
    
    if engine:
        result = engine.get_result()
        trades = [t.to_dict() for t in result.trades[-limit:]]
        return {
            "backtest_id": backtest_id,
            "trades": trades,
            "total": len(result.trades),
            "stats": {
                "total_trades": result.total_trades,
                "winning_trades": result.winning_trades,
                "losing_trades": result.losing_trades,
                "win_rate": round(result.win_rate, 4),
                "profit_factor": round(result.profit_factor, 2),
                "avg_win": round(result.avg_win, 4),
                "avg_loss": round(result.avg_loss, 4),
                "total_pnl": round(result.total_pnl, 4),
            }
        }
    
    agent_config = get_config("agent")
    base_dir = BASE_DIR / agent_config.get("data_dir", "modules/data")
    result_path = base_dir / "backtest" / backtest_id / "result.json"
    
    if result_path.exists():
        try:
            with open(result_path, 'r', encoding='utf-8') as f:
                result_data = json.load(f)
            
            trades = result_data.get("trades", [])[-limit:]
            return {
                "backtest_id": backtest_id,
                "trades": trades,
                "total": len(result_data.get("trades", [])),
                "stats": {
                    "total_trades": result_data.get("total_trades", 0),
                    "winning_trades": result_data.get("winning_trades", 0),
                    "losing_trades": result_data.get("losing_trades", 0),
                    "win_rate": result_data.get("win_rate", 0),
                    "profit_factor": result_data.get("profit_factor", 0),
                    "avg_win": result_data.get("avg_win", 0),
                    "avg_loss": result_data.get("avg_loss", 0),
                    "total_pnl": result_data.get("total_pnl", 0),
                }
            }
        except Exception as e:
            logger.error(f"读取回测交易记录失败: {e}")
    
    raise HTTPException(status_code=404, detail=f"回测不存在: {backtest_id}")


@router.delete("/{backtest_id}")
async def delete_backtest(backtest_id: str):
    """删除回测"""
    engine = get_active_backtest(backtest_id)
    if engine and engine.is_running():
        raise HTTPException(status_code=400, detail="无法删除正在运行的回测")
    
    agent_config = get_config("agent")
    base_dir = BASE_DIR / agent_config.get("data_dir", "modules/data")
    backtest_path = base_dir / "backtest" / backtest_id
    
    if not backtest_path.exists():
        raise HTTPException(status_code=404, detail=f"回测不存在: {backtest_id}")
    
    try:
        import shutil
        shutil.rmtree(backtest_path)
        
        if engine:
            unregister_backtest(backtest_id)
        
        return {"message": "回测已删除", "backtest_id": backtest_id}
    except Exception as e:
        logger.error(f"删除回测失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除回测失败: {str(e)}")


@router.websocket("/ws/{backtest_id}")
async def backtest_websocket(websocket: WebSocket, backtest_id: str):
    """回测进度 WebSocket"""
    await websocket.accept()
    
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    
    if backtest_id not in _progress_subscribers:
        _progress_subscribers[backtest_id] = []
    _progress_subscribers[backtest_id].append(queue)
    
    try:
        while True:
            try:
                data = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_json(data)
                
                if isinstance(data, dict) and data.get("type") == "complete":
                    break
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        logger.info(f"WebSocket 断开: backtest_id={backtest_id}")
    finally:
        if backtest_id in _progress_subscribers:
            _progress_subscribers[backtest_id].remove(queue)
            if not _progress_subscribers[backtest_id]:
                del _progress_subscribers[backtest_id]
