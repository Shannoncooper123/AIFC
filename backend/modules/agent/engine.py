from __future__ import annotations
"""统一的交易引擎接口（支持模拟和实盘模式）"""
import contextvars
import threading
from typing import Optional, TYPE_CHECKING, Any, Dict, Protocol, List

if TYPE_CHECKING:
    from modules.agent.trade_simulator.engine.simulator import TradeSimulatorEngine
    from modules.agent.live_engine.engine import BinanceLiveEngine
    from modules.agent.reverse_engine.engine import ReverseEngine


class EngineProtocol(Protocol):
    """引擎统一协议：模拟与实盘均需实现这些方法"""
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def get_account_summary(self) -> Dict[str, Any]: ...
    def get_positions_summary(self) -> List[Dict[str, Any]]: ...
    def open_position(
        self,
        symbol: str,
        side: str,
        quote_notional_usdt: float,
        leverage: int,
        tp_price: Optional[float] = None,
        sl_price: Optional[float] = None,
    ) -> Dict[str, Any]: ...
    def close_position(
        self,
        position_id: Optional[str] = None,
        symbol: Optional[str] = None,
        close_reason: Optional[str] = None,
        close_price: Optional[float] = None,
    ) -> Dict[str, Any]: ...
    def update_tp_sl(
        self,
        symbol: str,
        tp_price: Optional[float] = None,
        sl_price: Optional[float] = None,
    ) -> Dict[str, Any]: ...


_engine: Optional[EngineProtocol] = None
_engine_lock = threading.RLock()

_context_engine: contextvars.ContextVar[Optional[EngineProtocol]] = contextvars.ContextVar(
    'context_engine', default=None
)


def set_engine(engine: EngineProtocol, thread_local: bool = False) -> Optional[contextvars.Token]:
    """设置交易引擎实例（模拟或实盘）
    
    Args:
        engine: 引擎实例
        thread_local: 是否设置为上下文本地（回测并发模式使用）
    
    Returns:
        如果 thread_local=True，返回 Token 用于后续恢复；否则返回 None
    """
    if thread_local:
        return _context_engine.set(engine)
    else:
        global _engine
        with _engine_lock:
            _engine = engine
        return None


def get_engine() -> Optional[EngineProtocol]:
    """获取交易引擎实例（模拟或实盘）。
    
    优先返回上下文本地引擎（回测模式），否则返回全局引擎。
    使用 contextvars 支持 asyncio 上下文传播。
    """
    context_engine = _context_engine.get()
    if context_engine is not None:
        return context_engine
    
    with _engine_lock:
        return _engine


def clear_thread_local_engine() -> None:
    """清除当前上下文的本地引擎"""
    _context_engine.set(None)


def reset_context_engine(token: contextvars.Token) -> None:
    """重置上下文引擎到之前的值
    
    Args:
        token: set_engine 返回的 token
    """
    _context_engine.reset(token)


def is_engine_initialized() -> bool:
    """引擎是否已初始化（单例是否存在）。"""
    context_engine = _context_engine.get()
    if context_engine is not None:
        return True
    with _engine_lock:
        return _engine is not None


_reverse_engine: Optional['ReverseEngine'] = None
_reverse_engine_lock = threading.RLock()


def init_reverse_engine(
    live_engine: 'BinanceLiveEngine',
    config: Dict[str, Any]
) -> 'ReverseEngine':
    """初始化反向交易引擎
    
    Args:
        live_engine: 实盘引擎实例（必需），用于复用 REST/WS 连接
        config: 配置字典
        
    Returns:
        ReverseEngine 实例
        
    Raises:
        ValueError: 如果 live_engine 为 None
    """
    if live_engine is None:
        raise ValueError("init_reverse_engine 必须传入 live_engine 参数")
    
    global _reverse_engine
    with _reverse_engine_lock:
        if _reverse_engine is None:
            from modules.agent.reverse_engine.engine import ReverseEngine
            _reverse_engine = ReverseEngine(live_engine, config)
        return _reverse_engine


def get_reverse_engine() -> Optional['ReverseEngine']:
    """获取反向交易引擎实例
    
    Returns:
        ReverseEngine 实例，如果未初始化则返回 None
    """
    with _reverse_engine_lock:
        return _reverse_engine


def start_reverse_engine() -> bool:
    """启动反向交易引擎
    
    Returns:
        是否成功启动
    """
    with _reverse_engine_lock:
        if _reverse_engine is not None:
            _reverse_engine.start()
            return True
        return False


def stop_reverse_engine() -> None:
    """停止反向交易引擎"""
    global _reverse_engine
    with _reverse_engine_lock:
        if _reverse_engine is not None:
            _reverse_engine.stop()


def ensure_engine(config: Dict[str, Any]) -> EngineProtocol:
    """确保返回一个已初始化的引擎单例。
    若尚未初始化，则根据配置创建对应模式的引擎实例并返回。
    注意：本方法只负责构造实例，不调用 start()，由调用方决定启动时机。
    """
    global _engine
    with _engine_lock:
        if _engine is None:
            mode = (config or {}).get('trading', {}).get('mode', 'simulator')
            if mode == 'live':
                from modules.agent.live_engine.engine import BinanceLiveEngine
                _engine = BinanceLiveEngine(config)
            else:
                from modules.agent.trade_simulator.engine.simulator import TradeSimulatorEngine
                _engine = TradeSimulatorEngine(config)
        return _engine
