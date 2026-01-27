"""回测上下文管理 - 用于在回测模式下共享状态"""
import threading

_backtest_mode_flag = threading.local()


def is_backtest_mode() -> bool:
    """检查当前是否处于回测模式"""
    return getattr(_backtest_mode_flag, 'active', False)


def set_backtest_mode(active: bool) -> None:
    """设置回测模式标志"""
    _backtest_mode_flag.active = active
