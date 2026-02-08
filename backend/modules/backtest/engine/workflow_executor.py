"""Workflow 执行器 - 负责执行单个回测步骤的 workflow"""
from __future__ import annotations

import contextvars
import threading
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from langchain_core.runnables import RunnableConfig

from modules.agent.builder import create_workflow
from modules.agent.engine import set_engine, clear_thread_local_engine
from modules.agent.state import AgentState
from modules.agent.utils.kline_utils import set_kline_provider, clear_context_kline_provider
from modules.agent.utils.trace_utils import workflow_trace_context
from modules.agent.utils.workflow_trace_storage import (
    generate_trace_id,
    record_workflow_start,
    record_workflow_end,
)
from modules.backtest.engine.backtest_trade_engine import BacktestTradeEngine
from modules.backtest.models import BacktestConfig, BacktestTradeResult, CancelledLimitOrder
from modules.backtest.providers.kline_provider import BacktestKlineProvider, set_backtest_time
from modules.config.settings import get_config
from modules.monitor.utils.logger import get_logger

if TYPE_CHECKING:
    from modules.backtest.engine.position_simulator import PositionSimulator

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
        position_simulator: "PositionSimulator",
    ):
        self.config = config
        self.kline_provider = kline_provider
        self.backtest_id = backtest_id
        self._position_simulator = position_simulator
    
    def execute_step(
        self,
        current_time: datetime,
        step_index: int,
    ) -> Tuple[str, List[BacktestTradeResult], List[CancelledLimitOrder], bool]:
        """执行单个回测步骤
        
        Args:
            current_time: 当前模拟时间
            step_index: 步骤索引
        
        Returns:
            (workflow_run_id, 交易结果列表, 取消订单列表, 是否超时)
        """
        ctx = contextvars.copy_context()
        return ctx.run(self._execute_step_isolated, current_time, step_index)
    
    def _execute_step_isolated(
        self,
        current_time: datetime,
        step_index: int,
    ) -> Tuple[str, List[BacktestTradeResult], List[CancelledLimitOrder], bool]:
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
                return workflow_run_id, [], [], is_timeout
            else:
                record_workflow_end(workflow_run_id, start_iso, "error", error=error_msg, cfg=cfg)
                return workflow_run_id, [], [], is_timeout
            
            trade_results, cancelled_orders = self._collect_trade_results(
                trade_engine, current_time, workflow_run_id, step_index
            )
            
            return workflow_run_id, trade_results, cancelled_orders, is_timeout
            
        finally:
            clear_thread_local_engine()
            clear_context_kline_provider()
            trade_engine.stop()
    
    def _create_trade_engine(self, step_id: str) -> BacktestTradeEngine:
        """创建隔离的交易引擎"""
        cfg = get_config()
        engine = BacktestTradeEngine(
            config=cfg,
            backtest_id=f"{self.backtest_id}_{step_id}",
            initial_balance=self.config.initial_balance,
            fixed_margin_usdt=self.config.fixed_margin_usdt,
            fixed_leverage=self.config.fixed_leverage,
            reverse_mode=self.config.reverse_mode,
        )
        engine.start()
        return engine
    
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
        """创建模拟警报
        
        构造符合 context_injection_node 期望的 alert 结构，
        包含 entries 字段以便正确填充 opportunities。
        """
        entries = []
        for symbol in self.config.symbols:
            kline = self.kline_provider.get_kline_at_time(symbol, self.config.interval, current_time)
            price = kline.close if kline else 0.0
            price_change_rate = 0.0
            if kline and kline.open > 0:
                price_change_rate = (kline.close - kline.open) / kline.open
            
            entries.append({
                "symbol": symbol,
                "price": price,
                "price_change_rate": price_change_rate,
                "triggered_indicators": ["BACKTEST"],
                "engulfing_type": "非外包",
            })
        
        return {
            "type": "backtest",
            "symbols": self.config.symbols,
            "timestamp": current_time.isoformat(),
            "ts": current_time.strftime("%Y-%m-%d %H:%M:%S"),
            "interval": self.config.interval,
            "source": "backtest_engine",
            "backtest_id": self.backtest_id,
            "entries": entries,
        }
    
    def _run_workflow(
        self,
        workflow_run_id: str,
        mock_alert: Dict[str, Any],
        current_time: datetime,
        step_index: int,
    ) -> Tuple[bool, Optional[str]]:
        """执行 workflow
        
        注意：移除了内部的 ThreadPoolExecutor 超时控制，因为：
        1. 外层已经有 ThreadPoolExecutor 管理并发
        2. 嵌套 ThreadPoolExecutor 会导致线程爆炸和潜在死锁
        3. workflow 超时由外层的 as_completed(timeout=600) 控制
        
        如果需要更精细的超时控制，应该在 LangGraph 层面配置。
        """
        cfg = get_config()
        graph = create_workflow(cfg)
        workflow_app = graph.compile()
        
        try:
            with workflow_trace_context(workflow_run_id):
                workflow_app.invoke(
                    AgentState(),
                    config=self._wrap_config(mock_alert, workflow_run_id, current_time)
                )
            return True, None
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
    ) -> Tuple[List[BacktestTradeResult], List[CancelledLimitOrder]]:
        """收集交易结果和取消订单
        
        Returns:
            (交易结果列表, 取消订单列表)
        """
        trade_results = []
        cancelled_orders = []
        
        for symbol in self.config.symbols:
            if symbol in trade_engine.positions and trade_engine.positions[symbol].status == 'open':
                logger.debug(f"步骤 {step_index} 检测到开仓: {symbol}")
                trade_result = self._position_simulator.simulate_position_outcome(
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
                limit_trade_result, cancelled_order = self._position_simulator.simulate_limit_order_outcome(
                    trade_engine, order, current_time, workflow_run_id
                )
                if limit_trade_result:
                    trade_results.append(limit_trade_result)
                    logger.info(
                        f"步骤 {step_index} 限价单交易完成: {order['symbol']} {limit_trade_result.side} "
                        f"exit_type={limit_trade_result.exit_type} pnl={limit_trade_result.realized_pnl:.2f}"
                    )
                elif cancelled_order:
                    cancelled_orders.append(cancelled_order)
                    logger.info(
                        f"步骤 {step_index} 限价单未成交: {order['symbol']} {cancelled_order.side} "
                        f"limit_price={cancelled_order.limit_price} 原因={cancelled_order.cancel_reason}"
                    )
        
        return trade_results, cancelled_orders
