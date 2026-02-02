"""反向交易引擎模块

当 Agent 下限价单时，自动创建反向条件单进行对冲交易。
使用固定保证金和杠杆，与 Agent 的参数无关。
"""

from typing import Optional
import threading

_reverse_engine_instance = None
_lock = threading.Lock()


def get_reverse_engine():
    """获取反向交易引擎单例
    
    Returns:
        ReverseEngine 实例，如果未初始化则返回 None
    """
    return _reverse_engine_instance


def init_reverse_engine(config: dict):
    """初始化反向交易引擎
    
    Args:
        config: 配置字典
        
    Returns:
        ReverseEngine 实例
    """
    global _reverse_engine_instance
    
    with _lock:
        if _reverse_engine_instance is None:
            from .engine import ReverseEngine
            _reverse_engine_instance = ReverseEngine(config)
        return _reverse_engine_instance


def shutdown_reverse_engine():
    """关闭反向交易引擎"""
    global _reverse_engine_instance
    
    with _lock:
        if _reverse_engine_instance is not None:
            _reverse_engine_instance.stop()
            _reverse_engine_instance = None
