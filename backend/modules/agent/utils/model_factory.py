"""LLM 模型工厂 - 单例模式 + 指数退避重试"""
import asyncio
import os
import random
import threading
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

from langchain_openai import ChatOpenAI

from modules.monitor.utils.logger import get_logger

logger = get_logger('agent.utils.model_factory')

T = TypeVar('T')

INITIAL_RETRY_DELAY = 1.0
MAX_RETRY_DELAY = 32.0
DEFAULT_MAX_RETRIES = 5
JITTER_FACTOR = 0.25


def calculate_retry_delay(attempt: int) -> float:
    """计算指数退避延迟时间
    
    Args:
        attempt: 当前重试次数（从0开始）
    
    Returns:
        延迟秒数（带随机抖动）
    """
    base_delay = min(INITIAL_RETRY_DELAY * (2 ** attempt), MAX_RETRY_DELAY)
    jitter = 1 - JITTER_FACTOR + (random.random() * JITTER_FACTOR * 2)
    return base_delay * jitter


def with_retry(
    max_retries: int = DEFAULT_MAX_RETRIES,
    retryable_exceptions: tuple = (Exception,),
):
    """同步函数重试装饰器
    
    Args:
        max_retries: 最大重试次数
        retryable_exceptions: 可重试的异常类型
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = calculate_retry_delay(attempt)
                        logger.warning(
                            f"[Retry {attempt + 1}/{max_retries}] {func.__name__} failed: {e}. "
                            f"Retrying in {delay:.2f}s..."
                        )
                        import time
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"[Retry exhausted] {func.__name__} failed after {max_retries} retries: {e}"
                        )
            raise last_exception
        return wrapper
    return decorator


def with_async_retry(
    max_retries: int = DEFAULT_MAX_RETRIES,
    retryable_exceptions: tuple = (Exception,),
):
    """异步函数重试装饰器
    
    Args:
        max_retries: 最大重试次数
        retryable_exceptions: 可重试的异常类型
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = calculate_retry_delay(attempt)
                        logger.warning(
                            f"[Retry {attempt + 1}/{max_retries}] {func.__name__} failed: {e}. "
                            f"Retrying in {delay:.2f}s..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"[Retry exhausted] {func.__name__} failed after {max_retries} retries: {e}"
                        )
            raise last_exception
        return wrapper
    return decorator


class ModelFactory:
    """LLM 模型工厂（单例模式）
    
    提供统一的模型创建接口，支持：
    1. 单例模式，避免重复创建相同配置的模型
    2. 内置指数退避重试逻辑
    3. 统一的配置管理
    """
    
    _instance: Optional['ModelFactory'] = None
    _lock = threading.Lock()
    _models: dict = {}
    
    def __new__(cls) -> 'ModelFactory':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._models = {}
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> 'ModelFactory':
        """获取工厂单例"""
        return cls()
    
    def _get_model_key(
        self,
        temperature: float,
        timeout: int,
        max_tokens: int,
        thinking_enabled: bool,
    ) -> str:
        """生成模型缓存键"""
        return f"t{temperature}_to{timeout}_mt{max_tokens}_th{thinking_enabled}"
    
    def get_model(
        self,
        temperature: float = 0.0,
        timeout: int = 600,
        max_tokens: int = 16000,
        thinking_enabled: bool = False,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> ChatOpenAI:
        """获取或创建 ChatOpenAI 模型实例
        
        Args:
            temperature: 温度参数
            timeout: 超时时间（秒）
            max_tokens: 最大 token 数
            thinking_enabled: 是否启用 thinking 模式
            max_retries: SDK 内置重试次数
        
        Returns:
            ChatOpenAI 实例
        """
        key = self._get_model_key(temperature, timeout, max_tokens, thinking_enabled)
        
        if key not in self._models:
            with self._lock:
                if key not in self._models:
                    extra_body = {"thinking": {"type": "enabled"}} if thinking_enabled else None
                    
                    model = ChatOpenAI(
                        model=os.getenv('AGENT_MODEL'),
                        api_key=os.getenv('AGENT_API_KEY'),
                        base_url=os.getenv('AGENT_BASE_URL') or None,
                        temperature=temperature,
                        timeout=timeout,
                        max_tokens=max_tokens,
                        max_retries=max_retries,
                        logprobs=False,
                        extra_body=extra_body,
                    )
                    
                    self._models[key] = model
                    logger.info(f"创建新模型实例: {key}")
        
        return self._models[key]
    
    def get_analysis_model(self) -> ChatOpenAI:
        """获取分析节点专用模型（做多/做空分析）"""
        return self.get_model(
            temperature=0.0,
            timeout=600,
            max_tokens=16000,
            thinking_enabled=True,
        )
    
    def get_decision_model(self) -> ChatOpenAI:
        """获取决策节点专用模型（开仓决策）"""
        return self.get_model(
            temperature=0.0,
            timeout=300,
            max_tokens=8000,
            thinking_enabled=True,
        )
    
    def get_position_management_model(self) -> ChatOpenAI:
        """获取持仓管理节点专用模型"""
        return self.get_model(
            temperature=0.0,    
            timeout=600,
            max_tokens=16000,
            thinking_enabled=False,
        )
    
    def get_reporting_model(self) -> ChatOpenAI:
        """获取报告节点专用模型"""
        return self.get_model(
            temperature=0.0,
            timeout=600,
            max_tokens=4096,
            thinking_enabled=True,
        )
    
    def clear_cache(self) -> None:
        """清除模型缓存"""
        with self._lock:
            self._models.clear()
            logger.info("模型缓存已清除")


def get_model_factory() -> ModelFactory:
    """获取模型工厂单例的便捷函数"""
    return ModelFactory.get_instance()
