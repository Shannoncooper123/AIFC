"""强化学习引擎 - 负责协调亏损交易的多轮重试优化

职责：
- 检测亏损交易并触发强化学习流程
- 调用 LossAnalysisAgent 生成反馈
- 重新执行 workflow 并注入反馈
- 跟踪多轮迭代（最多3轮）
- 记录完整的可追溯数据
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from modules.backtest.engine.loss_analysis_agent import LossAnalysisAgent, LossAnalysisContext
from modules.backtest.engine.reinforcement_storage import ReinforcementStorage
from modules.backtest.models import (
    BacktestConfig,
    BacktestTradeResult,
    ReinforcementFeedback,
    ReinforcementRound,
    ReinforcementSession,
)
from modules.agent.utils.workflow_trace_storage import (
    generate_trace_id,
    get_workflow_trace_path,
)
from modules.monitor.utils.logger import get_logger

if TYPE_CHECKING:
    from modules.backtest.providers.kline_provider import BacktestKlineProvider

logger = get_logger('backtest.reinforcement_engine')


class ReinforcementLearningEngine:
    """强化学习主控制器
    
    对亏损交易进行多轮分析和重试，观察agent是否能从反馈中学习并改进决策。
    """
    
    MAX_ROUNDS = 3
    
    def __init__(
        self,
        config: BacktestConfig,
        kline_provider: "BacktestKlineProvider",
        backtest_id: str,
        base_dir: str,
    ):
        """初始化强化学习引擎
        
        Args:
            config: 回测配置
            kline_provider: K线数据提供者
            backtest_id: 回测ID
            base_dir: 基础数据目录
        """
        self.config = config
        self.kline_provider = kline_provider
        self.backtest_id = backtest_id
        self.base_dir = base_dir
        
        self._loss_analysis_agent = LossAnalysisAgent()
        self._storage = ReinforcementStorage(backtest_id, base_dir)
        
        self._workflow_executor = None
    
    def set_workflow_executor(self, executor) -> None:
        """设置 workflow 执行器（用于重新执行 workflow）"""
        self._workflow_executor = executor
    
    def should_run_reinforcement(self, trade_result: BacktestTradeResult) -> bool:
        """判断是否应该对该交易执行强化学习
        
        只对亏损交易执行强化学习。
        
        Args:
            trade_result: 交易结果
            
        Returns:
            是否应该执行强化学习
        """
        if trade_result.exit_type == "sl":
            return True
        if trade_result.realized_pnl < 0:
            return True
        return False
    
    def run_reinforcement_loop(
        self,
        original_workflow_run_id: str,
        original_trade_result: BacktestTradeResult,
        analysis_output: str,
        decision_output: str,
        kline_time: datetime,
    ) -> ReinforcementSession:
        """执行强化学习循环
        
        Args:
            original_workflow_run_id: 原始 workflow 运行ID
            original_trade_result: 原始交易结果（亏损）
            analysis_output: 分析节点输出
            decision_output: 决策节点输出
            kline_time: K线时间点
            
        Returns:
            完整的强化学习会话记录
        """
        session_id = generate_trace_id("rl")
        symbol = original_trade_result.symbol
        
        logger.info(
            f"开始强化学习: session={session_id}, symbol={symbol}, "
            f"time={kline_time}, original_pnl={original_trade_result.realized_pnl:.2f}"
        )
        
        session = ReinforcementSession(
            session_id=session_id,
            symbol=symbol,
            kline_time=kline_time,
            backtest_id=self.backtest_id,
        )
        
        kline_images = self._collect_kline_images(original_workflow_run_id)
        
        round1 = ReinforcementRound(
            round_number=1,
            workflow_run_id=original_workflow_run_id,
            injected_feedback=None,
            analysis_output=analysis_output,
            decision_output=decision_output,
            kline_images=kline_images,
            trade_result=original_trade_result,
            outcome="loss",
        )
        
        context = LossAnalysisContext(
            analysis_output=analysis_output,
            decision_output=decision_output,
            kline_images=kline_images,
            trade_result=original_trade_result,
        )
        round1.loss_analysis = self._loss_analysis_agent.analyze(context)
        session.rounds.append(round1)
        
        current_feedback = round1.loss_analysis.feedback
        
        for round_num in range(2, self.MAX_ROUNDS + 1):
            logger.info(f"强化学习第 {round_num} 轮: session={session_id}")
            
            round_result = self._execute_round_with_feedback(
                round_num=round_num,
                kline_time=kline_time,
                symbol=symbol,
                feedback=current_feedback,
            )
            
            session.rounds.append(round_result)
            
            if round_result.outcome != "loss":
                logger.info(
                    f"强化学习成功改进: session={session_id}, "
                    f"round={round_num}, outcome={round_result.outcome}"
                )
                session.improvement_achieved = True
                break
            
            if round_result.trade_result:
                context = LossAnalysisContext(
                    analysis_output=round_result.analysis_output,
                    decision_output=round_result.decision_output,
                    kline_images=round_result.kline_images,
                    trade_result=round_result.trade_result,
                )
                round_result.loss_analysis = self._loss_analysis_agent.analyze(context)
                current_feedback = round_result.loss_analysis.feedback
        
        session.total_rounds = len(session.rounds)
        session.final_outcome = session.rounds[-1].outcome
        
        self._storage.save_session(session)
        
        logger.info(
            f"强化学习完成: session={session_id}, "
            f"rounds={session.total_rounds}, "
            f"final_outcome={session.final_outcome}, "
            f"improved={session.improvement_achieved}"
        )
        
        return session
    
    def _execute_round_with_feedback(
        self,
        round_num: int,
        kline_time: datetime,
        symbol: str,
        feedback: ReinforcementFeedback,
    ) -> ReinforcementRound:
        """执行带反馈注入的单轮workflow
        
        Args:
            round_num: 轮次号
            kline_time: K线时间点
            symbol: 交易对
            feedback: 要注入的反馈
            
        Returns:
            本轮记录
        """
        if self._workflow_executor is None:
            logger.error("WorkflowExecutor 未设置，无法执行重试")
            return ReinforcementRound(
                round_number=round_num,
                workflow_run_id="",
                injected_feedback=feedback,
                outcome="error",
            )
        
        workflow_run_id, trade_results, _, is_timeout = self._workflow_executor.execute_step(
            current_time=kline_time,
            step_index=-round_num,
            reinforcement_feedback=feedback,
        )
        
        analysis_output = ""
        decision_output = ""
        kline_images = self._collect_kline_images(workflow_run_id)
        
        trade_result = None
        outcome = "no_trade"
        
        if is_timeout:
            outcome = "timeout"
        elif trade_results:
            trade_result = trade_results[0]
            if trade_result.realized_pnl >= 0:
                outcome = "profit"
            else:
                outcome = "loss"
        
        return ReinforcementRound(
            round_number=round_num,
            workflow_run_id=workflow_run_id,
            injected_feedback=feedback,
            analysis_output=analysis_output,
            decision_output=decision_output,
            kline_images=kline_images,
            trade_result=trade_result,
            outcome=outcome,
        )
    
    def _collect_kline_images(self, workflow_run_id: str) -> Dict[str, str]:
        """从 workflow trace 中收集K线图像路径
        
        Args:
            workflow_run_id: workflow 运行ID
            
        Returns:
            {interval: file_path} 映射
        """
        images = {}
        trace_path = get_workflow_trace_path(workflow_run_id)
        
        if not os.path.exists(trace_path):
            logger.warning(f"Trace 文件不存在: {trace_path}")
            return images
        
        try:
            with open(trace_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                        if event.get("type") == "artifact":
                            payload = event.get("payload", {})
                            artifact_type = payload.get("artifact_type")
                            if artifact_type == "kline_image":
                                interval = payload.get("interval", "")
                                file_path = payload.get("file_path", "")
                                if interval and file_path:
                                    images[interval] = file_path
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error(f"收集K线图像失败: {e}")
        
        return images
    
    def get_storage(self) -> ReinforcementStorage:
        """获取存储管理器"""
        return self._storage
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取强化学习统计信息"""
        return self._storage.get_statistics()
