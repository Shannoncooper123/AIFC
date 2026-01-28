"""回测统计收集器 - 负责收集和汇总运行时统计信息"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

from modules.monitor.utils.logger import get_logger

logger = get_logger('backtest.stats')


@dataclass
class StepMetrics:
    """单步执行指标"""
    step_index: int
    duration: float
    success: bool
    is_timeout: bool = False
    trade_count: int = 0


class BacktestStatsCollector:
    """回测统计收集器
    
    线程安全地收集和汇总回测运行时统计信息。
    """
    
    def __init__(self, total_steps: int, log_interval: int = 60):
        self._lock = threading.Lock()
        self._total_steps = total_steps
        self._log_interval = log_interval
        
        self._start_time = time.time()
        self._last_log_time = time.time()
        
        self._step_durations: List[float] = []
        self._recent_durations: List[float] = []
        self._recent_window = 100
        
        self._completed_count = 0
        self._timeout_count = 0
        self._error_count = 0
        self._trade_count = 0
    
    def record_step(self, metrics: StepMetrics) -> None:
        """记录单步执行结果"""
        with self._lock:
            self._completed_count += 1
            self._step_durations.append(metrics.duration)
            
            self._recent_durations.append(metrics.duration)
            if len(self._recent_durations) > self._recent_window:
                self._recent_durations.pop(0)
            
            if metrics.is_timeout:
                self._timeout_count += 1
            if not metrics.success:
                self._error_count += 1
            
            self._trade_count += metrics.trade_count
    
    def should_log(self) -> bool:
        """检查是否应该输出日志"""
        now = time.time()
        if now - self._last_log_time >= self._log_interval:
            self._last_log_time = now
            return True
        return False
    
    def log_stats(self, pending_count: int = 0) -> None:
        """输出统计日志"""
        stats = self.get_stats()
        logger.info(
            f"[回测统计] 已完成={stats['completed_steps']}/{stats['total_steps']} | "
            f"待处理={pending_count} | "
            f"平均耗时={stats['avg_step_duration']:.1f}s | "
            f"近期耗时={stats['recent_avg_duration']:.1f}s "
            f"(min={stats['recent_min_duration']:.1f}s, max={stats['recent_max_duration']:.1f}s) | "
            f"吞吐量={stats['throughput_per_min']:.1f}/min | "
            f"超时={stats['timeout_count']} | "
            f"错误={stats['error_count']}"
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """获取当前统计信息"""
        with self._lock:
            elapsed = time.time() - self._start_time
            
            avg_duration = sum(self._step_durations) / len(self._step_durations) if self._step_durations else 0
            recent_avg = sum(self._recent_durations) / len(self._recent_durations) if self._recent_durations else 0
            recent_min = min(self._recent_durations) if self._recent_durations else 0
            recent_max = max(self._recent_durations) if self._recent_durations else 0
            
            throughput = self._completed_count / elapsed * 60 if elapsed > 0 else 0
            
            return {
                "completed_steps": self._completed_count,
                "total_steps": self._total_steps,
                "elapsed_seconds": round(elapsed, 1),
                "avg_step_duration": round(avg_duration, 2),
                "recent_avg_duration": round(recent_avg, 2),
                "recent_min_duration": round(recent_min, 2),
                "recent_max_duration": round(recent_max, 2),
                "throughput_per_min": round(throughput, 2),
                "timeout_count": self._timeout_count,
                "error_count": self._error_count,
                "trade_count": self._trade_count,
            }
    
    @property
    def completed_count(self) -> int:
        with self._lock:
            return self._completed_count
    
    @property
    def timeout_count(self) -> int:
        with self._lock:
            return self._timeout_count
    
    @property
    def error_count(self) -> int:
        with self._lock:
            return self._error_count
