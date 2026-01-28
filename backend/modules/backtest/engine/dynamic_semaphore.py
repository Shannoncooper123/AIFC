"""动态信号量 - 支持运行时动态调整并发上限

功能：
1. 线程安全的信号量实现
2. 支持运行时动态调整上限（立即生效）
3. 提供当前运行数量和上限的查询接口
"""
from __future__ import annotations

import threading
from typing import Optional

from modules.monitor.utils.logger import get_logger

logger = get_logger('backtest.dynamic_semaphore')


class DynamicSemaphore:
    """支持运行时动态调整上限的信号量
    
    与标准 threading.Semaphore 的区别：
    - 可以在运行时调整上限值
    - 提供当前占用数量的查询
    - 增加上限时立即唤醒等待的线程
    """
    
    def __init__(self, initial_value: int = 1):
        """初始化动态信号量
        
        Args:
            initial_value: 初始并发上限
        """
        if initial_value < 1:
            raise ValueError("initial_value must be >= 1")
        
        self._max_value = initial_value
        self._current_count = 0
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        
        logger.debug(f"DynamicSemaphore 初始化: max_value={initial_value}")
    
    def acquire(self, timeout: Optional[float] = None) -> bool:
        """获取一个槽位
        
        Args:
            timeout: 超时时间（秒），None 表示无限等待
            
        Returns:
            是否成功获取槽位
        """
        with self._condition:
            while self._current_count >= self._max_value:
                if not self._condition.wait(timeout=timeout):
                    return False
            
            self._current_count += 1
            return True
    
    def release(self) -> None:
        """释放一个槽位"""
        with self._condition:
            if self._current_count <= 0:
                logger.warning("release() 调用时 current_count 已为 0")
                return
            
            self._current_count -= 1
            self._condition.notify()
    
    def set_max_value(self, new_max: int) -> None:
        """动态调整上限
        
        - 增加上限：立即唤醒等待的线程
        - 减少上限：不会中断已运行的任务，只影响新任务的启动
        
        Args:
            new_max: 新的并发上限
        """
        if new_max < 1:
            raise ValueError("new_max must be >= 1")
        
        with self._condition:
            old_max = self._max_value
            self._max_value = new_max
            
            if new_max > old_max:
                diff = new_max - old_max
                self._condition.notify(diff)
                logger.info(f"并发上限增加: {old_max} -> {new_max}, 唤醒 {diff} 个等待线程")
            else:
                logger.info(f"并发上限减少: {old_max} -> {new_max}")
    
    @property
    def current_count(self) -> int:
        """当前正在运行的数量"""
        with self._lock:
            return self._current_count
    
    @property
    def max_value(self) -> int:
        """当前上限"""
        with self._lock:
            return self._max_value
    
    @property
    def available(self) -> int:
        """当前可用槽位数"""
        with self._lock:
            return max(0, self._max_value - self._current_count)
    
    def __enter__(self) -> 'DynamicSemaphore':
        """支持 with 语句"""
        self.acquire()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """支持 with 语句"""
        self.release()
        return None
    
    def __repr__(self) -> str:
        return f"DynamicSemaphore(current={self.current_count}, max={self.max_value})"
