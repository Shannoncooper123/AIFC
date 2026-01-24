"""实盘模拟引擎单例入口"""
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from modules.agent.trade_simulator.engine.simulator import TradeSimulatorEngine

_engine: Optional['TradeSimulatorEngine'] = None


def set_engine(engine: 'TradeSimulatorEngine') -> None:
    """设置交易引擎实例"""
    global _engine
    _engine = engine


def get_engine() -> Optional['TradeSimulatorEngine']:
    """获取交易引擎实例"""
    return _engine
