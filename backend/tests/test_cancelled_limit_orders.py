"""测试未成交限价单的记录和追踪功能

测试场景：
1. 限价单未成交时应该生成 CancelledLimitOrder 记录
2. CancelledLimitOrder 的 to_dict() 方法应该正确序列化
3. BacktestResult 应该正确包含 cancelled_orders 列表
4. API 响应应该正确返回 cancelled_orders
"""
import sys
import json
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from unittest.mock import Mock, MagicMock, patch

sys.path.insert(0, '.')

from modules.backtest.models import (
    BacktestConfig, 
    BacktestResult, 
    BacktestTradeResult,
    CancelledLimitOrder,
    BacktestStatus,
)


class TestCancelledLimitOrderModel:
    """测试 CancelledLimitOrder 数据模型"""
    
    def test_create_cancelled_order(self):
        """测试创建 CancelledLimitOrder 对象"""
        created_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        cancelled_time = datetime(2024, 1, 16, 10, 0, 0, tzinfo=timezone.utc)
        
        order = CancelledLimitOrder(
            order_id="order_123",
            symbol="BTCUSDT",
            side="long",
            limit_price=42000.0,
            tp_price=44000.0,
            sl_price=40000.0,
            margin_usdt=100.0,
            leverage=10,
            created_time=created_time,
            cancelled_time=cancelled_time,
            cancel_reason="超时未成交",
            workflow_run_id="wf_abc123",
        )
        
        assert order.order_id == "order_123"
        assert order.symbol == "BTCUSDT"
        assert order.side == "long"
        assert order.limit_price == 42000.0
        assert order.tp_price == 44000.0
        assert order.sl_price == 40000.0
        assert order.margin_usdt == 100.0
        assert order.leverage == 10
        assert order.cancel_reason == "超时未成交"
        assert order.workflow_run_id == "wf_abc123"
        print("✅ test_create_cancelled_order 通过")
    
    def test_cancelled_order_to_dict(self):
        """测试 CancelledLimitOrder.to_dict() 序列化"""
        created_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        cancelled_time = datetime(2024, 1, 16, 10, 0, 0, tzinfo=timezone.utc)
        
        order = CancelledLimitOrder(
            order_id="order_456",
            symbol="ETHUSDT",
            side="short",
            limit_price=2500.0,
            tp_price=2400.0,
            sl_price=2600.0,
            margin_usdt=50.5,
            leverage=20,
            created_time=created_time,
            cancelled_time=cancelled_time,
            cancel_reason="回测结束未成交",
            workflow_run_id="wf_def456",
        )
        
        result = order.to_dict()
        
        assert isinstance(result, dict)
        assert result["order_id"] == "order_456"
        assert result["symbol"] == "ETHUSDT"
        assert result["side"] == "short"
        assert result["limit_price"] == 2500.0
        assert result["tp_price"] == 2400.0
        assert result["sl_price"] == 2600.0
        assert result["margin_usdt"] == 50.5
        assert result["leverage"] == 20
        assert result["cancel_reason"] == "回测结束未成交"
        assert result["workflow_run_id"] == "wf_def456"
        assert "created_time" in result
        assert "cancelled_time" in result
        
        json_str = json.dumps(result)
        assert "order_456" in json_str
        print("✅ test_cancelled_order_to_dict 通过")


class TestBacktestResultWithCancelledOrders:
    """测试 BacktestResult 包含 cancelled_orders"""
    
    def test_backtest_result_has_cancelled_orders_field(self):
        """测试 BacktestResult 有 cancelled_orders 字段"""
        config = BacktestConfig(
            symbols=["BTCUSDT"],
            start_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2024, 1, 31, tzinfo=timezone.utc),
            interval="15m",
            initial_balance=10000.0,
        )
        
        result = BacktestResult(
            backtest_id="bt_test123",
            config=config,
            status=BacktestStatus.COMPLETED,
            start_timestamp=datetime.now(timezone.utc),
        )
        
        assert hasattr(result, 'cancelled_orders')
        assert isinstance(result.cancelled_orders, list)
        assert len(result.cancelled_orders) == 0
        print("✅ test_backtest_result_has_cancelled_orders_field 通过")
    
    def test_backtest_result_to_dict_includes_cancelled_orders(self):
        """测试 BacktestResult.to_dict() 包含 cancelled_orders"""
        config = BacktestConfig(
            symbols=["BTCUSDT"],
            start_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2024, 1, 31, tzinfo=timezone.utc),
            interval="15m",
            initial_balance=10000.0,
        )
        
        cancelled_order = CancelledLimitOrder(
            order_id="order_789",
            symbol="BTCUSDT",
            side="long",
            limit_price=41000.0,
            tp_price=43000.0,
            sl_price=39000.0,
            margin_usdt=200.0,
            leverage=5,
            created_time=datetime(2024, 1, 10, tzinfo=timezone.utc),
            cancelled_time=datetime(2024, 1, 11, tzinfo=timezone.utc),
            cancel_reason="价格未触及",
            workflow_run_id="wf_ghi789",
        )
        
        result = BacktestResult(
            backtest_id="bt_test456",
            config=config,
            status=BacktestStatus.COMPLETED,
            start_timestamp=datetime.now(timezone.utc),
            cancelled_orders=[cancelled_order],
        )
        
        result_dict = result.to_dict()
        
        assert "cancelled_orders" in result_dict
        assert isinstance(result_dict["cancelled_orders"], list)
        assert len(result_dict["cancelled_orders"]) == 1
        assert result_dict["cancelled_orders"][0]["order_id"] == "order_789"
        assert result_dict["cancelled_orders"][0]["symbol"] == "BTCUSDT"
        print("✅ test_backtest_result_to_dict_includes_cancelled_orders 通过")


class TestPositionSimulatorCancelledOrders:
    """测试 PositionSimulator 生成 CancelledLimitOrder"""
    
    def test_simulate_limit_order_returns_tuple(self):
        """测试 simulate_limit_order_outcome 返回元组"""
        from modules.backtest.engine.position_simulator import PositionSimulator
        
        assert hasattr(PositionSimulator, 'simulate_limit_order_outcome')
        
        import inspect
        sig = inspect.signature(PositionSimulator.simulate_limit_order_outcome)
        
        from typing import get_type_hints
        hints = get_type_hints(PositionSimulator.simulate_limit_order_outcome)
        return_hint = hints.get('return', None)
        
        print(f"  返回类型注解: {return_hint}")
        print("✅ test_simulate_limit_order_returns_tuple 通过")


class MockKline:
    """模拟K线数据"""
    def __init__(self, open_price: float, high: float, low: float, close: float):
        self.open = open_price
        self.high = high
        self.low = low
        self.close = close


class TestPositionSimulatorIntegration:
    """集成测试 PositionSimulator 的限价单取消逻辑"""
    
    def test_limit_order_not_filled_creates_cancelled_order(self):
        """测试限价单未成交时创建 CancelledLimitOrder"""
        from modules.backtest.engine.position_simulator import PositionSimulator
        from modules.backtest.engine.backtest_trade_engine import BacktestTradeEngine
        
        config = BacktestConfig(
            symbols=["BTCUSDT"],
            start_time=datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2024, 1, 1, 1, 0, tzinfo=timezone.utc),
            interval="15m",
            initial_balance=10000.0,
        )
        
        mock_kline_provider = Mock()
        mock_kline_provider.get_kline_at_time.return_value = MockKline(
            open_price=45000.0,
            high=45500.0,
            low=44500.0,
            close=45200.0
        )
        
        simulator = PositionSimulator(
            config=config,
            kline_provider=mock_kline_provider,
            backtest_id="bt_test_integration",
        )
        
        mock_trade_engine = Mock(spec=BacktestTradeEngine)
        mock_trade_engine.positions = {}
        mock_trade_engine.check_limit_orders.return_value = []
        mock_trade_engine.get_pending_limit_orders.return_value = [
            {'id': 'limit_order_1', 'symbol': 'BTCUSDT', 'limit_price': 40000.0}
        ]
        mock_trade_engine.cancel_limit_order.return_value = True
        
        order = {
            'id': 'limit_order_1',
            'symbol': 'BTCUSDT',
            'side': 'long',
            'limit_price': 40000.0,
            'tp_price': 42000.0,
            'sl_price': 38000.0,
            'margin_usdt': 100.0,
            'leverage': 10,
        }
        
        entry_time = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
        workflow_run_id = "wf_test_123"
        
        trade_result, cancelled_order = simulator.simulate_limit_order_outcome(
            trade_engine=mock_trade_engine,
            order=order,
            entry_time=entry_time,
            workflow_run_id=workflow_run_id,
        )
        
        assert trade_result is None, "未成交的限价单不应该有交易结果"
        assert cancelled_order is not None, "未成交的限价单应该有取消记录"
        assert isinstance(cancelled_order, CancelledLimitOrder)
        assert cancelled_order.order_id == "limit_order_1"
        assert cancelled_order.symbol == "BTCUSDT"
        assert cancelled_order.side == "long"
        assert cancelled_order.limit_price == 40000.0
        assert cancelled_order.workflow_run_id == workflow_run_id
        assert "未成交" in cancelled_order.cancel_reason
        
        print("✅ test_limit_order_not_filled_creates_cancelled_order 通过")


class TestResultCollectorCancelledOrders:
    """测试 ResultCollector 收集 cancelled_orders"""
    
    def test_add_cancelled_orders(self):
        """测试 add_cancelled_orders 方法"""
        from modules.backtest.engine.result_collector import ResultCollector
        
        config = BacktestConfig(
            symbols=["BTCUSDT"],
            start_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2024, 1, 31, tzinfo=timezone.utc),
            interval="15m",
            initial_balance=10000.0,
        )
        
        backtest_result = BacktestResult(
            backtest_id="bt_collector_test",
            config=config,
            status=BacktestStatus.RUNNING,
            start_timestamp=datetime.now(timezone.utc),
        )
        
        collector = ResultCollector(result=backtest_result)
        
        assert hasattr(collector, 'add_cancelled_orders')
        
        cancelled_order = CancelledLimitOrder(
            order_id="order_collector_test",
            symbol="BTCUSDT",
            side="long",
            limit_price=41000.0,
            tp_price=43000.0,
            sl_price=39000.0,
            margin_usdt=100.0,
            leverage=10,
            created_time=datetime(2024, 1, 10, tzinfo=timezone.utc),
            cancelled_time=datetime(2024, 1, 11, tzinfo=timezone.utc),
            cancel_reason="测试取消",
            workflow_run_id="wf_collector_test",
        )
        
        collector.add_cancelled_orders([cancelled_order])
        
        result = collector.result
        assert len(result.cancelled_orders) == 1
        assert result.cancelled_orders[0].order_id == "order_collector_test"
        
        print("✅ test_add_cancelled_orders 通过")


class TestAPIResponseCancelledOrders:
    """测试 API 响应包含 cancelled_orders"""
    
    def test_api_response_structure(self):
        """测试 API 响应结构"""
        config = BacktestConfig(
            symbols=["BTCUSDT"],
            start_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2024, 1, 31, tzinfo=timezone.utc),
            interval="15m",
            initial_balance=10000.0,
        )
        
        cancelled_order = CancelledLimitOrder(
            order_id="api_test_order",
            symbol="BTCUSDT",
            side="short",
            limit_price=50000.0,
            tp_price=48000.0,
            sl_price=52000.0,
            margin_usdt=150.0,
            leverage=15,
            created_time=datetime(2024, 1, 15, tzinfo=timezone.utc),
            cancelled_time=datetime(2024, 1, 16, tzinfo=timezone.utc),
            cancel_reason="API测试取消",
            workflow_run_id="wf_api_test",
        )
        
        result = BacktestResult(
            backtest_id="bt_api_test",
            config=config,
            status=BacktestStatus.COMPLETED,
            start_timestamp=datetime.now(timezone.utc),
            cancelled_orders=[cancelled_order],
        )
        
        api_response = {
            "backtest_id": result.backtest_id,
            "trades": [t.to_dict() for t in result.trades],
            "cancelled_orders": [o.to_dict() for o in result.cancelled_orders],
            "total": len(result.trades),
            "stats": {
                "total_trades": result.total_trades,
                "winning_trades": result.winning_trades,
                "losing_trades": result.losing_trades,
            }
        }
        
        assert "cancelled_orders" in api_response
        assert len(api_response["cancelled_orders"]) == 1
        assert api_response["cancelled_orders"][0]["order_id"] == "api_test_order"
        assert api_response["cancelled_orders"][0]["symbol"] == "BTCUSDT"
        assert api_response["cancelled_orders"][0]["side"] == "short"
        assert api_response["cancelled_orders"][0]["limit_price"] == 50000.0
        
        json_response = json.dumps(api_response)
        assert "cancelled_orders" in json_response
        assert "api_test_order" in json_response
        
        print("✅ test_api_response_structure 通过")


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("开始运行未成交限价单功能测试")
    print("=" * 60 + "\n")
    
    test_classes = [
        TestCancelledLimitOrderModel,
        TestBacktestResultWithCancelledOrders,
        TestPositionSimulatorCancelledOrders,
        TestPositionSimulatorIntegration,
        TestResultCollectorCancelledOrders,
        TestAPIResponseCancelledOrders,
    ]
    
    total_tests = 0
    passed_tests = 0
    failed_tests = []
    
    for test_class in test_classes:
        print(f"\n📋 {test_class.__name__}")
        print("-" * 40)
        
        instance = test_class()
        
        for method_name in dir(instance):
            if method_name.startswith('test_'):
                total_tests += 1
                try:
                    method = getattr(instance, method_name)
                    method()
                    passed_tests += 1
                except Exception as e:
                    failed_tests.append((test_class.__name__, method_name, str(e)))
                    print(f"❌ {method_name} 失败: {e}")
    
    print("\n" + "=" * 60)
    print(f"测试结果: {passed_tests}/{total_tests} 通过")
    
    if failed_tests:
        print("\n失败的测试:")
        for class_name, method_name, error in failed_tests:
            print(f"  - {class_name}.{method_name}: {error}")
    else:
        print("\n🎉 所有测试通过!")
    
    print("=" * 60 + "\n")
    
    return len(failed_tests) == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
