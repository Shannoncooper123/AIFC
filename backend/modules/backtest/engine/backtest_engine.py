"""回测引擎主协调器 - 轻量级协调器模式

职责：
- 协调各个子模块（执行器、统计收集器、结果收集器）
- 管理回测生命周期（启动、停止、清理）
- 提供对外接口
"""
from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from modules.agent.engine import get_engine
from modules.backtest.context import set_backtest_mode
from modules.backtest.engine.dynamic_semaphore import DynamicSemaphore
from modules.backtest.engine.position_logger import PositionLogger
from modules.backtest.engine.position_simulator import PositionSimulator
from modules.backtest.engine.result_collector import ResultCollector
from modules.backtest.engine.stats_collector import BacktestStatsCollector, StepMetrics
from modules.backtest.engine.workflow_executor import WorkflowExecutor
from modules.backtest.models import (
    BacktestConfig,
    BacktestProgress,
    BacktestResult,
    BacktestStatus,
    BacktestTradeResult,
    CancelledLimitOrder,
)
from modules.backtest.providers.kline_provider import BacktestKlineProvider
from modules.config.settings import get_config
from modules.monitor.utils.logger import get_logger

try:
    from modules.backtest.engine.reinforcement_learning_engine import ReinforcementLearningEngine
    _REINFORCEMENT_AVAILABLE = True
except ImportError:
    _REINFORCEMENT_AVAILABLE = False

logger = get_logger('backtest.engine')

_active_backtests: Dict[str, "BacktestEngine"] = {}
_backtests_lock = threading.Lock()


def register_backtest(engine: "BacktestEngine") -> None:
    """注册活跃的回测引擎"""
    with _backtests_lock:
        _active_backtests[engine.backtest_id] = engine


def unregister_backtest(backtest_id: str) -> None:
    """注销回测引擎"""
    with _backtests_lock:
        _active_backtests.pop(backtest_id, None)


def get_active_backtest(backtest_id: str) -> Optional["BacktestEngine"]:
    """获取活跃的回测引擎"""
    with _backtests_lock:
        return _active_backtests.get(backtest_id)


def list_active_backtests() -> List[str]:
    """列出所有活跃的回测ID"""
    with _backtests_lock:
        return list(_active_backtests.keys())


class BacktestEngine:
    """回测引擎主协调器
    
    核心设计：
    1. 每个K线的分析完全独立，拥有相同的初始资金
    2. 开仓后立即在后续K线中模拟止盈止损
    3. 支持并发执行多个K线分析
    4. 统计胜率、盈亏比等指标
    
    架构：
    - WorkflowExecutor: 执行单个回测步骤
    - StatsCollector: 收集运行时统计
    - ResultCollector: 收集交易结果
    """
    
    def __init__(
        self,
        config: BacktestConfig,
        on_progress: Optional[Callable[[BacktestProgress], None]] = None,
        on_complete: Optional[Callable[[BacktestResult], None]] = None,
        enable_reinforcement: bool = False,
    ):
        self.config = config
        self.on_progress = on_progress
        self.on_complete = on_complete
        self.enable_reinforcement = enable_reinforcement and _REINFORCEMENT_AVAILABLE
        
        self.backtest_id = f"bt_{int(time.time() * 1000)}"
        self._stop_requested = False
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        self._original_engine = None
        
        self.kline_provider: Optional[BacktestKlineProvider] = None
        self._position_simulator: Optional[PositionSimulator] = None
        self._executor: Optional[WorkflowExecutor] = None
        self._stats: Optional[BacktestStatsCollector] = None
        self._result_collector: Optional[ResultCollector] = None
        self._position_logger: Optional[PositionLogger] = None
        self._semaphore: Optional[DynamicSemaphore] = None
        self._executor_max_workers = max(1, self.config.concurrency)
        self._executor_resize_target: Optional[int] = None
        self._reinforcement_engine: Optional["ReinforcementLearningEngine"] = None
        
        self._base_dir = get_config().get("agent", {}).get("data_dir", "modules/data")
        self._total_steps = 0
        
        self.result = BacktestResult(
            backtest_id=self.backtest_id,
            config=config,
            status=BacktestStatus.PENDING,
            start_timestamp=datetime.now(timezone.utc),
        )
        
        reinforcement_info = " (强化学习已启用)" if self.enable_reinforcement else ""
        logger.info(f"回测引擎创建: backtest_id={self.backtest_id}, concurrency={config.concurrency}{reinforcement_info}")
    
    def _get_interval_minutes(self, interval: str) -> int:
        """将K线周期转换为分钟数"""
        mapping = {
            "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
            "1h": 60, "2h": 120, "4h": 240, "6h": 360, "12h": 720, "1d": 1440,
        }
        return mapping.get(interval, 15)
    
    def _align_to_kline_time(self, dt: datetime, interval_minutes: int) -> datetime:
        """将时间对齐到K线的标准时间点
        
        Args:
            dt: 原始时间
            interval_minutes: K线周期（分钟）
        
        Returns:
            对齐后的时间
        """
        total_minutes = dt.hour * 60 + dt.minute
        aligned_minutes = (total_minutes // interval_minutes) * interval_minutes
        aligned_hour = aligned_minutes // 60
        aligned_minute = aligned_minutes % 60
        
        return dt.replace(hour=aligned_hour, minute=aligned_minute, second=0, microsecond=0)
    
    def _calculate_total_steps(self) -> int:
        """计算总步数"""
        interval_minutes = self._get_interval_minutes(self.config.interval)
        total_minutes = (self.config.end_time - self.config.start_time).total_seconds() / 60
        return int(total_minutes / interval_minutes)
    
    def _initialize(self) -> None:
        """初始化回测环境
        
        注意：不再设置全局 KlineProvider，每个回测步骤通过 WorkflowExecutor
        使用 context-local provider 实现隔离。这样支持并发回测且避免全局状态污染。
        """
        logger.info("初始化回测环境...")
        
        self._original_engine = get_engine()
        
        logger.info("加载历史K线数据...")
        self.kline_provider = BacktestKlineProvider(
            symbols=self.config.symbols,
            start_time=self.config.start_time,
            end_time=self.config.end_time,
            interval=self.config.interval,
        )
        
        set_backtest_mode(True)
        
        # 注意：已切换到 Pillow 渲染器，线程安全，无需进程池预热
        
        self._position_logger = PositionLogger(
            backtest_id=self.backtest_id,
            base_dir=self._base_dir,
        )
        
        self._position_simulator = PositionSimulator(
            config=self.config,
            kline_provider=self.kline_provider,
            backtest_id=self.backtest_id,
            position_logger=self._position_logger,
        )
        
        self._executor = WorkflowExecutor(
            config=self.config,
            kline_provider=self.kline_provider,
            backtest_id=self.backtest_id,
            position_simulator=self._position_simulator,
        )
        
        self._total_steps = self._calculate_total_steps()
        self._stats = BacktestStatsCollector(self._total_steps)
        self._result_collector = ResultCollector(self.result)
        
        if self.enable_reinforcement and _REINFORCEMENT_AVAILABLE:
            self._reinforcement_engine = ReinforcementLearningEngine(
                config=self.config,
                kline_provider=self.kline_provider,
                backtest_id=self.backtest_id,
                base_dir=self._base_dir,
            )
            self._reinforcement_engine.set_workflow_executor(self._executor)
            logger.info("强化学习引擎已初始化")
        
        logger.info(f"回测环境初始化完成, 仓位记录文件: {self._position_logger.positions_file_path}")
    
    def _cleanup(self) -> None:
        """清理回测环境"""
        logger.info("清理回测环境...")
        
        set_backtest_mode(False)
        
        if self._position_logger:
            self._position_logger.write_summary()
        
        self.kline_provider = None
        self._executor = None
        
        logger.info("回测环境清理完成")
    
    def _execute_step_with_semaphore(
        self,
        current_time: datetime,
        step_index: int,
    ) -> Tuple[str, List[BacktestTradeResult], List["CancelledLimitOrder"], bool]:
        """执行步骤并在完成后释放信号量
        
        Returns:
            (workflow_run_id, 交易结果列表, 取消订单列表, 是否超时)
        """
        try:
            return self._executor.execute_step(current_time, step_index)
        finally:
            if self._semaphore:
                self._semaphore.release()
    
    def _run_streaming(self, all_steps: List[Tuple[int, datetime]]) -> None:
        """流式并发执行回测步骤（使用动态信号量控制并发）"""
        self._semaphore = DynamicSemaphore(self.config.concurrency)
        step_iter = iter(all_steps)
        step_start_times: Dict[Any, float] = {}
        pending_step: Optional[Tuple[int, datetime]] = None
        steps_exhausted = False
        
        current_executor = ThreadPoolExecutor(max_workers=self._executor_max_workers)
        executors = [current_executor]
        executor_counts: Dict[ThreadPoolExecutor, int] = {current_executor: 0}
        
        try:
            pending_futures: Dict[Any, Tuple[int, datetime, ThreadPoolExecutor]] = {}
            
            def get_next_step() -> Optional[Tuple[int, datetime]]:
                """获取下一个待提交的步骤"""
                nonlocal pending_step, steps_exhausted
                if pending_step:
                    step = pending_step
                    pending_step = None
                    return step
                if steps_exhausted:
                    return None
                try:
                    return next(step_iter)
                except StopIteration:
                    steps_exhausted = True
                    return None
            
            def submit_available_steps() -> int:
                """尽可能多地提交步骤，返回成功提交的数量"""
                nonlocal pending_step
                nonlocal current_executor
                submitted = 0
                target_workers = self._executor_resize_target
                if target_workers and target_workers > self._executor_max_workers:
                    self._executor_resize_target = None
                    new_executor = ThreadPoolExecutor(max_workers=target_workers)
                    executors.append(new_executor)
                    executor_counts[new_executor] = 0
                    self._executor_max_workers = target_workers
                    current_executor = new_executor
                while self._semaphore.available > 0:
                    step = get_next_step()
                    if step is None:
                        break
                    step_index, current_time = step
                    if self._semaphore.acquire(timeout=0):
                        future = current_executor.submit(
                            self._execute_step_with_semaphore, 
                            current_time, 
                            step_index
                        )
                        pending_futures[future] = (step_index, current_time, current_executor)
                        executor_counts[current_executor] = executor_counts.get(current_executor, 0) + 1
                        step_start_times[future] = time.time()
                        submitted += 1
                    else:
                        pending_step = step
                        break
                return submitted
            
            submit_available_steps()
            
            while pending_futures or (not steps_exhausted and self._semaphore.available > 0):
                if self._stop_requested:
                    for f in pending_futures:
                        f.cancel()
                    break
                
                submitted = submit_available_steps()
                if submitted > 0:
                    logger.debug(f"动态提交了 {submitted} 个新任务, 当前运行: {self._semaphore.current_count}")
                
                if not pending_futures:
                    if steps_exhausted:
                        break
                    time.sleep(0.1)
                    continue
                
                done_futures = []
                try:
                    for future in as_completed(pending_futures, timeout=0.2):
                        done_futures.append(future)
                        break
                except TimeoutError:
                    pass
                
                for future in done_futures:
                    step_index, current_time, future_executor = pending_futures.pop(future)
                    step_duration = time.time() - step_start_times.pop(future, time.time())
                    executor_counts[future_executor] = executor_counts.get(future_executor, 1) - 1
                    if executor_counts[future_executor] <= 0 and future_executor is not current_executor:
                        future_executor.shutdown(wait=False)
                    
                    try:
                        workflow_run_id, trade_results, cancelled_orders, is_timeout, analysis_outputs, decision_outputs = future.result(timeout=1)
                        
                        self._stats.record_step(StepMetrics(
                            step_index=step_index,
                            duration=step_duration,
                            success=not is_timeout,
                            is_timeout=is_timeout,
                            trade_count=len(trade_results),
                        ))
                        
                        self._result_collector.add_workflow_run(workflow_run_id)
                        self._result_collector.add_trades(trade_results)
                        if cancelled_orders:
                            self._result_collector.add_cancelled_orders(cancelled_orders)
                        
                        if trade_results and self.enable_reinforcement:
                            self._handle_trade_results(
                                workflow_run_id=workflow_run_id,
                                trade_results=trade_results,
                                kline_time=current_time,
                                analysis_outputs=analysis_outputs,
                                decision_outputs=decision_outputs,
                            )
                        
                        if self._stats.should_log():
                            self._stats.log_stats(len(pending_futures))
                        
                        completed = self._stats.completed_count
                        if self.on_progress and completed % 5 == 0:
                            progress = BacktestProgress(
                                current_time=current_time,
                                total_steps=self._total_steps,
                                completed_steps=completed,
                                current_step_info=f"已完成 {completed}/{self._total_steps}, 交易 {self._result_collector.get_trade_count()} 笔",
                                current_running=self._semaphore.current_count if self._semaphore else 0,
                                max_concurrency=self._semaphore.max_value if self._semaphore else self.config.concurrency,
                            )
                            try:
                                self.on_progress(progress)
                            except Exception as e:
                                logger.error(f"进度回调失败: {e}")
                        
                    except Exception as e:
                        logger.error(f"步骤 {step_index} 执行失败: {e}", exc_info=True)
                        self._stats.record_step(StepMetrics(
                            step_index=step_index,
                            duration=step_duration,
                            success=False,
                        ))
        finally:
            for executor_item in executors:
                executor_item.shutdown(wait=False)
    
    def _run_backtest(self) -> None:
        """执行回测主循环"""
        self._running = True
        self.result.status = BacktestStatus.RUNNING
        
        try:
            self._initialize()
            
            interval_minutes = self._get_interval_minutes(self.config.interval)
            step_delta = timedelta(minutes=interval_minutes)
            
            aligned_start = self._align_to_kline_time(self.config.start_time, interval_minutes)
            
            all_steps = []
            current_time = aligned_start
            step_index = 0
            
            while current_time <= self.config.end_time:
                all_steps.append((step_index, current_time))
                current_time += step_delta
                step_index += 1
            
            self._total_steps = len(all_steps)
            self.result.total_klines_analyzed = self._total_steps
            self.result.total_batches = (self._total_steps + self.config.concurrency - 1) // self.config.concurrency
            
            logger.info(
                f"开始回测（流式并发模式）: total_steps={self._total_steps}, "
                f"concurrency={self.config.concurrency}"
            )
            
            self._run_streaming(all_steps)
            
            self._result_collector.compile_results()
            self.result.completed_batches = self.result.total_batches
            
            if self._stop_requested:
                self.result.status = BacktestStatus.CANCELLED
                logger.info("回测已取消")
            else:
                self.result.status = BacktestStatus.COMPLETED
                logger.info("回测完成")
                
        except Exception as e:
            logger.error(f"回测执行失败: {e}", exc_info=True)
            self.result.status = BacktestStatus.FAILED
            self.result.error_message = str(e)
        finally:
            self._cleanup()
            self.result.end_timestamp = datetime.now(timezone.utc)
            self._running = False
            
            if self.on_complete:
                try:
                    self.on_complete(self.result)
                except Exception as e:
                    logger.error(f"完成回调失败: {e}")
            
            self._save_result()
    
    def _save_result(self) -> None:
        """保存回测结果到文件"""
        try:
            result_dir = os.path.join(self._base_dir, "backtest", self.backtest_id)
            os.makedirs(result_dir, exist_ok=True)
            
            result_path = os.path.join(result_dir, "result.json")
            with open(result_path, 'w', encoding='utf-8') as f:
                json.dump(self.result.to_dict(), f, ensure_ascii=False, indent=2, default=str)
            
            logger.info(f"回测结果已保存: {result_path}")
        except Exception as e:
            logger.error(f"保存回测结果失败: {e}")
    
    def start(self) -> str:
        """启动回测（异步）"""
        if self._running:
            raise RuntimeError("回测已在运行中")
        
        self._thread = threading.Thread(target=self._run_backtest, daemon=True)
        self._thread.start()
        
        logger.info(f"回测已启动: {self.backtest_id}")
        return self.backtest_id
    
    def stop(self) -> None:
        """停止回测"""
        if not self._running:
            return
        
        logger.info(f"请求停止回测: {self.backtest_id}")
        self._stop_requested = True
    
    def wait(self, timeout: Optional[float] = None) -> None:
        """等待回测完成"""
        if self._thread:
            self._thread.join(timeout=timeout)
    
    def get_result(self) -> BacktestResult:
        """获取回测结果"""
        return self.result
    
    def get_runtime_stats(self) -> Dict[str, Any]:
        """获取运行时统计信息"""
        if self._stats:
            return self._stats.get_stats()
        return {
            "completed_steps": 0,
            "total_steps": self._total_steps,
            "elapsed_seconds": 0,
            "avg_step_duration": 0,
            "recent_avg_duration": 0,
            "recent_min_duration": 0,
            "recent_max_duration": 0,
            "throughput_per_min": 0,
            "timeout_count": 0,
            "error_count": 0,
        }
    
    def get_side_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取做多/做空实时统计数据"""
        if self._result_collector:
            return self._result_collector.get_realtime_side_stats()
        return {
            "long_stats": {
                "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
                "total_pnl": 0.0, "win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
            },
            "short_stats": {
                "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
                "total_pnl": 0.0, "win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
            },
        }
    
    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self._running
    
    def get_concurrency_info(self) -> Dict[str, Any]:
        """获取当前并发信息
        
        Returns:
            包含 current_running 和 max_concurrency 的字典
        """
        if self._semaphore:
            return {
                "current_running": self._semaphore.current_count,
                "max_concurrency": self._semaphore.max_value,
                "available": self._semaphore.available,
            }
        return {
            "current_running": 0,
            "max_concurrency": self.config.concurrency,
            "available": self.config.concurrency,
        }
    
    def set_max_concurrency(self, new_max: int) -> bool:
        """动态调整并发上限
        
        Args:
            new_max: 新的并发上限（必须 >= 1）
            
        Returns:
            是否成功调整
        """
        if new_max < 1:
            logger.warning(f"无效的并发上限: {new_max}")
            return False
        
        if not self._running:
            logger.warning("回测未在运行中，无法调整并发")
            return False
        
        if self._semaphore:
            old_max = self._semaphore.max_value
            self._semaphore.set_max_value(new_max)
            if new_max > self._executor_max_workers:
                self._executor_resize_target = new_max
            logger.info(f"并发上限已调整: {old_max} -> {new_max}")
            return True
        
        logger.warning("信号量未初始化，无法调整并发")
        return False
    
    def get_reinforcement_statistics(self) -> Optional[Dict[str, Any]]:
        """获取强化学习统计信息
        
        Returns:
            强化学习统计字典，如果未启用强化学习则返回 None
        """
        if self._reinforcement_engine:
            return self._reinforcement_engine.get_statistics()
        return None
    
    def get_reinforcement_engine(self) -> Optional["ReinforcementLearningEngine"]:
        """获取强化学习引擎实例
        
        Returns:
            ReinforcementLearningEngine 实例，如果未启用则返回 None
        """
        return self._reinforcement_engine
    
    def _handle_trade_results(
        self,
        workflow_run_id: str,
        trade_results: List[BacktestTradeResult],
        kline_time: datetime,
        analysis_outputs: Dict[str, str],
        decision_outputs: Dict[str, str],
    ) -> None:
        """处理交易结果，并在需要时触发强化学习
        
        Args:
            workflow_run_id: workflow 运行ID
            trade_results: 交易结果列表
            kline_time: K线时间
            analysis_outputs: 分析节点输出字典 {symbol: output}
            decision_outputs: 决策节点输出字典 {symbol: output}
        """
        if not self.enable_reinforcement or not self._reinforcement_engine:
            return
        
        for trade_result in trade_results:
            if self._reinforcement_engine.should_run_reinforcement(trade_result):
                symbol = trade_result.symbol
                analysis_output = analysis_outputs.get(symbol, "")
                decision_output = decision_outputs.get(symbol, "")
                
                logger.info(
                    f"检测到亏损交易，启动强化学习: symbol={symbol}, "
                    f"pnl={trade_result.realized_pnl:.2f}, exit_type={trade_result.exit_type}"
                )
                
                try:
                    session = self._reinforcement_engine.run_reinforcement_loop(
                        original_workflow_run_id=workflow_run_id,
                        original_trade_result=trade_result,
                        analysis_output=analysis_output,
                        decision_output=decision_output,
                        kline_time=kline_time,
                    )
                    logger.info(
                        f"强化学习完成: session_id={session.session_id}, "
                        f"rounds={session.total_rounds}, improved={session.improvement_achieved}"
                    )
                except Exception as e:
                    logger.error(f"强化学习执行失败: {e}", exc_info=True)
