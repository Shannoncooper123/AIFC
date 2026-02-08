#!/usr/bin/env python3
"""
反向交易回测测试脚本

测试场景：
1. 限价单成交逻辑（正向/反向）
2. 止盈止损触发逻辑
3. 各种K线边界情况
4. 盈亏计算验证
"""
import sys
import logging
from pathlib import Path

logging.getLogger('crypto-monitor').setLevel(logging.WARNING)

sys.path.insert(0, str(Path(__file__).parent.parent))

from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from modules.agent.trade_simulator.engine.limit_order_manager import LimitOrderManager
from modules.agent.trade_simulator.models import Account, Position, PendingOrder
from modules.backtest.engine.backtest_trade_engine import BacktestTradeEngine
from modules.agent.engine import set_engine, reset_context_engine
from modules.agent.tools.create_limit_order_tool import create_limit_order_tool
from modules.monitor.utils.logger import get_logger

logger = get_logger('test.reverse_backtest')


@dataclass
class TestKline:
    """测试用K线数据"""
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'o': self.open,
            'h': self.high,
            'l': self.low,
            'c': self.close,
        }


@dataclass
class TestResult:
    """测试结果"""
    name: str
    passed: bool
    expected: str
    actual: str
    details: str = ""


class ReverseBacktestTester:
    """反向回测测试器"""
    
    def __init__(self):
        self.results: List[TestResult] = []
        self.base_config = {
            'api': {
                'base_url': 'https://fapi.binance.com',
                'timeout': 30,
                'retry_times': 3
            },
            'websocket': {
                'url': 'wss://fstream.binance.com',
                'max_streams_per_connection': 200,
                'reconnect_delay': 5
            },
            'agent': {
                'simulator': {
                    'initial_balance': 10000.0,
                    'max_leverage': 20
                },
                'disable_persistence': True
            },
            'trading': {
                'fixed_margin_usdt': 100.0,
                'max_leverage': 10
            }
        }
    
    def _create_engine(self, reverse_mode: bool = False) -> BacktestTradeEngine:
        """创建测试用交易引擎"""
        engine = BacktestTradeEngine(
            config=self.base_config,
            backtest_id=f"test_{datetime.now().timestamp()}",
            initial_balance=10000.0,
            fixed_margin_usdt=100.0,
            fixed_leverage=10,
            reverse_mode=reverse_mode
        )
        engine.start()
        return engine
    
    def _log_result(self, result: TestResult):
        """记录测试结果"""
        self.results.append(result)
        status = "✅ PASS" if result.passed else "❌ FAIL"
        print(f"\n{status}: {result.name}")
        print(f"  预期: {result.expected}")
        print(f"  实际: {result.actual}")
        if result.details:
            print(f"  详情: {result.details}")
    
    # ==================== 限价单成交逻辑测试 ====================
    
    def test_long_limit_order_price_above_market(self):
        """测试：做多限价单，限价高于市价（应以open成交）
        
        场景：限价单 0.15，市价（open）0.14
        预期：立即以 0.14 成交（因为限价高于市价，立即吃单）
        """
        engine = self._create_engine(reverse_mode=False)
        
        engine.set_simulated_price("TESTUSDT", 0.14)
        
        result = engine.limit_order_manager.create_limit_order(
            symbol="TESTUSDT",
            side="long",
            limit_price=0.15,
            margin_usdt=100.0,
            leverage=10,
            tp_price=0.16,
            sl_price=0.13
        )
        
        kline = TestKline(
            timestamp=1000,
            open=0.14,
            high=0.145,
            low=0.138,
            close=0.142
        )
        
        engine.limit_order_manager.on_kline("TESTUSDT", kline.to_dict())
        
        order = list(engine.limit_order_manager.orders.values())[0]
        
        passed = (order.status == "filled" and order.filled_price == 0.14)
        
        self._log_result(TestResult(
            name="做多限价单-限价高于市价",
            passed=passed,
            expected="状态=filled, 成交价=0.14 (以open成交)",
            actual=f"状态={order.status}, 成交价={order.filled_price}",
            details="限价0.15高于市价open=0.14，应立即以0.14成交"
        ))
        
        engine.stop()
    
    def test_long_limit_order_price_below_market(self):
        """测试：做多限价单，限价低于市价（等待价格下跌）
        
        场景：限价单 0.13，市价（open）0.15
        预期：等待 low 触及 0.13 时，以 0.13 成交
        """
        engine = self._create_engine(reverse_mode=False)
        
        engine.set_simulated_price("TESTUSDT", 0.15)
        
        result = engine.limit_order_manager.create_limit_order(
            symbol="TESTUSDT",
            side="long",
            limit_price=0.13,
            margin_usdt=100.0,
            leverage=10,
            tp_price=0.16,
            sl_price=0.12
        )
        
        kline1 = TestKline(
            timestamp=1000,
            open=0.15,
            high=0.155,
            low=0.14,
            close=0.145
        )
        engine.limit_order_manager.on_kline("TESTUSDT", kline1.to_dict())
        
        order = list(engine.limit_order_manager.orders.values())[0]
        still_pending = order.status == "pending"
        
        kline2 = TestKline(
            timestamp=2000,
            open=0.14,
            high=0.142,
            low=0.128,
            close=0.135
        )
        engine.limit_order_manager.on_kline("TESTUSDT", kline2.to_dict())
        
        order = list(engine.limit_order_manager.orders.values())[0]
        
        passed = (still_pending and order.status == "filled" and order.filled_price == 0.13)
        
        self._log_result(TestResult(
            name="做多限价单-限价低于市价",
            passed=passed,
            expected="第一根K线pending，第二根K线filled @ 0.13",
            actual=f"第一根K线{'pending' if still_pending else 'filled'}, "
                   f"第二根K线{order.status} @ {order.filled_price}",
            details="限价0.13低于市价0.15，等待low=0.128触及后以0.13成交"
        ))
        
        engine.stop()
    
    def test_short_limit_order_price_below_market(self):
        """测试：做空限价单，限价低于市价（应以open成交）
        
        场景：限价单 0.14，市价（open）0.15
        预期：立即以 0.15 成交（因为限价低于市价，立即吃单）
        """
        engine = self._create_engine(reverse_mode=False)
        
        engine.set_simulated_price("TESTUSDT", 0.15)
        
        result = engine.limit_order_manager.create_limit_order(
            symbol="TESTUSDT",
            side="short",
            limit_price=0.14,
            margin_usdt=100.0,
            leverage=10,
            tp_price=0.12,
            sl_price=0.16
        )
        
        kline = TestKline(
            timestamp=1000,
            open=0.15,
            high=0.155,
            low=0.145,
            close=0.148
        )
        
        engine.limit_order_manager.on_kline("TESTUSDT", kline.to_dict())
        
        order = list(engine.limit_order_manager.orders.values())[0]
        
        passed = (order.status == "filled" and order.filled_price == 0.15)
        
        self._log_result(TestResult(
            name="做空限价单-限价低于市价",
            passed=passed,
            expected="状态=filled, 成交价=0.15 (以open成交)",
            actual=f"状态={order.status}, 成交价={order.filled_price}",
            details="限价0.14低于市价open=0.15，应立即以0.15成交"
        ))
        
        engine.stop()
    
    def test_short_limit_order_price_above_market(self):
        """测试：做空限价单，限价高于市价（等待价格上涨）
        
        场景：限价单 0.16，市价（open）0.14
        预期：等待 high 触及 0.16 时，以 0.16 成交
        """
        engine = self._create_engine(reverse_mode=False)
        
        engine.set_simulated_price("TESTUSDT", 0.14)
        
        result = engine.limit_order_manager.create_limit_order(
            symbol="TESTUSDT",
            side="short",
            limit_price=0.16,
            margin_usdt=100.0,
            leverage=10,
            tp_price=0.14,
            sl_price=0.18
        )
        
        kline1 = TestKline(
            timestamp=1000,
            open=0.14,
            high=0.155,
            low=0.138,
            close=0.15
        )
        engine.limit_order_manager.on_kline("TESTUSDT", kline1.to_dict())
        
        order = list(engine.limit_order_manager.orders.values())[0]
        still_pending = order.status == "pending"
        
        kline2 = TestKline(
            timestamp=2000,
            open=0.15,
            high=0.165,
            low=0.148,
            close=0.16
        )
        engine.limit_order_manager.on_kline("TESTUSDT", kline2.to_dict())
        
        order = list(engine.limit_order_manager.orders.values())[0]
        
        passed = (still_pending and order.status == "filled" and order.filled_price == 0.16)
        
        self._log_result(TestResult(
            name="做空限价单-限价高于市价",
            passed=passed,
            expected="第一根K线pending，第二根K线filled @ 0.16",
            actual=f"第一根K线{'pending' if still_pending else 'filled'}, "
                   f"第二根K线{order.status} @ {order.filled_price}",
            details="限价0.16高于市价0.14，等待high=0.165触及后以0.16成交"
        ))
        
        engine.stop()
    
    # ==================== 反向模式测试（通过工具调用）====================
    
    def test_reverse_long_to_short(self):
        """测试：反向模式-做多信号转做空（通过工具调用）
        
        场景：Agent发出做多信号，工具自动反向为做空
        """
        engine = self._create_engine(reverse_mode=True)
        engine.set_simulated_price("TESTUSDT", 0.15)
        
        token = set_engine(engine, thread_local=True)
        try:
            create_limit_order_tool.invoke({
                'symbol': 'TESTUSDT',
                'side': 'BUY',
                'limit_price': 0.14,
                'tp_price': 0.16,
                'sl_price': 0.12
            })
            
            order = list(engine.limit_order_manager.orders.values())[0]
            
            passed = (
                order.side == "short" and
                order.tp_price == 0.12 and
                order.sl_price == 0.16
            )
            
            self._log_result(TestResult(
                name="反向模式-做多转做空",
                passed=passed,
                expected="方向=short, TP=0.12(原SL), SL=0.16(原TP)",
                actual=f"方向={order.side}, TP={order.tp_price}, SL={order.sl_price}",
                details="Agent做多 → 工具反向做空，TP/SL互换"
            ))
        finally:
            reset_context_engine(token)
            engine.stop()
    
    def test_reverse_short_to_long(self):
        """测试：反向模式-做空信号转做多（通过工具调用）
        
        场景：Agent发出做空信号，工具自动反向为做多
        """
        engine = self._create_engine(reverse_mode=True)
        engine.set_simulated_price("TESTUSDT", 0.15)
        
        token = set_engine(engine, thread_local=True)
        try:
            create_limit_order_tool.invoke({
                'symbol': 'TESTUSDT',
                'side': 'SELL',
                'limit_price': 0.16,
                'tp_price': 0.14,
                'sl_price': 0.18
            })
            
            order = list(engine.limit_order_manager.orders.values())[0]
            
            passed = (
                order.side == "long" and
                order.tp_price == 0.18 and
                order.sl_price == 0.14
            )
            
            self._log_result(TestResult(
                name="反向模式-做空转做多",
                passed=passed,
                expected="方向=long, TP=0.18(原SL), SL=0.14(原TP)",
                actual=f"方向={order.side}, TP={order.tp_price}, SL={order.sl_price}",
                details="Agent做空 → 工具反向做多，TP/SL互换"
            ))
        finally:
            reset_context_engine(token)
            engine.stop()
    
    def test_reverse_open_position(self):
        """测试：反向模式-限价单成交后开仓
        
        场景：Agent做多限价单成交后，实际建立做空仓位
        """
        engine = self._create_engine(reverse_mode=True)
        engine.set_simulated_price("TESTUSDT", 0.15)
        
        token = set_engine(engine, thread_local=True)
        try:
            create_limit_order_tool.invoke({
                'symbol': 'TESTUSDT',
                'side': 'BUY',
                'limit_price': 0.16,
                'tp_price': 0.18,
                'sl_price': 0.12
            })
            
            kline = TestKline(
                timestamp=1000,
                open=0.16,
                high=0.165,
                low=0.155,
                close=0.16
            )
            engine.limit_order_manager.on_kline("TESTUSDT", kline.to_dict())
            
            if "TESTUSDT" in engine.positions:
                pos = engine.positions["TESTUSDT"]
                passed = (
                    pos.side == "short" and
                    pos.tp_price == 0.12 and
                    pos.sl_price == 0.18
                )
                actual = f"方向={pos.side}, TP={pos.tp_price}, SL={pos.sl_price}"
            else:
                passed = False
                actual = "未找到仓位"
            
            self._log_result(TestResult(
                name="反向模式-市价开仓",
                passed=passed,
                expected="方向=short, TP=0.12(原SL), SL=0.18(原TP)",
                actual=actual,
                details="Agent做多 → 工具反向做空，限价单成交后建立空头仓位"
            ))
        finally:
            reset_context_engine(token)
            engine.stop()
    
    # ==================== 止盈止损测试 ====================
    
    def test_long_position_take_profit(self):
        """测试：做多仓位止盈触发
        
        场景：做多 @ 0.15，TP=0.18，价格涨到0.18
        """
        engine = self._create_engine(reverse_mode=False)
        
        engine.set_simulated_price("TESTUSDT", 0.15)
        
        result = engine.open_position(
            symbol="TESTUSDT",
            side="long",
            quote_notional_usdt=1000.0,
            leverage=10,
            tp_price=0.18,
            sl_price=0.12,
            entry_price=0.15
        )
        
        close_result = engine.check_tp_sl_simple(
            symbol="TESTUSDT",
            high_price=0.185,
            low_price=0.16
        )
        
        passed = (
            close_result is not None and
            "止盈" in close_result.get("close_reason", "") and
            close_result.get("close_price") == 0.18
        )
        
        self._log_result(TestResult(
            name="做多仓位止盈",
            passed=passed,
            expected="触发止盈 @ 0.18",
            actual=f"close_reason={close_result.get('close_reason') if close_result else None}, "
                   f"close_price={close_result.get('close_price') if close_result else None}",
            details="做多入场0.15，TP=0.18，high=0.185触发止盈"
        ))
        
        engine.stop()
    
    def test_long_position_stop_loss(self):
        """测试：做多仓位止损触发
        
        场景：做多 @ 0.15，SL=0.12，价格跌到0.12
        """
        engine = self._create_engine(reverse_mode=False)
        
        engine.set_simulated_price("TESTUSDT", 0.15)
        
        result = engine.open_position(
            symbol="TESTUSDT",
            side="long",
            quote_notional_usdt=1000.0,
            leverage=10,
            tp_price=0.18,
            sl_price=0.12,
            entry_price=0.15
        )
        
        close_result = engine.check_tp_sl_simple(
            symbol="TESTUSDT",
            high_price=0.14,
            low_price=0.115
        )
        
        passed = (
            close_result is not None and
            "止损" in close_result.get("close_reason", "") and
            close_result.get("close_price") == 0.12
        )
        
        self._log_result(TestResult(
            name="做多仓位止损",
            passed=passed,
            expected="触发止损 @ 0.12",
            actual=f"close_reason={close_result.get('close_reason') if close_result else None}, "
                   f"close_price={close_result.get('close_price') if close_result else None}",
            details="做多入场0.15，SL=0.12，low=0.115触发止损"
        ))
        
        engine.stop()
    
    def test_short_position_take_profit(self):
        """测试：做空仓位止盈触发
        
        场景：做空 @ 0.15，TP=0.12，价格跌到0.12
        """
        engine = self._create_engine(reverse_mode=False)
        
        engine.set_simulated_price("TESTUSDT", 0.15)
        
        result = engine.open_position(
            symbol="TESTUSDT",
            side="short",
            quote_notional_usdt=1000.0,
            leverage=10,
            tp_price=0.12,
            sl_price=0.18,
            entry_price=0.15
        )
        
        close_result = engine.check_tp_sl_simple(
            symbol="TESTUSDT",
            high_price=0.14,
            low_price=0.115
        )
        
        passed = (
            close_result is not None and
            "止盈" in close_result.get("close_reason", "") and
            close_result.get("close_price") == 0.12
        )
        
        self._log_result(TestResult(
            name="做空仓位止盈",
            passed=passed,
            expected="触发止盈 @ 0.12",
            actual=f"close_reason={close_result.get('close_reason') if close_result else None}, "
                   f"close_price={close_result.get('close_price') if close_result else None}",
            details="做空入场0.15，TP=0.12，low=0.115触发止盈"
        ))
        
        engine.stop()
    
    def test_short_position_stop_loss(self):
        """测试：做空仓位止损触发
        
        场景：做空 @ 0.15，SL=0.18，价格涨到0.18
        """
        engine = self._create_engine(reverse_mode=False)
        
        engine.set_simulated_price("TESTUSDT", 0.15)
        
        result = engine.open_position(
            symbol="TESTUSDT",
            side="short",
            quote_notional_usdt=1000.0,
            leverage=10,
            tp_price=0.12,
            sl_price=0.18,
            entry_price=0.15
        )
        
        close_result = engine.check_tp_sl_simple(
            symbol="TESTUSDT",
            high_price=0.185,
            low_price=0.16
        )
        
        passed = (
            close_result is not None and
            "止损" in close_result.get("close_reason", "") and
            close_result.get("close_price") == 0.18
        )
        
        self._log_result(TestResult(
            name="做空仓位止损",
            passed=passed,
            expected="触发止损 @ 0.18",
            actual=f"close_reason={close_result.get('close_reason') if close_result else None}, "
                   f"close_price={close_result.get('close_price') if close_result else None}",
            details="做空入场0.15，SL=0.18，high=0.185触发止损"
        ))
        
        engine.stop()
    
    # ==================== 边界情况测试 ====================
    
    def test_price_exactly_at_limit(self):
        """测试：价格刚好等于限价
        
        场景：做多限价单 0.14，K线 low 刚好等于 0.14
        """
        engine = self._create_engine(reverse_mode=False)
        
        engine.set_simulated_price("TESTUSDT", 0.15)
        
        result = engine.limit_order_manager.create_limit_order(
            symbol="TESTUSDT",
            side="long",
            limit_price=0.14,
            margin_usdt=100.0,
            leverage=10
        )
        
        kline = TestKline(
            timestamp=1000,
            open=0.15,
            high=0.155,
            low=0.14,
            close=0.145
        )
        
        engine.limit_order_manager.on_kline("TESTUSDT", kline.to_dict())
        
        order = list(engine.limit_order_manager.orders.values())[0]
        
        passed = (order.status == "filled" and order.filled_price == 0.14)
        
        self._log_result(TestResult(
            name="边界-价格刚好等于限价",
            passed=passed,
            expected="状态=filled, 成交价=0.14",
            actual=f"状态={order.status}, 成交价={order.filled_price}",
            details="low=0.14 刚好等于限价0.14，应该触发成交"
        ))
        
        engine.stop()
    
    def test_gap_up_open_triggers_short_limit(self):
        """测试：跳空高开触发做空限价单
        
        场景：做空限价单 0.16，但开盘直接跳空到 0.17
        预期：以 0.17（open）成交
        """
        engine = self._create_engine(reverse_mode=False)
        
        engine.set_simulated_price("TESTUSDT", 0.15)
        
        result = engine.limit_order_manager.create_limit_order(
            symbol="TESTUSDT",
            side="short",
            limit_price=0.16,
            margin_usdt=100.0,
            leverage=10
        )
        
        kline = TestKline(
            timestamp=1000,
            open=0.17,
            high=0.175,
            low=0.165,
            close=0.168
        )
        
        engine.limit_order_manager.on_kline("TESTUSDT", kline.to_dict())
        
        order = list(engine.limit_order_manager.orders.values())[0]
        
        passed = (order.status == "filled" and order.filled_price == 0.17)
        
        self._log_result(TestResult(
            name="边界-跳空高开做空",
            passed=passed,
            expected="状态=filled, 成交价=0.17 (open价)",
            actual=f"状态={order.status}, 成交价={order.filled_price}",
            details="限价0.16，跳空高开到0.17，应以0.17成交"
        ))
        
        engine.stop()
    
    def test_gap_down_open_triggers_long_limit(self):
        """测试：跳空低开触发做多限价单
        
        场景：做多限价单 0.14，但开盘直接跳空到 0.13
        预期：以 0.13（open）成交
        """
        engine = self._create_engine(reverse_mode=False)
        
        engine.set_simulated_price("TESTUSDT", 0.15)
        
        result = engine.limit_order_manager.create_limit_order(
            symbol="TESTUSDT",
            side="long",
            limit_price=0.14,
            margin_usdt=100.0,
            leverage=10
        )
        
        kline = TestKline(
            timestamp=1000,
            open=0.13,
            high=0.135,
            low=0.125,
            close=0.132
        )
        
        engine.limit_order_manager.on_kline("TESTUSDT", kline.to_dict())
        
        order = list(engine.limit_order_manager.orders.values())[0]
        
        passed = (order.status == "filled" and order.filled_price == 0.13)
        
        self._log_result(TestResult(
            name="边界-跳空低开做多",
            passed=passed,
            expected="状态=filled, 成交价=0.13 (open价)",
            actual=f"状态={order.status}, 成交价={order.filled_price}",
            details="限价0.14，跳空低开到0.13，应以0.13成交"
        ))
        
        engine.stop()
    
    def test_no_trigger_when_price_not_reached(self):
        """测试：价格未触及限价时不成交
        
        场景：做多限价单 0.12，但价格一直在 0.14-0.16 之间
        """
        engine = self._create_engine(reverse_mode=False)
        
        engine.set_simulated_price("TESTUSDT", 0.15)
        
        result = engine.limit_order_manager.create_limit_order(
            symbol="TESTUSDT",
            side="long",
            limit_price=0.12,
            margin_usdt=100.0,
            leverage=10
        )
        
        for i in range(5):
            kline = TestKline(
                timestamp=1000 + i * 1000,
                open=0.15 + i * 0.002,
                high=0.16 + i * 0.002,
                low=0.14 + i * 0.002,
                close=0.155 + i * 0.002
            )
            engine.limit_order_manager.on_kline("TESTUSDT", kline.to_dict())
        
        order = list(engine.limit_order_manager.orders.values())[0]
        
        passed = (order.status == "pending")
        
        self._log_result(TestResult(
            name="边界-价格未触及限价",
            passed=passed,
            expected="状态=pending (未成交)",
            actual=f"状态={order.status}",
            details="限价0.12，价格范围0.14-0.17，不应触发成交"
        ))
        
        engine.stop()
    
    # ==================== 完整反向交易流程测试（通过工具调用）====================
    
    def test_reverse_complete_flow_profit(self):
        """测试：反向模式完整流程 - 盈利场景（通过工具调用）
        
        场景：
        - Agent信号：做多限价 @ 0.15，TP=0.18，SL=0.12
        - 工具反向后：做空限价 @ 0.15，TP=0.12(原SL)，SL=0.18(原TP)
        - 限价单成交后，价格下跌到 0.12 触发止盈
        """
        engine = self._create_engine(reverse_mode=True)
        engine.set_simulated_price("TESTUSDT", 0.15)
        
        token = set_engine(engine, thread_local=True)
        try:
            create_limit_order_tool.invoke({
                'symbol': 'TESTUSDT',
                'side': 'BUY',
                'limit_price': 0.15,
                'tp_price': 0.18,
                'sl_price': 0.12
            })
            
            kline_fill = TestKline(timestamp=1000, open=0.15, high=0.155, low=0.145, close=0.15)
            engine.limit_order_manager.on_kline("TESTUSDT", kline_fill.to_dict())
            
            pos = engine.positions.get("TESTUSDT")
            is_short = pos and pos.side == "short"
            tp_is_012 = pos and pos.tp_price == 0.12
            sl_is_018 = pos and pos.sl_price == 0.18
            
            close_result = engine.check_tp_sl_simple(
                symbol="TESTUSDT",
                high_price=0.14,
                low_price=0.115
            )
            
            is_tp = close_result and "止盈" in close_result.get("close_reason", "")
            realized_pnl = close_result.get("realized_pnl", 0) if close_result else 0
            
            expected_pnl = 1000.0 * (0.15 - 0.12) / 0.15
            pnl_correct = abs(realized_pnl - expected_pnl) < 1.0
            
            passed = is_short and tp_is_012 and sl_is_018 and is_tp and pnl_correct
            
            self._log_result(TestResult(
                name="反向完整流程-盈利",
                passed=passed,
                expected=f"做空仓位，TP=0.12触发止盈，盈利≈{expected_pnl:.2f}",
                actual=f"方向={'short' if is_short else 'long'}, TP={pos.tp_price if pos else None}, "
                       f"{'止盈' if is_tp else '未触发'}, PnL={realized_pnl:.2f}",
                details="Agent做多 → 工具反向做空，价格下跌后触发止盈"
            ))
        finally:
            reset_context_engine(token)
            engine.stop()
    
    def test_reverse_complete_flow_loss(self):
        """测试：反向模式完整流程 - 亏损场景（通过工具调用）
        
        场景：
        - Agent信号：做多限价 @ 0.15，TP=0.18，SL=0.12
        - 工具反向后：做空限价 @ 0.15，TP=0.12(原SL)，SL=0.18(原TP)
        - 限价单成交后，价格上涨到 0.18 触发止损
        """
        engine = self._create_engine(reverse_mode=True)
        engine.set_simulated_price("TESTUSDT", 0.15)
        
        token = set_engine(engine, thread_local=True)
        try:
            create_limit_order_tool.invoke({
                'symbol': 'TESTUSDT',
                'side': 'BUY',
                'limit_price': 0.15,
                'tp_price': 0.18,
                'sl_price': 0.12
            })
            
            kline_fill = TestKline(timestamp=1000, open=0.15, high=0.155, low=0.145, close=0.15)
            engine.limit_order_manager.on_kline("TESTUSDT", kline_fill.to_dict())
            
            pos = engine.positions.get("TESTUSDT")
            
            close_result = engine.check_tp_sl_simple(
                symbol="TESTUSDT",
                high_price=0.185,
                low_price=0.16
            )
            
            is_sl = close_result and "止损" in close_result.get("close_reason", "")
            realized_pnl = close_result.get("realized_pnl", 0) if close_result else 0
            
            expected_pnl = -1000.0 * (0.18 - 0.15) / 0.15
            pnl_correct = abs(realized_pnl - expected_pnl) < 1.0
            
            passed = is_sl and pnl_correct
            
            self._log_result(TestResult(
                name="反向完整流程-亏损",
                passed=passed,
                expected=f"触发止损，亏损≈{expected_pnl:.2f}",
                actual=f"{'止损' if is_sl else '未触发'}, PnL={realized_pnl:.2f}",
                details="Agent做多 → 工具反向做空，价格上涨后触发止损"
            ))
        finally:
            reset_context_engine(token)
            engine.stop()
    
    # ==================== 非反向模式对照测试 ====================
    
    def test_normal_mode_no_reverse(self):
        """测试：非反向模式保持原方向
        
        场景：验证 reverse_mode=False 时不进行反向
        """
        engine = self._create_engine(reverse_mode=False)
        
        engine.set_simulated_price("TESTUSDT", 0.15)
        
        result = engine.open_position(
            symbol="TESTUSDT",
            side="long",
            quote_notional_usdt=1000.0,
            leverage=10,
            tp_price=0.18,
            sl_price=0.12,
            entry_price=0.15
        )
        
        pos = engine.positions.get("TESTUSDT")
        
        passed = (
            pos is not None and
            pos.side == "long" and
            pos.tp_price == 0.18 and
            pos.sl_price == 0.12
        )
        
        self._log_result(TestResult(
            name="非反向模式-保持原方向",
            passed=passed,
            expected="方向=long, TP=0.18, SL=0.12 (原值不变)",
            actual=f"方向={pos.side if pos else None}, TP={pos.tp_price if pos else None}, SL={pos.sl_price if pos else None}",
            details="reverse_mode=False 时方向和TP/SL保持不变"
        ))
        
        engine.stop()
    
    def run_all_tests(self):
        """运行所有测试"""
        print("=" * 80)
        print("🧪 反向交易回测测试")
        print("=" * 80)
        
        print("\n📌 限价单成交逻辑测试")
        print("-" * 40)
        self.test_long_limit_order_price_above_market()
        self.test_long_limit_order_price_below_market()
        self.test_short_limit_order_price_below_market()
        self.test_short_limit_order_price_above_market()
        
        print("\n📌 反向模式测试")
        print("-" * 40)
        self.test_reverse_long_to_short()
        self.test_reverse_short_to_long()
        self.test_reverse_open_position()
        
        print("\n📌 止盈止损测试")
        print("-" * 40)
        self.test_long_position_take_profit()
        self.test_long_position_stop_loss()
        self.test_short_position_take_profit()
        self.test_short_position_stop_loss()
        
        print("\n📌 边界情况测试")
        print("-" * 40)
        self.test_price_exactly_at_limit()
        self.test_gap_up_open_triggers_short_limit()
        self.test_gap_down_open_triggers_long_limit()
        self.test_no_trigger_when_price_not_reached()
        
        print("\n📌 完整反向流程测试")
        print("-" * 40)
        self.test_reverse_complete_flow_profit()
        self.test_reverse_complete_flow_loss()
        
        print("\n📌 对照测试")
        print("-" * 40)
        self.test_normal_mode_no_reverse()
        
        print("\n" + "=" * 80)
        print("📊 测试结果汇总")
        print("=" * 80)
        
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        total = len(self.results)
        
        print(f"\n总计: {total} 个测试")
        print(f"✅ 通过: {passed}")
        print(f"❌ 失败: {failed}")
        print(f"通过率: {passed/total*100:.1f}%")
        
        if failed > 0:
            print("\n❌ 失败的测试:")
            for r in self.results:
                if not r.passed:
                    print(f"  - {r.name}")
        
        print("\n" + "=" * 80)
        
        return failed == 0


def main():
    tester = ReverseBacktestTester()
    success = tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
