"""回测引擎主协调器 - 并发独立执行模式"""
from __future__ import annotations

import asyncio
import contextvars
import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from modules.agent.builder import create_workflow
from modules.agent.engine import set_engine, get_engine, clear_thread_local_engine
from modules.agent.state import AgentState
from modules.agent.tools.tool_utils import set_kline_provider, get_kline_provider, clear_context_kline_provider
from modules.agent.utils.trace_context import workflow_trace_context
from modules.agent.utils.workflow_trace_storage import (
    generate_trace_id,
    record_workflow_start,
    record_workflow_end,
)
from modules.backtest.engine.backtest_trade_engine import BacktestTradeEngine
from modules.backtest.models import (
    BacktestConfig,
    BacktestProgress,
    BacktestResult,
    BacktestStatus,
    BacktestTradeResult,
)
from modules.backtest.providers.kline_provider import BacktestKlineProvider, set_backtest_time
from modules.config.settings import get_config
from modules.monitor.utils.logger import get_logger
from modules.backtest.context import is_backtest_mode, set_backtest_mode
from langchain_core.runnables import RunnableConfig

logger = get_logger('backtest.engine')


class BacktestEngine:
    """回测引擎主协调器 - 并发独立执行模式
    
    核心设计：
    1. 每个K线的分析完全独立，拥有相同的初始资金
    2. 开仓后立即在后续K线中模拟止盈止损
    3. 支持并发执行多个K线分析
    4. 统计胜率、盈亏比等指标
    """
    
    def __init__(
        self,
        config: BacktestConfig,
        on_progress: Optional[Callable[[BacktestProgress], None]] = None,
        on_complete: Optional[Callable[[BacktestResult], None]] = None,
    ):
        """初始化回测引擎
        
        Args:
            config: 回测配置
            on_progress: 进度回调函数
            on_complete: 完成回调函数
        """
        self.config = config
        self.on_progress = on_progress
        self.on_complete = on_complete
        
        self.backtest_id = f"bt_{int(time.time() * 1000)}"
        self._stop_requested = False
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        self._original_engine = None
        self._original_provider = None
        
        self.kline_provider: Optional[BacktestKlineProvider] = None
        
        self._trades_lock = threading.Lock()
        self._completed_count = 0
        self._total_count = 0
        
        self.result = BacktestResult(
            backtest_id=self.backtest_id,
            config=config,
            status=BacktestStatus.PENDING,
            start_timestamp=datetime.now(timezone.utc),
        )
        
        logger.info(f"回测引擎创建: backtest_id={self.backtest_id}, concurrency={config.concurrency}")
    
    def _get_interval_minutes(self, interval: str) -> int:
        """将K线周期转换为分钟数"""
        mapping = {
            "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
            "1h": 60, "2h": 120, "4h": 240, "6h": 360, "12h": 720, "1d": 1440,
        }
        return mapping.get(interval, 15)
    
    def _calculate_total_steps(self) -> int:
        """计算总步数"""
        interval_minutes = self._get_interval_minutes(self.config.interval)
        total_minutes = (self.config.end_time - self.config.start_time).total_seconds() / 60
        return int(total_minutes / interval_minutes)
    
    def _initialize(self) -> None:
        """初始化回测环境"""
        logger.info("初始化回测环境...")
        
        self._original_engine = get_engine()
        self._original_provider = get_kline_provider()
        
        logger.info("加载历史K线数据...")
        self.kline_provider = BacktestKlineProvider(
            symbols=self.config.symbols,
            start_time=self.config.start_time,
            end_time=self.config.end_time,
            interval=self.config.interval,
        )
        
        set_kline_provider(self.kline_provider)
        set_backtest_mode(True)
        
        logger.info("回测环境初始化完成")
    
    def _cleanup(self) -> None:
        """清理回测环境，恢复原始状态"""
        logger.info("清理回测环境...")
        
        set_backtest_mode(False)
        set_kline_provider(self._original_provider)
        if self._original_engine:
            set_engine(self._original_engine)
        
        logger.info("回测环境已清理")
    
    def _create_mock_alert(self, current_time: datetime) -> Dict[str, Any]:
        """创建模拟的alert记录"""
        entries = []
        for symbol in self.config.symbols:
            price = self.kline_provider.get_current_price(symbol) if self.kline_provider else 0
            entries.append({
                'symbol': symbol,
                'price': price or 0,
                'price_change_rate': 0,
                'triggered_indicators': ['BACKTEST_TRIGGER'],
                'engulfing_type': '非外包',
            })
        
        return {
            'type': 'aggregate',
            'source': 'backtest',
            'ts': current_time.isoformat(),
            'interval': self.config.interval,
            'symbols': self.config.symbols,
            'pending_count': len(self.config.symbols),
            'entries': entries,
        }
    
    def _wrap_config(self, alert: Dict[str, Any], workflow_run_id: str, current_time: datetime) -> RunnableConfig:
        """包装workflow配置"""
        cfg = get_config()
        return RunnableConfig(
            configurable={
                "workflow_run_id": workflow_run_id,
                "current_trace_id": workflow_run_id,
                "latest_alert": alert,
                "backtest_mode": True,
                "backtest_time": current_time.isoformat(),
            },
            recursion_limit=100,
            tags=["backtest", f"bt_{self.backtest_id}"],
            run_name="backtest_workflow_run",
            metadata={
                "env": cfg.get('env', {}),
                "workflow_run_id": workflow_run_id,
                "backtest_id": self.backtest_id,
                "backtest_mode": True,
                "backtest_time": current_time.isoformat(),
            }
        )
    
    def _create_isolated_trade_engine(self, step_id: str) -> BacktestTradeEngine:
        """为单个步骤创建独立的交易引擎
        
        Args:
            step_id: 步骤唯一标识
        
        Returns:
            独立的交易引擎实例
        """
        cfg = get_config()
        engine = BacktestTradeEngine(
            config=cfg,
            backtest_id=f"{self.backtest_id}_{step_id}",
            initial_balance=self.config.initial_balance,
        )
        engine.start()
        return engine
    
    def _simulate_position_outcome(
        self,
        trade_engine: BacktestTradeEngine,
        symbol: str,
        entry_time: datetime,
        workflow_run_id: str,
    ) -> Optional[BacktestTradeResult]:
        """模拟仓位的止盈止损结果
        
        在开仓后，逐个K线检查止盈止损是否触发
        
        Args:
            trade_engine: 交易引擎
            symbol: 交易对
            entry_time: 入场时间
            workflow_run_id: workflow运行ID
        
        Returns:
            交易结果，如果没有开仓则返回None
        """
        if symbol not in trade_engine.positions:
            return None
        
        pos = trade_engine.positions[symbol]
        if pos.status != 'open':
            return None
        
        interval_minutes = self._get_interval_minutes(self.config.interval)
        step_delta = timedelta(minutes=interval_minutes)
        
        current_time = entry_time + step_delta
        holding_bars = 0
        max_bars = 1000
        
        while current_time <= self.config.end_time and holding_bars < max_bars:
            kline = self.kline_provider.get_kline_at_time(symbol, self.config.interval, current_time)
            
            if kline:
                holding_bars += 1
                
                result = trade_engine.check_tp_sl(
                    symbol,
                    current_price=kline.close,
                    high_price=kline.high,
                    low_price=kline.low
                )
                
                if result and 'error' not in result:
                    exit_type = "tp" if "止盈" in result.get('close_reason', '') else "sl"
                    realized_pnl = result.get('realized_pnl', 0)
                    exit_price = result.get('close_price', kline.close)
                    
                    pnl_percent = (realized_pnl / self.config.initial_balance) * 100
                    
                    return BacktestTradeResult(
                        trade_id=f"{self.backtest_id}_{uuid.uuid4().hex[:8]}",
                        kline_time=entry_time,
                        symbol=symbol,
                        side=pos.side,
                        entry_price=pos.entry_price,
                        exit_price=exit_price,
                        tp_price=pos.tp_price or 0,
                        sl_price=pos.sl_price or 0,
                        size=pos.size,
                        exit_time=current_time,
                        exit_type=exit_type,
                        realized_pnl=realized_pnl,
                        pnl_percent=pnl_percent,
                        holding_bars=holding_bars,
                        workflow_run_id=workflow_run_id,
                    )
            
            current_time += step_delta
        
        if symbol in trade_engine.positions and trade_engine.positions[symbol].status == 'open':
            final_kline = self.kline_provider.get_kline_at_time(
                symbol, self.config.interval, self.config.end_time
            )
            if final_kline:
                close_result = trade_engine.close_position(
                    symbol=symbol,
                    close_reason="回测结束强制平仓",
                    close_price=final_kline.close
                )
                if close_result and 'error' not in close_result:
                    realized_pnl = close_result.get('realized_pnl', 0)
                    pnl_percent = (realized_pnl / self.config.initial_balance) * 100
                    
                    return BacktestTradeResult(
                        trade_id=f"{self.backtest_id}_{uuid.uuid4().hex[:8]}",
                        kline_time=entry_time,
                        symbol=symbol,
                        side=pos.side,
                        entry_price=pos.entry_price,
                        exit_price=final_kline.close,
                        tp_price=pos.tp_price or 0,
                        sl_price=pos.sl_price or 0,
                        size=pos.size,
                        exit_time=self.config.end_time,
                        exit_type="timeout",
                        realized_pnl=realized_pnl,
                        pnl_percent=pnl_percent,
                        holding_bars=holding_bars,
                        workflow_run_id=workflow_run_id,
                    )
        
        return None
    
    def _simulate_limit_order_outcome(
        self,
        trade_engine: BacktestTradeEngine,
        order: Dict[str, Any],
        entry_time: datetime,
        workflow_run_id: str
    ) -> Optional[BacktestTradeResult]:
        """模拟限价单的成交和后续止盈止损
        
        在后续K线中检测限价单是否触发成交，成交后继续模拟止盈止损。
        
        Args:
            trade_engine: 回测交易引擎
            order: 限价单信息
            entry_time: 当前K线时间
            workflow_run_id: workflow运行ID
        
        Returns:
            如果限价单成交并平仓，返回交易结果；否则返回None
        """
        symbol = order['symbol']
        limit_price = order['limit_price']
        side = order['side']
        
        interval_minutes = self._get_interval_minutes(self.config.interval)
        step_delta = timedelta(minutes=interval_minutes)
        
        current_time = entry_time + step_delta
        max_bars = 1000
        bars_checked = 0
        
        while current_time <= self.config.end_time and bars_checked < max_bars:
            kline = self.kline_provider.get_kline_at_time(symbol, self.config.interval, current_time)
            
            if kline:
                bars_checked += 1
                
                filled_orders = trade_engine.check_limit_orders(
                    symbol,
                    high_price=kline.high,
                    low_price=kline.low,
                    close_price=kline.close
                )
                
                if filled_orders:
                    for filled in filled_orders:
                        if filled['id'] == order['id']:
                            logger.info(f"限价单成交: {symbol} @ {filled['filled_price']}")
                            
                            if symbol in trade_engine.positions and trade_engine.positions[symbol].status == 'open':
                                return self._simulate_position_outcome(
                                    trade_engine, symbol, current_time, workflow_run_id
                                )
            
            current_time += step_delta
        
        pending = trade_engine.get_pending_limit_orders(symbol)
        if pending:
            for p in pending:
                if p['id'] == order['id']:
                    trade_engine.cancel_limit_order(order['id'])
                    logger.info(f"限价单超时取消: {symbol} order_id={order['id']}")
        
        return None
    
    def _run_single_step_isolated(
        self, 
        current_time: datetime, 
        step_index: int
    ) -> Tuple[str, List[BacktestTradeResult]]:
        """执行单个独立的回测步骤
        
        每个步骤拥有独立的交易引擎和初始资金
        
        Args:
            current_time: 当前模拟时间
            step_index: 步骤索引
        
        Returns:
            (workflow_run_id, 交易结果列表)
        """
        step_id = f"step_{step_index}_{int(time.time() * 1000)}"
        trade_results = []
        thread_name = threading.current_thread().name
        
        logger.info(f"[{thread_name}] 步骤 {step_index} 开始: 目标时间={current_time}")
        
        time_token = set_backtest_time(current_time)
        
        kline_provider_token = set_kline_provider(self.kline_provider, context_local=True)
        
        trade_engine = self._create_isolated_trade_engine(step_id)
        
        try:
            actual_time = self.kline_provider.get_current_time()
            logger.info(f"[{thread_name}] 步骤 {step_index} 时间设置: 目标={current_time}, 实际={actual_time}, 匹配={current_time == actual_time}")
            
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
            
            set_engine(trade_engine, thread_local=True)
            
            mock_alert = self._create_mock_alert(current_time)
            workflow_run_id = generate_trace_id("bt")
            
            cfg = get_config()
            record_workflow_start(workflow_run_id, mock_alert, cfg)
            
            start_iso = datetime.now(timezone.utc).isoformat()
            
            graph = create_workflow(cfg)
            workflow_app = graph.compile()
            
            try:
                with workflow_trace_context(workflow_run_id):
                    workflow_app.invoke(
                        AgentState(),
                        config=self._wrap_config(mock_alert, workflow_run_id, current_time)
                    )
                record_workflow_end(workflow_run_id, start_iso, "success", cfg=cfg)
                logger.debug(f"步骤 {step_index} workflow完成: time={current_time}, run_id={workflow_run_id}")
            except Exception as e:
                logger.error(f"步骤 {step_index} workflow失败: {e}", exc_info=True)
                record_workflow_end(workflow_run_id, start_iso, "error", error=str(e), cfg=cfg)
                return workflow_run_id, []
            
            for symbol in self.config.symbols:
                if symbol in trade_engine.positions and trade_engine.positions[symbol].status == 'open':
                    logger.info(f"步骤 {step_index} 检测到开仓: {symbol}, 开始模拟止盈止损...")
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
                logger.info(f"步骤 {step_index} 检测到 {len(pending_orders)} 个限价单, 开始模拟成交...")
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
            
            return workflow_run_id, trade_results
            
        finally:
            clear_thread_local_engine()
            clear_context_kline_provider()
            trade_engine.stop()
    
    def _run_step_with_context(self, current_time: datetime, step_index: int) -> Tuple[str, List[BacktestTradeResult]]:
        """在独立的上下文中执行回测步骤
        
        使用 contextvars.copy_context() 确保每个任务有独立的上下文
        """
        ctx = contextvars.copy_context()
        return ctx.run(self._run_single_step_isolated, current_time, step_index)
    
    def _run_batch(self, batch_times: List[Tuple[int, datetime]]) -> List[Tuple[str, List[BacktestTradeResult]]]:
        """并发执行一批回测步骤
        
        Args:
            batch_times: [(step_index, current_time), ...]
        
        Returns:
            [(workflow_run_id, trade_results), ...]
        """
        results = []
        
        with ThreadPoolExecutor(max_workers=self.config.concurrency) as executor:
            futures = [
                executor.submit(self._run_step_with_context, current_time, step_index)
                for step_index, current_time in batch_times
            ]
            
            for future in futures:
                if self._stop_requested:
                    break
                try:
                    result = future.result(timeout=300)
                    results.append(result)
                except Exception as e:
                    logger.error(f"批次执行失败: {e}", exc_info=True)
                    results.append(("error", []))
        
        return results
    
    def _run_backtest(self) -> None:
        """执行回测主循环 - 并发独立执行模式"""
        self._running = True
        self.result.status = BacktestStatus.RUNNING
        
        try:
            self._initialize()
            
            total_steps = self._calculate_total_steps()
            interval_minutes = self._get_interval_minutes(self.config.interval)
            step_delta = timedelta(minutes=interval_minutes)
            
            all_steps = []
            current_time = self.config.start_time
            step_index = 0
            
            while current_time <= self.config.end_time:
                all_steps.append((step_index, current_time))
                current_time += step_delta
                step_index += 1
            
            self._total_count = len(all_steps)
            self.result.total_klines_analyzed = self._total_count
            
            batch_size = self.config.concurrency
            total_batches = (len(all_steps) + batch_size - 1) // batch_size
            self.result.total_batches = total_batches
            
            logger.info(
                f"开始回测: total_steps={self._total_count}, "
                f"batch_size={batch_size}, total_batches={total_batches}"
            )
            
            all_trades = []
            completed_steps = 0
            
            for batch_idx in range(total_batches):
                if self._stop_requested:
                    break
                
                batch_start = batch_idx * batch_size
                batch_end = min(batch_start + batch_size, len(all_steps))
                batch_times = all_steps[batch_start:batch_end]
                
                logger.info(f"执行批次 {batch_idx + 1}/{total_batches}, 步骤 {batch_start}-{batch_end-1}")
                
                batch_results = self._run_batch(batch_times)
                
                for workflow_run_id, trade_results in batch_results:
                    if workflow_run_id != "error":
                        self.result.workflow_runs.append(workflow_run_id)
                    all_trades.extend(trade_results)
                    completed_steps += 1
                
                self.result.completed_batches = batch_idx + 1
                self.result.trades = all_trades.copy()
                
                if self.on_progress:
                    progress = BacktestProgress(
                        current_time=batch_times[-1][1] if batch_times else self.config.start_time,
                        total_steps=self._total_count,
                        completed_steps=completed_steps,
                        current_step_info=f"批次 {batch_idx + 1}/{total_batches}, 已完成交易 {len(all_trades)} 笔",
                    )
                    try:
                        self.on_progress(progress)
                    except Exception as e:
                        logger.error(f"进度回调失败: {e}")
            
            self.result.trades = all_trades
            self._compile_results()
            
            if self._stop_requested:
                self.result.status = BacktestStatus.CANCELLED
                logger.info("回测已取消")
            else:
                self.result.status = BacktestStatus.COMPLETED
                logger.info(f"回测完成: 总交易 {len(all_trades)} 笔")
                
        except Exception as e:
            logger.error(f"回测失败: {e}", exc_info=True)
            self.result.status = BacktestStatus.FAILED
            self.result.error_message = str(e)
        finally:
            self._cleanup()
            self._running = False
            self.result.end_timestamp = datetime.now(timezone.utc)
            
            if self.on_complete:
                try:
                    self.on_complete(self.result)
                except Exception as e:
                    logger.error(f"完成回调失败: {e}")
            
            self._save_result()
    
    def _compile_results(self) -> None:
        """汇总回测结果"""
        trades = self.result.trades
        
        if not trades:
            self.result.final_balance = self.config.initial_balance
            return
        
        self.result.total_trades = len(trades)
        
        winning_trades = [t for t in trades if t.realized_pnl > 0]
        losing_trades = [t for t in trades if t.realized_pnl < 0]
        
        self.result.winning_trades = len(winning_trades)
        self.result.losing_trades = len(losing_trades)
        
        self.result.total_pnl = sum(t.realized_pnl for t in trades)
        
        if winning_trades:
            self.result.avg_win = sum(t.realized_pnl for t in winning_trades) / len(winning_trades)
        
        if losing_trades:
            self.result.avg_loss = sum(t.realized_pnl for t in losing_trades) / len(losing_trades)
        
        self.result.final_balance = self.config.initial_balance + self.result.total_pnl
        
        cumulative_pnl = 0
        peak = 0
        max_drawdown = 0
        
        for trade in sorted(trades, key=lambda t: t.kline_time):
            cumulative_pnl += trade.realized_pnl
            if cumulative_pnl > peak:
                peak = cumulative_pnl
            drawdown = peak - cumulative_pnl
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        self.result.max_drawdown = max_drawdown
        
        logger.info(
            f"回测统计: 总交易={self.result.total_trades}, "
            f"胜率={self.result.win_rate:.2%}, "
            f"盈亏比={self.result.profit_factor:.2f}, "
            f"总盈亏={self.result.total_pnl:.2f}"
        )
    
    def _save_result(self) -> None:
        """保存回测结果"""
        cfg = get_config()
        base_dir = cfg.get('agent', {}).get('data_dir', 'modules/data')
        result_path = os.path.join(base_dir, 'backtest', self.backtest_id, 'result.json')
        
        try:
            os.makedirs(os.path.dirname(result_path), exist_ok=True)
            with open(result_path, 'w', encoding='utf-8') as f:
                json.dump(self.result.to_dict(), f, indent=2, ensure_ascii=False)
            logger.info(f"回测结果已保存: {result_path}")
        except Exception as e:
            logger.error(f"保存回测结果失败: {e}")
    
    def start(self) -> str:
        """启动回测（异步）
        
        Returns:
            回测ID
        """
        if self._running:
            logger.warning("回测已在运行中")
            return self.backtest_id
        
        self._thread = threading.Thread(target=self._run_backtest, daemon=True)
        self._thread.start()
        
        logger.info(f"回测已启动: backtest_id={self.backtest_id}")
        return self.backtest_id
    
    def start_sync(self) -> BacktestResult:
        """同步执行回测
        
        Returns:
            回测结果
        """
        self._run_backtest()
        return self.result
    
    def stop(self) -> None:
        """停止回测"""
        logger.info("请求停止回测...")
        self._stop_requested = True
    
    def is_running(self) -> bool:
        """检查回测是否正在运行"""
        return self._running
    
    def get_status(self) -> BacktestStatus:
        """获取回测状态"""
        return self.result.status
    
    def get_result(self) -> BacktestResult:
        """获取回测结果"""
        return self.result


_active_backtests: Dict[str, BacktestEngine] = {}
_backtests_lock = threading.Lock()


def get_active_backtest(backtest_id: str) -> Optional[BacktestEngine]:
    """获取活跃的回测引擎"""
    with _backtests_lock:
        return _active_backtests.get(backtest_id)


def register_backtest(engine: BacktestEngine) -> None:
    """注册回测引擎"""
    with _backtests_lock:
        _active_backtests[engine.backtest_id] = engine


def unregister_backtest(backtest_id: str) -> None:
    """注销回测引擎"""
    with _backtests_lock:
        _active_backtests.pop(backtest_id, None)


def list_active_backtests() -> List[str]:
    """列出所有活跃的回测ID"""
    with _backtests_lock:
        return list(_active_backtests.keys())
