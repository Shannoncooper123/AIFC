"""回测上下文管理 - 用于在回测模式下共享状态

使用 contextvars 替代 threading.local，支持：
1. asyncio 上下文传播
2. 并发回测步骤的隔离
3. 与 tool_utils 中的 KlineProvider 机制保持一致
"""
import contextvars
from typing import Optional

_backtest_mode: contextvars.ContextVar[bool] = contextvars.ContextVar(
    'backtest_mode', default=False
)


def is_backtest_mode() -> bool:
    """检查当前是否处于回测模式
    
    Returns:
        True 如果当前上下文处于回测模式
    """
    return _backtest_mode.get()


def set_backtest_mode(active: bool) -> Optional[contextvars.Token]:
    """设置回测模式标志
    
    Args:
        active: 是否激活回测模式
    
    Returns:
        Token 用于后续恢复上下文（如需要）
    """
    return _backtest_mode.set(active)


def reset_backtest_mode(token: contextvars.Token) -> None:
    """重置回测模式到之前的值
    
    Args:
        token: set_backtest_mode 返回的 token
    """
    _backtest_mode.reset(token)
