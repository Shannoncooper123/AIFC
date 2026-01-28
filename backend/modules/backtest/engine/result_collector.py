"""结果收集器 - 负责收集和编译回测结果"""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from modules.backtest.models import (
    BacktestConfig,
    BacktestResult,
    BacktestStatus,
    BacktestTradeResult,
)
from modules.monitor.utils.logger import get_logger

logger = get_logger('backtest.result')


class ResultCollector:
    """结果收集器
    
    线程安全地收集交易结果并编译最终统计。
    """
    
    def __init__(self, result: BacktestResult):
        self._lock = threading.Lock()
        self.result = result
    
    def add_workflow_run(self, workflow_run_id: str) -> None:
        """添加 workflow 运行记录"""
        if workflow_run_id and workflow_run_id != "error":
            with self._lock:
                self.result.workflow_runs.append(workflow_run_id)
    
    def add_trades(self, trades: List[BacktestTradeResult]) -> None:
        """添加交易结果"""
        if trades:
            with self._lock:
                self.result.trades.extend(trades)
    
    def get_trades_copy(self) -> List[BacktestTradeResult]:
        """获取交易结果的副本"""
        with self._lock:
            return self.result.trades.copy()
    
    def get_trade_count(self) -> int:
        """获取交易数量"""
        with self._lock:
            return len(self.result.trades)
    
    def compile_results(self) -> None:
        """编译最终结果统计"""
        with self._lock:
            trades = self.result.trades
            
            if not trades:
                self.result.final_balance = self.result.config.initial_balance
                return
            
            self.result.total_trades = len(trades)
            
            winning_trades = [t for t in trades if t.realized_pnl > 0]
            losing_trades = [t for t in trades if t.realized_pnl < 0]
            
            self.result.winning_trades = len(winning_trades)
            self.result.losing_trades = len(losing_trades)
            self.result.win_rate = len(winning_trades) / len(trades) if trades else 0
            
            self.result.total_pnl = sum(t.realized_pnl for t in trades)
            self.result.final_balance = self.result.config.initial_balance + self.result.total_pnl
            
            avg_win = sum(t.realized_pnl for t in winning_trades) / len(winning_trades) if winning_trades else 0
            avg_loss = abs(sum(t.realized_pnl for t in losing_trades) / len(losing_trades)) if losing_trades else 0
            self.result.profit_factor = avg_win / avg_loss if avg_loss > 0 else float('inf') if avg_win > 0 else 0
            
            self.result.max_drawdown = self._calculate_max_drawdown(trades)
            
            if trades:
                self.result.avg_trade_duration = sum(t.holding_bars for t in trades) / len(trades)
            
            self._log_summary()
    
    def _calculate_max_drawdown(self, trades: List[BacktestTradeResult]) -> float:
        """计算最大回撤"""
        if not trades:
            return 0
        
        sorted_trades = sorted(trades, key=lambda t: t.exit_time)
        
        cumulative_pnl = 0
        peak_pnl = 0
        max_drawdown = 0
        
        for trade in sorted_trades:
            cumulative_pnl += trade.realized_pnl
            peak_pnl = max(peak_pnl, cumulative_pnl)
            drawdown = peak_pnl - cumulative_pnl
            max_drawdown = max(max_drawdown, drawdown)
        
        return max_drawdown
    
    def _log_summary(self) -> None:
        """输出结果摘要日志"""
        r = self.result
        logger.info("=" * 60)
        logger.info("回测结果汇总")
        logger.info("=" * 60)
        logger.info(f"总交易数: {r.total_trades}")
        logger.info(f"胜率: {r.win_rate:.2%}")
        logger.info(f"盈利交易: {r.winning_trades}, 亏损交易: {r.losing_trades}")
        logger.info(f"总盈亏: ${r.total_pnl:.2f}")
        logger.info(f"最终余额: ${r.final_balance:.2f}")
        logger.info(f"盈亏比: {r.profit_factor:.2f}")
        logger.info(f"最大回撤: ${r.max_drawdown:.2f}")
        logger.info(f"平均持仓时长: {r.avg_trade_duration:.1f} bars")
        logger.info("=" * 60)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        with self._lock:
            return self.result.to_dict()
