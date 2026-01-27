"""回测模块 - 支持历史K线数据回测Agent交易策略"""

__all__ = [
    'BacktestEngine',
    'BacktestTradeEngine',
    'BacktestKlineProvider',
    'BacktestConfig',
    'BacktestResult',
    'BacktestStatus',
]


def __getattr__(name):
    """延迟导入以避免循环依赖"""
    if name == 'BacktestEngine':
        from modules.backtest.engine.backtest_engine import BacktestEngine
        return BacktestEngine
    elif name == 'BacktestTradeEngine':
        from modules.backtest.engine.backtest_trade_engine import BacktestTradeEngine
        return BacktestTradeEngine
    elif name == 'BacktestKlineProvider':
        from modules.backtest.providers.kline_provider import BacktestKlineProvider
        return BacktestKlineProvider
    elif name in ('BacktestConfig', 'BacktestResult', 'BacktestStatus'):
        from modules.backtest import models
        return getattr(models, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
