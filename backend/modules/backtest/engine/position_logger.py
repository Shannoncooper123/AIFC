"""统一仓位记录器 - 将所有回测交易记录到单一文件中便于对账"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from modules.agent.trade_simulator.utils.file_utils import locked_append_jsonl, locked_write_json
from modules.monitor.utils.logger import get_logger

logger = get_logger('backtest.position_logger')


class PositionLogger:
    """统一仓位记录器
    
    线程安全地将所有回测交易记录到单一 JSONL 文件中，
    便于对账和分析。
    
    记录内容包括：
    - 开仓信息（时间、价格、方向、数量等）
    - 平仓信息（时间、价格、原因、盈亏等）
    - 止盈止损设置
    - workflow 运行信息
    """
    
    def __init__(self, backtest_id: str, base_dir: str = "modules/data"):
        """初始化仓位记录器
        
        Args:
            backtest_id: 回测ID
            base_dir: 数据基础目录
        """
        self.backtest_id = backtest_id
        self._lock = threading.Lock()
        
        backtest_dir = os.path.join(base_dir, "backtest", backtest_id)
        os.makedirs(backtest_dir, exist_ok=True)
        
        self._positions_file = os.path.join(backtest_dir, "all_positions.jsonl")
        self._summary_file = os.path.join(backtest_dir, "positions_summary.json")
        
        self._trade_count = 0
        self._long_count = 0
        self._short_count = 0
        self._total_pnl = 0.0
        
        header = {
            "type": "header",
            "backtest_id": backtest_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "version": "1.0",
        }
        locked_append_jsonl(self._positions_file, header, fsync=False)
        
        logger.info(f"仓位记录器初始化: {self._positions_file}")
    
    def log_trade(
        self,
        trade_id: str,
        symbol: str,
        side: str,
        entry_time: datetime,
        entry_price: float,
        exit_time: datetime,
        exit_price: float,
        exit_type: str,
        realized_pnl: float,
        qty: float,
        margin_usdt: float,
        leverage: int,
        tp_price: Optional[float] = None,
        sl_price: Optional[float] = None,
        original_tp_price: Optional[float] = None,
        original_sl_price: Optional[float] = None,
        holding_bars: int = 0,
        order_type: str = "market",
        limit_price: Optional[float] = None,
        fees_total: float = 0.0,
        r_multiple: Optional[float] = None,
        close_reason: str = "",
        workflow_run_id: str = "",
        step_index: Optional[int] = None,
        tp_distance_percent: float = 0.0,
        sl_distance_percent: float = 0.0,
        order_created_time: Optional[datetime] = None,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """记录一笔完整的交易
        
        Args:
            trade_id: 交易ID
            symbol: 交易对
            side: 方向 (long/short)
            entry_time: 入场时间
            entry_price: 入场价格
            exit_time: 出场时间
            exit_price: 出场价格
            exit_type: 出场类型 (tp/sl/timeout)
            realized_pnl: 已实现盈亏
            qty: 数量
            margin_usdt: 保证金
            leverage: 杠杆
            tp_price: 止盈价
            sl_price: 止损价
            original_tp_price: 原始止盈价
            original_sl_price: 原始止损价
            holding_bars: 持仓K线数
            order_type: 订单类型 (market/limit)
            limit_price: 限价单价格
            fees_total: 总手续费
            r_multiple: R值
            close_reason: 平仓原因
            workflow_run_id: workflow运行ID
            step_index: 步骤索引
            tp_distance_percent: 止盈距离百分比
            sl_distance_percent: 止损距离百分比
            order_created_time: 限价单创建时间
            extra_data: 额外数据
        """
        record = {
            "type": "trade",
            "trade_id": trade_id,
            "symbol": symbol,
            "side": side,
            "entry_time": entry_time.isoformat() if isinstance(entry_time, datetime) else entry_time,
            "entry_price": entry_price,
            "exit_time": exit_time.isoformat() if isinstance(exit_time, datetime) else exit_time,
            "exit_price": exit_price,
            "exit_type": exit_type,
            "realized_pnl": round(realized_pnl, 6),
            "qty": qty,
            "margin_usdt": round(margin_usdt, 4),
            "leverage": leverage,
            "notional_usdt": round(margin_usdt * leverage, 4),
            "tp_price": tp_price,
            "sl_price": sl_price,
            "original_tp_price": original_tp_price,
            "original_sl_price": original_sl_price,
            "holding_bars": holding_bars,
            "order_type": order_type,
            "limit_price": limit_price,
            "fees_total": round(fees_total, 6),
            "r_multiple": round(r_multiple, 2) if r_multiple is not None else None,
            "close_reason": close_reason,
            "workflow_run_id": workflow_run_id,
            "step_index": step_index,
            "tp_distance_percent": round(tp_distance_percent, 2),
            "sl_distance_percent": round(sl_distance_percent, 2),
            "order_created_time": order_created_time.isoformat() if isinstance(order_created_time, datetime) else order_created_time,
            "logged_at": datetime.now(timezone.utc).isoformat(),
        }
        
        if extra_data:
            record["extra"] = extra_data
        
        pnl_pct = (realized_pnl / margin_usdt * 100) if margin_usdt > 0 else 0
        record["pnl_percent"] = round(pnl_pct, 2)
        
        is_win = realized_pnl > 0
        record["is_win"] = is_win
        
        locked_append_jsonl(self._positions_file, record, fsync=False)
        
        with self._lock:
            self._trade_count += 1
            self._total_pnl += realized_pnl
            if side.lower() == 'long':
                self._long_count += 1
            else:
                self._short_count += 1
        
        win_str = "WIN" if is_win else "LOSS"
        logger.debug(
            f"[PositionLog] {symbol} {side.upper()} {win_str} | "
            f"Entry: {entry_price:.6g} -> Exit: {exit_price:.6g} | "
            f"PnL: {realized_pnl:+.4f} ({pnl_pct:+.2f}%) | "
            f"Type: {exit_type}"
        )
    
    def log_trade_from_result(self, trade_result, step_index: Optional[int] = None) -> None:
        """从 BacktestTradeResult 对象记录交易
        
        Args:
            trade_result: BacktestTradeResult 对象
            step_index: 步骤索引
        """
        self.log_trade(
            trade_id=trade_result.trade_id,
            symbol=trade_result.symbol,
            side=trade_result.side,
            entry_time=trade_result.kline_time,
            entry_price=trade_result.entry_price,
            exit_time=trade_result.exit_time,
            exit_price=trade_result.exit_price,
            exit_type=trade_result.exit_type,
            realized_pnl=trade_result.realized_pnl,
            qty=trade_result.size,
            margin_usdt=trade_result.margin_usdt,
            leverage=trade_result.leverage,
            tp_price=trade_result.tp_price,
            sl_price=trade_result.sl_price,
            original_tp_price=trade_result.original_tp_price,
            original_sl_price=trade_result.original_sl_price,
            holding_bars=trade_result.holding_bars,
            order_type=trade_result.order_type,
            limit_price=trade_result.limit_price,
            fees_total=trade_result.fees_total,
            r_multiple=trade_result.r_multiple,
            close_reason=trade_result.close_reason,
            workflow_run_id=trade_result.workflow_run_id,
            step_index=step_index,
            tp_distance_percent=trade_result.tp_distance_percent,
            sl_distance_percent=trade_result.sl_distance_percent,
            order_created_time=trade_result.order_created_time,
        )
    
    def write_summary(self) -> None:
        """写入汇总信息"""
        with self._lock:
            summary = {
                "backtest_id": self.backtest_id,
                "total_trades": self._trade_count,
                "long_trades": self._long_count,
                "short_trades": self._short_count,
                "total_pnl": round(self._total_pnl, 4),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        
        locked_write_json(self._summary_file, summary, fsync=True, indent=2)
        
        logger.info(
            f"仓位汇总已更新: 总交易={self._trade_count}, "
            f"Long={self._long_count}, Short={self._short_count}, "
            f"总PnL={self._total_pnl:.4f}"
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """获取当前统计信息"""
        with self._lock:
            return {
                "total_trades": self._trade_count,
                "long_trades": self._long_count,
                "short_trades": self._short_count,
                "total_pnl": round(self._total_pnl, 4),
            }
    
    @property
    def positions_file_path(self) -> str:
        """获取仓位记录文件路径"""
        return self._positions_file
