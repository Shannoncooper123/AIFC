from __future__ import annotations
"""统一的交易引擎接口（支持模拟和实盘模式）"""
from typing import Optional, TYPE_CHECKING, Any, Dict, Protocol, List
import threading

if TYPE_CHECKING:
    from modules.agent.trade_simulator.engine.simulator import TradeSimulatorEngine
    from modules.agent.live_engine.engine import BinanceLiveEngine


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

_thread_local_engine = threading.local()


def set_engine(engine: EngineProtocol, thread_local: bool = False) -> None:
    """设置交易引擎实例（模拟或实盘）
    
    Args:
        engine: 引擎实例
        thread_local: 是否设置为线程本地（回测并发模式使用）
    """
    if thread_local:
        _thread_local_engine.engine = engine
    else:
        global _engine
        with _engine_lock:
            _engine = engine


def get_engine() -> Optional[EngineProtocol]:
    """获取交易引擎实例（模拟或实盘）。
    
    优先返回线程本地引擎（回测模式），否则返回全局引擎。
    """
    thread_engine = getattr(_thread_local_engine, 'engine', None)
    if thread_engine is not None:
        return thread_engine
    
    with _engine_lock:
        return _engine


def clear_thread_local_engine() -> None:
    """清除当前线程的本地引擎"""
    if hasattr(_thread_local_engine, 'engine'):
        delattr(_thread_local_engine, 'engine')


def is_engine_initialized() -> bool:
    """引擎是否已初始化（单例是否存在）。"""
    thread_engine = getattr(_thread_local_engine, 'engine', None)
    if thread_engine is not None:
        return True
    with _engine_lock:
        return _engine is not None


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
