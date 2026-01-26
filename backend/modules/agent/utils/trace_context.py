"""
Trace Context Manager - 线程/协程安全的 trace 上下文管理

提供全局可访问的 trace context，供引擎层获取当前 workflow_run_id。
使用 contextvars 实现协程安全的上下文传递。

使用方式：
    # 在 workflow 入口处设置上下文
    from modules.agent.utils.trace_context import workflow_trace_context
    
    with workflow_trace_context(workflow_run_id):
        result = workflow.invoke(...)
    
    # 在引擎层获取 run_id
    from modules.agent.utils.trace_context import get_current_workflow_run_id
    
    run_id = get_current_workflow_run_id()  # 自动获取当前上下文中的 run_id
"""
import contextvars
from contextlib import contextmanager
from typing import Optional, Generator

_workflow_run_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'workflow_run_id', default=None
)


def get_current_workflow_run_id() -> Optional[str]:
    """
    获取当前 workflow run_id（线程/协程安全）
    
    Returns:
        当前上下文中的 workflow_run_id，如果未设置则返回 None
    """
    return _workflow_run_id.get()


def set_current_workflow_run_id(run_id: Optional[str]) -> contextvars.Token:
    """
    设置当前 workflow run_id
    
    Args:
        run_id: workflow run_id
        
    Returns:
        Token 用于后续恢复上下文
    """
    return _workflow_run_id.set(run_id)


@contextmanager
def workflow_trace_context(run_id: str) -> Generator[None, None, None]:
    """
    上下文管理器：设置 workflow run_id 作用域
    
    在上下文内部，引擎层可以通过 get_current_workflow_run_id() 获取 run_id。
    退出上下文后自动恢复之前的值。
    
    Args:
        run_id: workflow run_id
        
    Yields:
        None
        
    Example:
        with workflow_trace_context(workflow_run_id):
            # 在这个作用域内，引擎层可以获取到 run_id
            result = workflow.invoke(...)
    """
    token = set_current_workflow_run_id(run_id)
    try:
        yield
    finally:
        _workflow_run_id.reset(token)
