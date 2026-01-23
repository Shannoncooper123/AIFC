"""交易模拟引擎自动化测试：
- 模拟BTCUSDT多仓
- 验证TP/SL触发
- 验证部分平仓与账户/持仓更新
"""
import math
import os
import sys
from typing import Dict

import pytest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, BASE_DIR)

from modules.agent.trade_simulator.engine.simulator import TradeSimulatorEngine
from modules.agent.engine import set_engine


def make_min_config(tmp_path) -> Dict:
    """构建最小可用测试配置，避免依赖外部.env和config.yaml"""
    cfg = {
        'env': {
            'smtp_user': 'test@example.com',
            'smtp_password': 'password',
            'alert_email': 'alert@example.com',
            'log_level': 'INFO',
        },
        'kline': {
            'interval': '1m',
            'history_size': 30,
            'warmup_size': 50,
        },
        'indicators': {
            'atr_period': 14,
            'stddev_period': 20,
            'volume_ma_period': 20,
            'bb_period': 20,
            'bb_std_multiplier': 2.0,
            'rsi_period': 14,
            'ema_fast_period': 12,
            'ema_slow_period': 26,
            'long_wick_ratio_threshold': 0.6,
        },
        'thresholds': {
            'atr_zscore': 2.5,
            'price_change_zscore': 2.5,
            'volume_zscore': 3.0,
            'min_indicators_triggered': 3,
            'rsi_overbought': 75,
            'rsi_oversold': 25,
            'rsi_zscore': 2.0,
            'bb_width_zscore': 3.0,
            'bb_squeeze_price_zscore': 1.0,
            'ma_deviation_zscore': 2.5,
            'long_wick_ratio_threshold': 0.6,
        },
        'websocket': {
            'base_url': 'wss://fstream.binance.com',
            'max_streams_per_connection': 1024,
            'reconnect_delay': 5,
            'max_reconnect_attempts': 10,
            'ping_interval': 180,
        },
        'api': {
            'base_url': 'https://fapi.binance.com',
            'timeout': 10,
            'retry_times': 3,
        },
        'symbols': {
            'quote_asset': 'USDT',
            'contract_type': 'PERPETUAL',
            'min_volume_24h': 1000000,
            'exclude': [],
        },
        'agent': {
            'alerts_jsonl_path': '/home/sunfayao/monitor/data/alerts.jsonl',
            'reports_jsonl_path': str(tmp_path / 'agent_reports.jsonl'),
            'state_path': str(tmp_path / 'state.json'),
            'trade_state_path': str(tmp_path / 'trade_state.json'),
            'position_history_path': str(tmp_path / 'position_history.jsonl'),
            'default_interval_min': 30,
            'simulator': {
                'initial_balance': 10000.0,
                'taker_fee_rate': 0.0005,
                'max_leverage': 10,
                'ws_interval': '1m',
            },
            'report_email': 'alert@example.com',
        }
    }
    return cfg


class FakeWSManager:
    def __init__(self, *args, **kwargs):
        self.connected = False
        self.symbols = []
        self.interval = '1m'

    def connect_all(self, symbols, interval):
        self.connected = True
        self.symbols = symbols
        self.interval = interval

    def close_all(self):
        self.connected = False
        self.symbols = []


class FakeRest:
    def __init__(self, entry_price: float):
        self.entry_price = entry_price

    def get_klines(self, symbol: str, interval: str, limit: int = 1):
        # 返回最近一根的收盘价为 entry_price
        return [[0, 0, 0, 0, self.entry_price]]


def approx_equal(a, b, tol=1e-6):
    return math.isclose(a, b, rel_tol=0, abs_tol=tol)


@pytest.fixture
def engine(tmp_path):
    cfg = make_min_config(tmp_path)
    eng = TradeSimulatorEngine(cfg)
    # 注入假的WS与REST，避免真实网络依赖
    eng.ws_manager = FakeWSManager(cfg, eng._on_kline_wrapper)
    eng.position_manager.rest = FakeRest(entry_price=100.0)
    set_engine(eng)
    return eng


def test_tp_trigger_long(engine):
    # 开多仓：名义1000，杠杆3，TP=102，SL=99
    res = engine.open_position(
        symbol='BTCUSDT', side='long', quote_notional_usdt=1000.0, leverage=3,
        tp_price=102.0, sl_price=99.0
    )
    assert 'error' not in res, f"开仓失败: {res}"
    pos_id = res['id']
    assert res['symbol'] == 'BTCUSDT'
    assert approx_equal(res['entry_price'], 100.0)
    assert approx_equal(res['tp_price'], 102.0)
    assert approx_equal(res['sl_price'], 99.0)
    engine._on_kline_wrapper('BTCUSDT', {'h': 102.5, 'l': 100.0, 'c': 103.0})
    # 校验持仓状态已关闭，账户实现盈亏为正
    pos = engine.positions['BTCUSDT']
    assert pos.status == 'closed'
    assert pos.close_price is not None
    assert engine.account.realized_pnl > 0.0
    # 手续费开/平均应扣减
    assert pos.fees_open > 0.0
    assert pos.fees_close > 0.0


def test_sl_trigger_long(engine):
    # 开多仓：名义1000，杠杆3，TP=102，SL=99
    res = engine.open_position(
        symbol='BTCUSDT', side='long', quote_notional_usdt=1000.0, leverage=3,
        tp_price=102.0, sl_price=99.0
    )
    assert 'error' not in res, f"开仓失败: {res}"
    engine._on_kline_wrapper('BTCUSDT', {'h': 100.5, 'l': 98.5, 'c': 99.0})
    pos = engine.positions['BTCUSDT']
    assert pos.status == 'closed'
    assert engine.account.realized_pnl < 0.0


def test_close_long(engine):
    res = engine.open_position(
        symbol='BTCUSDT', side='long', quote_notional_usdt=1000.0, leverage=2,
        tp_price=103.0, sl_price=99.0
    )
    assert 'error' not in res, f"开仓失败: {res}"
    res_close = engine.close_position(symbol='BTCUSDT', close_reason='agent', close_price=101.0)
    assert 'error' not in res_close, f"平仓失败: {res_close}"
    pos = engine.positions['BTCUSDT']
    assert pos.status == 'closed'
    assert pos.fees_close > 0.0


def test_summary_consistency(engine):
    # 开多仓并检查摘要接口一致性
    res = engine.open_position(
        symbol='BTCUSDT', side='long', quote_notional_usdt=1000.0, leverage=3,
        tp_price=102.0, sl_price=99.0
    )
    assert 'error' not in res
    acc = engine.get_account_summary()
    pos_list = engine.get_positions_summary()
    assert isinstance(acc, dict)
    assert isinstance(pos_list, list)
    assert any(p['symbol'] == 'BTCUSDT' for p in pos_list)
