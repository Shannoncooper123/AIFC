"""文件操作工具：提供并发安全的文件读写功能"""
import json
import os
import fcntl
import threading
import queue
import time
from typing import Any, Dict
from enum import Enum

from modules.monitor.utils.logger import get_logger

logger = get_logger('agent.trade_simulator.utils.file_utils')


class TaskType(Enum):
    """写入任务类型"""
    STATE = "state"       # 状态文件，支持去重合并
    HISTORY = "history"   # 历史记录，严格保序


def locked_write_json(path: str, data: Any, **json_dump_kwargs) -> None:
    """使用文件锁的同步写入JSON文件（适合低频重要数据）
    
    Args:
        path: 目标文件路径
        data: 要写入的数据（将序列化为JSON）
        **json_dump_kwargs: 传递给 json.dump 的额外参数
                          默认会使用: ensure_ascii=False, indent=2, sort_keys=True
    
    原理：
        1. 使用 fcntl.flock() 获取文件排他锁
        2. 直接写入目标文件
        3. 释放文件锁
        
    并发安全性：
        - fcntl.flock() 是 Unix/Linux 系统的文件锁机制
        - 排他锁保证同一时刻只有一个进程/线程可以写入
        - 无需临时文件，减少 IO 开销
        
    注意：
        - 仅支持 Unix/Linux 系统（使用 fcntl）
        - 如果其他进程持有锁，会阻塞等待
        
    Example:
        >>> locked_write_json('/path/to/data.json', {'key': 'value'})
    """
    # 确保目标目录存在
    dir_name = os.path.dirname(path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    
    # 设置默认的 json.dump 参数
    dump_kwargs = {
        'ensure_ascii': False,
        'indent': 2,
        'sort_keys': True,
    }
    dump_kwargs.update(json_dump_kwargs)
    
    # 使用文件锁保证并发安全
    try:
        with open(path, 'w', encoding='utf-8') as f:
            # 获取排他锁（阻塞等待）
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                json.dump(data, f, **dump_kwargs)
                f.flush()
                os.fsync(f.fileno())  # 确保数据写入磁盘
            finally:
                # 释放锁
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except Exception as e:
        logger.error(f"文件锁写入失败: {path}, error={e}")
        raise


def locked_append_jsonl(path: str, record: Any) -> None:
    dir_name = os.path.dirname(path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    
    try:
        with open(path, 'a', encoding='utf-8') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except Exception as e:
        logger.error(f"文件锁追加失败: {path}, error={e}")
        raise


def locked_write_jsonl(path: str, records: list[Any]) -> None:
    dir_name = os.path.dirname(path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    
    try:
        with open(path, 'w', encoding='utf-8') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                for record in records:
                    f.write(json.dumps(record, ensure_ascii=False) + '\n')
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except Exception as e:
        logger.error(f"文件锁写入JSONL失败: {path}, error={e}")
        raise


class WriteQueue:
    """单例写入队列：异步非阻塞的文件写入服务
    
    使用生产者-消费者模式，主线程将写入任务加入队列后立即返回，
    单独的消费者线程负责实际的文件写入操作。
    
    特性：
        - 完全非阻塞：入队操作立即返回
        - 按顺序处理：所有任务按入队顺序依次写入
        - 优雅关闭：支持等待队列清空后再退出
    
    注意：
        去重和保序逻辑由上游调用者控制，队列只负责异步消费。
    
    Example:
        >>> queue = WriteQueue.get_instance()
        >>> queue.enqueue(TaskType.STATE, '/path/to/state.json', {'balance': 1000})
        >>> queue.shutdown(timeout=5)
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __init__(self):
        """初始化写入队列（私有构造函数，使用 get_instance() 获取实例）"""
        self._queue = queue.Queue(maxsize=100)
        self._running = True
        self._worker_thread = threading.Thread(target=self._consume_loop, daemon=False, name="WriteQueueWorker")
        self._worker_thread.start()
        logger.info("WriteQueue 启动: 消费者线程已启动")
    
    @classmethod
    def get_instance(cls) -> 'WriteQueue':
        """获取单例实例（线程安全）"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def enqueue(self, task_type: TaskType, path: str, data: Any, **json_dump_kwargs) -> None:
        """将写入任务加入队列（非阻塞）
        
        Args:
            task_type: 任务类型（STATE 或 HISTORY）
            path: 目标文件路径
            data: 要写入的数据
            **json_dump_kwargs: 传递给 json.dump 的额外参数
        """
        if not self._running:
            logger.warning("WriteQueue 已关闭，无法加入新任务")
            return
        
        try:
            # 所有任务直接入队，按顺序处理，超时3秒写入失败
            self._queue.put((task_type, path, data, json_dump_kwargs), timeout=3)
        except queue.Full:
            logger.error(f"写入队列已满，任务被丢弃: {path}")
    
    def _consume_loop(self) -> None:
        """消费者循环：不断从队列中取出任务并写入文件"""
        logger.info("WriteQueue 消费者线程开始运行")
        
        while self._running or not self._queue.empty():
            try:
                # 从队列中取任务，超时 0.5 秒
                task = self._queue.get(timeout=0.5)
                task_type, path, data, json_dump_kwargs = task
                
                # 执行文件写入
                self._write_file(task_type, path, data, json_dump_kwargs or {})
                
                self._queue.task_done()
                
            except queue.Empty:
                # 队列为空，继续等待
                continue
            except Exception as e:
                logger.error(f"WriteQueue 消费者异常: {e}", exc_info=True)
        
        logger.info("WriteQueue 消费者线程已退出")
    
    def _write_file(self, task_type: TaskType, path: str, data: Any, json_dump_kwargs: Dict) -> None:
        """实际执行文件写入"""
        try:
            locked_write_json(path, data, **json_dump_kwargs)
            logger.debug(f"WriteQueue 写入成功: type={task_type.value}, path={path}")
        except Exception as e:
            logger.error(f"WriteQueue 写入失败: type={task_type.value}, path={path}, error={e}")
    
    def shutdown(self, timeout: float = 5.0) -> bool:
        """优雅关闭队列：等待所有任务完成
        
        Args:
            timeout: 最大等待时间（秒）
        
        Returns:
            True 如果所有任务已完成，False 如果超时
        """
        if not self._running:
            logger.warning("WriteQueue 已经关闭")
            return True
        
        logger.info(f"WriteQueue 开始关闭，当前队列大小: {self._queue.qsize()}，等待队列清空（超时={timeout}秒）...")
        self._running = False
        
        import time
        start_time = time.time()
        
        # 使用轮询方式等待队列清空（带超时控制）
        while not self._queue.empty():
            elapsed = time.time() - start_time
            if elapsed >= timeout:
                remaining = self._queue.qsize()
                logger.warning(f"WriteQueue 等待超时，队列中还有 {remaining} 个任务未完成")
                break
            time.sleep(0.1)  # 每 100ms 检查一次
        
        if self._queue.empty():
            logger.info("WriteQueue 队列已清空")
        
        # 等待工作线程退出（使用剩余时间）
        elapsed = time.time() - start_time
        remaining_timeout = max(0.5, timeout - elapsed)  # 至少等待 0.5 秒
        
        logger.info(f"等待工作线程退出（剩余超时={remaining_timeout:.1f}秒）...")
        self._worker_thread.join(timeout=remaining_timeout)
        
        if self._worker_thread.is_alive():
            logger.warning(f"WriteQueue 工作线程未能在 {timeout} 秒内退出")
            return False
        else:
            logger.info("WriteQueue 已完全关闭")
            return True
