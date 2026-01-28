"""Workflow 执行器 - 负责执行单个回测步骤的 workflow"""
from __future__ import annotations

import contextvars
import threading
import time
from concurrent.futures import ThreadPoolExecutor as InnerThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from langchain_core.runnables import RunnableConfig

from modules.agent.builder import create_workflow
from modules.agent.engine import set_engine, clear_thread_local_engine
from modules.agent.state import AgentState
from modules.agent.tools.tool_utils import set_kline_provider, clear_context_kline_provider
from modules.agent.utils.trace_context import workflow_trace_context
from modules.agent.utils.workflow_trace_storage import (
    generate_trace_id,
    record_workflow_start,
    record_workflow_end,
)
from modules.backtest.engine.backtest_trade_engine import BacktestTradeEngine
from modules.backtest.models import BacktestConfig, BacktestTradeResult
from modules.backtest.providers.kline_provider import BacktestKlineProvider, set_backtest_time
from modules.config.settings import get_config
from modules.monitor.utils.logger import get_logger

logger = get_logger('backtest.executor')


class WorkflowExecutor:
    """Workflow 执行器
    
    负责执行单个回测步骤的 workflow，包括：
    - 设置回测上下文（时间、价格、交易引擎）
    - 执行 workflow
    - 模拟止盈止损
    - 清理上下文
    """
    
    def __init__(
        self,
        config: BacktestConfig,
        kline_provider: BacktestKlineProvider,
        backtest_id: str,
        simulate_position_outcome: Callable,
        simulate_limit_order_outcome: Callable,
    ):
        self.config = config
        self.kline_provider = kline_provider
        self.backtest_id = backtest_id
        self._simulate_position_outcome = simulate_position_outcome
        self._simulate_limit_order_outcome = simulate_limit_order_outcome
    
    def execute_step(
        self,
        current_time: datetime,
        step_index: int,
    ) -> Tuple[str, List[BacktestTradeResult], bool]:
        """执行单个回测步骤
        
        Args:
            current_time: 当前模拟时间
            step_index: 步骤索引
        
        Returns:
            (workflow_run_id, 交易结果列表, 是否超时)
        """
        ctx = contextvars.copy_context()
        return ctx.run(self._execute_step_isolated, current_time, step_index)
    
    def _execute_step_isolated(
        self,
        current_time: datetime,
        step_index: int,
    ) -> Tuple[str, List[BacktestTradeResult], bool]:
        """在隔离上下文中执行步骤"""
        step_id = f"step_{step_index}_{int(time.time() * 1000)}"
        trade_results = []
        is_timeout = False
        thread_name = threading.current_thread().name
        
        logger.debug(f"[{thread_name}] 步骤 {step_index} 开始: 目标时间={current_time}")
        
        set_backtest_time(current_time)
        set_kline_provider(self.kline_provider, context_local=True)
        
        trade_engine = self._create_trade_engine(step_id)
        
        try:
            self._update_prices(trade_engine, current_time)
            set_engine(trade_engine, thread_local=True)
            
            mock_alert = self._create_mock_alert(current_time)
            workflow_run_id = generate_trace_id("bt")
            
            cfg = get_config()
            record_workflow_start(workflow_run_id, mock_alert, cfg)
            start_iso = datetime.now(timezone.utc).isoformat()
            
            success, error_msg = self._run_workflow(
                workflow_run_id, mock_alert, current_time, step_index
            )
            
            if success:
                record_workflow_end(workflow_run_id, start_iso, "success", cfg=cfg)
            elif error_msg and "超时" in error_msg:
                is_timeout = True
                record_workflow_end(workflow_run_id, start_iso, "timeout", error=error_msg, cfg=cfg)
                return workflow_run_id, [], is_timeout
            else:
                record_workflow_end(workflow_run_id, start_iso, "error", error=error_msg, cfg=cfg)
                return workflow_run_id, [], is_timeout
            
            trade_results = self._collect_trade_results(
                trade_engine, current_time, workflow_run_id, step_index
            )
            
            return workflow_run_id, trade_results, is_timeout
            
        finally:
            clear_thread_local_engine()
            clear_context_kline_provider()
            trade_engine.stop()
    
    def _create_trade_engine(self, step_id: str) -> BacktestTradeEngine:
        """创建隔离的交易引擎"""
        return BacktestTradeEngine(
            initial_balance=self.config.initial_balance,
            symbols=self.config.symbols,
            backtest_id=self.backtest_id,
            step_id=step_id,
        )
    
    def _update_prices(self, trade_engine: BacktestTradeEngine, current_time: datetime) -> None:
        """更新交易引擎的价格"""
        prices = {}
        for symbol in self.config.symbols:
            kline = self.kline_provider.get_kline_at_time(symbol, self.config.interval, current_time)
            if kline:
                prices[symbol] = kline.close
            else:
                price = self.kline_provider.get_current_price(symbol)
                if price:
                    prices[symbol] = price
        trade_engine.update_mark_prices(prices)
    
    def _create_mock_alert(self, current_time: datetime) -> Dict[str, Any]:
        """创建模拟警报"""
        return {
            "type": "backtest",
            "symbols": self.config.symbols,
            "timestamp": current_time.isoformat(),
            "source": "backtest_engine",
            "backtest_id": self.backtest_id,
        }
    
    def _run_workflow(
        self,
        workflow_run_id: str,
        mock_alert: Dict[str, Any],
        current_time: datetime,
        step_index: int,
    ) -> Tuple[bool, Optional[str]]:
        """执行 workflow（带超时控制）"""
        cfg = get_config()
        graph = create_workflow(cfg)
        workflow_app = graph.compile()
        
        current_ctx = contextvars.copy_context()
        
        def _execute_with_context():
            def _inner():
                with workflow_trace_context(workflow_run_id):
                    workflow_app.invoke(
                        AgentState(),
                        config=self._wrap_config(mock_alert, workflow_run_id, current_time)
                    )
            current_ctx.run(_inner)
        
        try:
            with InnerThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_execute_with_context)
                future.result(timeout=self.config.workflow_timeout)
            return True, None
        except FuturesTimeoutError:
            error_msg = f"workflow执行超时（{self.config.workflow_timeout}秒）"
            logger.error(f"步骤 {step_index} {error_msg}")
            return False, error_msg
        except Exception as e:
            logger.error(f"步骤 {step_index} workflow失败: {e}", exc_info=True)
            return False, str(e)
    
    def _wrap_config(
        self,
        alert: Dict[str, Any],
        workflow_run_id: str,
        current_time: datetime,
    ) -> RunnableConfig:
        """包装 workflow 配置"""
        return RunnableConfig(
            configurable={
                "latest_alert": alert,
                "workflow_run_id": workflow_run_id,
                "backtest_time": current_time,
                "is_backtest": True,
            },
            run_id=workflow_run_id,
        )
    
    def _collect_trade_results(
        self,
        trade_engine: BacktestTradeEngine,
        current_time: datetime,
        workflow_run_id: str,
        step_index: int,
    ) -> List[BacktestTradeResult]:
        """收集交易结果"""
        trade_results = []
        
        for symbol in self.config.symbols:
            if symbol in trade_engine.positions and trade_engine.positions[symbol].status == 'open':
                logger.debug(f"步骤 {step_index} 检测到开仓: {symbol}")
                trade_result = self._simulate_position_outcome(
                    trade_engine, symbol, current_time, workflow_run_id
                )
                if trade_result:
                    trade_results.append(trade_result)
                    logger.info(
                        f"步骤 {step_index} 交易完成: {symbol} {trade_result.side} "
                        f"exit_type={trade_result.exit_type} pnl={trade_result.realized_pnl:.2f}"
                    )
        
        pending_orders = trade_engine.get_pending_limit_orders()
        if pending_orders:
            logger.debug(f"步骤 {step_index} 检测到 {len(pending_orders)} 个限价单")
            for order in pending_orders:
                limit_trade_result = self._simulate_limit_order_outcome(
                    trade_engine, order, current_time, workflow_run_id
                )
                if limit_trade_result:
                    trade_results.append(limit_trade_result)
                    logger.info(
                        f"步骤 {step_index} 限价单交易完成: {order['symbol']} {limit_trade_result.side} "
                        f"exit_type={limit_trade_result.exit_type} pnl={limit_trade_result.realized_pnl:.2f}"
                    )
        
        return trade_results
