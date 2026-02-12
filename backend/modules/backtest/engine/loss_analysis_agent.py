"""亏损分析Agent - 负责分析亏损交易并生成改进建议

职责：
- 分析亏损交易的根本原因
- 为分析节点和决策节点分别生成具体可操作的注意事项
- 输出结构化的反馈用于注入下一轮workflow
"""
from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from modules.agent.utils.model_factory import get_model_factory, with_retry
from modules.backtest.models import (
    BacktestTradeResult,
    LossAnalysisResult,
    NodeFeedback,
    ReinforcementFeedback,
)
from modules.monitor.utils.logger import get_logger

logger = get_logger('backtest.loss_analysis_agent')


@dataclass
class LossAnalysisContext:
    """亏损分析上下文
    
    包含亏损分析所需的所有信息。
    """
    analysis_output: str
    decision_output: str
    kline_images: Dict[str, str]
    trade_result: BacktestTradeResult
    
    def format_trade_result(self) -> str:
        """格式化交易结果为文本"""
        tr = self.trade_result
        return f"""## 交易结果
- 交易对: {tr.symbol}
- 方向: {tr.side}
- 入场价: ${tr.entry_price}
- 出场价: ${tr.exit_price}
- 止盈价: ${tr.tp_price}
- 止损价: ${tr.sl_price}
- 持仓K线数: {tr.holding_bars}
- 盈亏金额: ${tr.realized_pnl:.2f}
- 平仓原因: {tr.close_reason or tr.exit_type}
"""


class LossAnalysisAgent:
    """亏损复盘分析Agent
    
    使用大模型分析亏损交易，生成分节点的注意事项反馈。
    """
    
    def __init__(self):
        """初始化Agent"""
        self._model = None
        self._system_prompt = None
    
    @property
    def model(self):
        """懒加载模型实例"""
        if self._model is None:
            self._model = get_model_factory().get_model(
                temperature=0.0,
                timeout=300,
                max_tokens=4000,
                thinking_enabled=True,
            )
        return self._model
    
    @property
    def system_prompt(self) -> str:
        """懒加载系统提示词"""
        if self._system_prompt is None:
            prompt_path = os.path.join(
                os.path.dirname(__file__), 
                'prompts/loss_analysis_prompt.md'
            )
            with open(prompt_path, 'r', encoding='utf-8') as f:
                self._system_prompt = f.read().strip()
        return self._system_prompt
    
    def analyze(self, context: LossAnalysisContext) -> LossAnalysisResult:
        """分析亏损交易并生成反馈
        
        Args:
            context: 包含分析输出、决策输出、K线图像和交易结果的上下文
            
        Returns:
            LossAnalysisResult 包含分节点的反馈和原始响应
        """
        logger.info(f"开始分析亏损交易: {context.trade_result.symbol} "
                   f"PnL={context.trade_result.realized_pnl:.2f}")
        
        messages = self._build_messages(context)
        
        @with_retry(max_retries=3, retryable_exceptions=(Exception,))
        def _invoke_with_retry():
            return self.model.invoke(messages)
        
        try:
            response = _invoke_with_retry()
            raw_content = response.content if hasattr(response, 'content') else str(response)
            
            feedback = self._parse_response(raw_content)
            
            logger.info(f"亏损分析完成: analysis_issues={len(feedback.analysis_node_feedback.issues) if feedback.analysis_node_feedback else 0}, "
                       f"decision_issues={len(feedback.decision_node_feedback.issues) if feedback.decision_node_feedback else 0}")
            
            return LossAnalysisResult(
                feedback=feedback,
                raw_response=raw_content,
            )
            
        except Exception as e:
            logger.error(f"亏损分析失败: {e}", exc_info=True)
            return LossAnalysisResult(
                feedback=ReinforcementFeedback(
                    analysis_node_feedback=NodeFeedback(
                        node_name="single_symbol_analysis",
                        issues=["分析过程出现异常，无法生成具体问题"],
                        attention_points=["请更谨慎地分析K线结构"],
                    ),
                    decision_node_feedback=NodeFeedback(
                        node_name="opening_decision",
                        issues=[],
                        attention_points=[],
                    ),
                    summary=f"亏损分析异常: {str(e)}",
                ),
                raw_response=f"Error: {str(e)}",
            )
    
    def _build_messages(self, context: LossAnalysisContext) -> List:
        """构建消息列表"""
        content = []
        
        text_intro = f"""# 亏损交易复盘

{context.format_trade_result()}

## 分析节点输出 (single_symbol_analysis_node)
```
{context.analysis_output}
```

## 决策节点输出 (opening_decision_node)
```
{context.decision_output}
```

## K线图像
以下是当时分析的K线图，请仔细观察：
"""
        content.append({"type": "text", "text": text_intro})
        
        interval_order = ["1h", "15m", "3m"]
        for interval in interval_order:
            if interval in context.kline_images:
                image_path = context.kline_images[interval]
                image_base64 = self._load_image_as_base64(image_path)
                if image_base64:
                    content.append({"type": "text", "text": f"\n### {interval} 周期"})
                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_base64}",
                            "detail": "high"
                        }
                    })
        
        content.append({
            "type": "text", 
            "text": "\n\n请根据以上信息，分析亏损原因并生成JSON格式的反馈。"
        })
        
        return [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=content),
        ]
    
    def _load_image_as_base64(self, image_path: str) -> Optional[str]:
        """加载图片并转为base64"""
        if not image_path or not os.path.exists(image_path):
            logger.warning(f"图片文件不存在: {image_path}")
            return None
        
        try:
            with open(image_path, 'rb') as f:
                return base64.b64encode(f.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"加载图片失败 {image_path}: {e}")
            return None
    
    def _parse_response(self, raw_content: str) -> ReinforcementFeedback:
        """解析模型响应为结构化反馈"""
        json_str = self._extract_json(raw_content)
        
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}, 原始内容: {json_str[:500]}")
            return self._create_fallback_feedback(raw_content)
        
        analysis_fb = None
        if data.get("analysis_node_feedback"):
            analysis_fb = NodeFeedback(
                node_name=data["analysis_node_feedback"].get("node_name", "single_symbol_analysis"),
                issues=data["analysis_node_feedback"].get("issues", []),
                attention_points=data["analysis_node_feedback"].get("attention_points", []),
            )
        
        decision_fb = None
        if data.get("decision_node_feedback"):
            decision_fb = NodeFeedback(
                node_name=data["decision_node_feedback"].get("node_name", "opening_decision"),
                issues=data["decision_node_feedback"].get("issues", []),
                attention_points=data["decision_node_feedback"].get("attention_points", []),
            )
        
        return ReinforcementFeedback(
            analysis_node_feedback=analysis_fb,
            decision_node_feedback=decision_fb,
            summary=data.get("summary", ""),
        )
    
    def _extract_json(self, raw_content: str) -> str:
        """从响应中提取JSON字符串"""
        content = raw_content.strip()
        
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        
        start_idx = content.find('{')
        end_idx = content.rfind('}')
        
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            content = content[start_idx:end_idx + 1]
        
        return content.strip()
    
    def _create_fallback_feedback(self, raw_content: str) -> ReinforcementFeedback:
        """创建降级反馈（当解析失败时）"""
        return ReinforcementFeedback(
            analysis_node_feedback=NodeFeedback(
                node_name="single_symbol_analysis",
                issues=["模型响应解析失败"],
                attention_points=["请更谨慎地分析K线结构和形态"],
            ),
            decision_node_feedback=NodeFeedback(
                node_name="opening_decision",
                issues=[],
                attention_points=["请仔细复核分析结论后再决策"],
            ),
            summary=f"响应解析失败，原始内容: {raw_content[:200]}...",
        )
