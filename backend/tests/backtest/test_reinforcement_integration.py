"""测试强化学习集成 - 验证亏损交易触发强化学习流程"""
import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch
from dataclasses import dataclass

from modules.backtest.models import (
    BacktestConfig,
    BacktestTradeResult,
    ReinforcementFeedback,
    NodeFeedback,
    LossAnalysisResult,
)
from modules.backtest.engine.reinforcement_learning_engine import ReinforcementLearningEngine


@pytest.fixture
def sample_losing_trade():
    """创建一个亏损交易结果"""
    return BacktestTradeResult(
        trade_id="test_trade_001",
        kline_time=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
        symbol="BTCUSDT",
        side="long",
        entry_price=50000.0,
        exit_price=49500.0,
        tp_price=51000.0,
        sl_price=49500.0,
        size=0.01,
        exit_time=datetime(2025, 1, 1, 13, 0, tzinfo=timezone.utc),
        exit_type="sl",
        realized_pnl=-50.0,
        pnl_percent=-1.0,
        holding_bars=4,
        workflow_run_id="test_wf_001",
    )


@pytest.fixture
def sample_winning_trade():
    """创建一个盈利交易结果"""
    return BacktestTradeResult(
        trade_id="test_trade_002",
        kline_time=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
        symbol="ETHUSDT",
        side="long",
        entry_price=3000.0,
        exit_price=3100.0,
        tp_price=3100.0,
        sl_price=2900.0,
        size=0.1,
        exit_time=datetime(2025, 1, 1, 14, 0, tzinfo=timezone.utc),
        exit_type="tp",
        realized_pnl=100.0,
        pnl_percent=3.33,
        holding_bars=8,
        workflow_run_id="test_wf_002",
    )


class TestShouldRunReinforcement:
    """测试 should_run_reinforcement 方法的判断逻辑"""
    
    def test_returns_true_for_stop_loss_exit(self, sample_losing_trade):
        """止损出场的交易应该触发强化学习"""
        engine = ReinforcementLearningEngine(
            config=Mock(),
            kline_provider=Mock(),
            backtest_id="test_bt_001",
            base_dir="/tmp/test",
        )
        
        assert engine.should_run_reinforcement(sample_losing_trade) is True
    
    def test_returns_true_for_negative_pnl(self, sample_winning_trade):
        """负盈亏的交易应该触发强化学习"""
        engine = ReinforcementLearningEngine(
            config=Mock(),
            kline_provider=Mock(),
            backtest_id="test_bt_001",
            base_dir="/tmp/test",
        )
        
        sample_winning_trade.realized_pnl = -10.0
        sample_winning_trade.exit_type = "timeout"
        
        assert engine.should_run_reinforcement(sample_winning_trade) is True
    
    def test_returns_false_for_profitable_trade(self, sample_winning_trade):
        """盈利交易不应该触发强化学习"""
        engine = ReinforcementLearningEngine(
            config=Mock(),
            kline_provider=Mock(),
            backtest_id="test_bt_001",
            base_dir="/tmp/test",
        )
        
        assert engine.should_run_reinforcement(sample_winning_trade) is False


class TestBacktestEngineReinforcementIntegration:
    """测试 BacktestEngine 调用强化学习引擎的集成"""
    
    def test_losing_trade_triggers_reinforcement_analysis(self, sample_losing_trade):
        """亏损交易应该触发强化学习分析流程"""
        from modules.backtest.engine.backtest_engine import BacktestEngine
        
        config = BacktestConfig(
            symbols=["BTCUSDT"],
            start_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2025, 1, 2, tzinfo=timezone.utc),
            enable_reinforcement=True,
        )
        
        engine = BacktestEngine(config=config, enable_reinforcement=True)
        
        assert engine.enable_reinforcement is True
        
        mock_rl_engine = Mock(spec=ReinforcementLearningEngine)
        mock_rl_engine.should_run_reinforcement.return_value = True
        mock_rl_engine.run_reinforcement_loop.return_value = Mock()
        engine._reinforcement_engine = mock_rl_engine
        
        engine._handle_trade_results(
            workflow_run_id="test_wf_001",
            trade_results=[sample_losing_trade],
            kline_time=sample_losing_trade.kline_time,
            analysis_outputs={"BTCUSDT": "test analysis"},
            decision_outputs={"BTCUSDT": "test decision"},
        )
        
        mock_rl_engine.should_run_reinforcement.assert_called_once_with(sample_losing_trade)
        mock_rl_engine.run_reinforcement_loop.assert_called_once()
    
    def test_winning_trade_does_not_trigger_reinforcement(self, sample_winning_trade):
        """盈利交易不应该触发强化学习分析"""
        from modules.backtest.engine.backtest_engine import BacktestEngine
        
        config = BacktestConfig(
            symbols=["ETHUSDT"],
            start_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2025, 1, 2, tzinfo=timezone.utc),
            enable_reinforcement=True,
        )
        
        engine = BacktestEngine(config=config, enable_reinforcement=True)
        
        mock_rl_engine = Mock(spec=ReinforcementLearningEngine)
        mock_rl_engine.should_run_reinforcement.return_value = False
        engine._reinforcement_engine = mock_rl_engine
        
        engine._handle_trade_results(
            workflow_run_id="test_wf_002",
            trade_results=[sample_winning_trade],
            kline_time=sample_winning_trade.kline_time,
            analysis_outputs={"ETHUSDT": "test analysis"},
            decision_outputs={"ETHUSDT": "test decision"},
        )
        
        mock_rl_engine.should_run_reinforcement.assert_called_once_with(sample_winning_trade)
        mock_rl_engine.run_reinforcement_loop.assert_not_called()
    
    def test_reinforcement_disabled_skips_analysis(self, sample_losing_trade):
        """禁用强化学习时不应该进行分析"""
        from modules.backtest.engine.backtest_engine import BacktestEngine
        
        config = BacktestConfig(
            symbols=["BTCUSDT"],
            start_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2025, 1, 2, tzinfo=timezone.utc),
            enable_reinforcement=False,
        )
        
        engine = BacktestEngine(config=config, enable_reinforcement=False)
        
        assert engine.enable_reinforcement is False
        assert engine._reinforcement_engine is None
        
        engine._handle_trade_results(
            workflow_run_id="test_wf_001",
            trade_results=[sample_losing_trade],
            kline_time=sample_losing_trade.kline_time,
            analysis_outputs={"BTCUSDT": "test analysis"},
            decision_outputs={"BTCUSDT": "test decision"},
        )
