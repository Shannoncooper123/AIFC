"""决策验证中间件：基于 logprobs 计算工具调用置信度"""
from __future__ import annotations
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional
import json
import os

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import ToolMessage, AIMessage
from langgraph.types import Command

from modules.monitor.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Awaitable
    from langchain.tools.tool_node import ToolCallRequest

logger = get_logger('agent.decision_verification_middleware')


class DecisionVerificationMiddleware(AgentMiddleware[dict, Any]):
    """决策验证中间件
    
    职责：
    - 拦截关键工具调用（如 open_position）
    - 从模型响应中提取布尔检查点参数的 logprobs
    - 计算加权置信度分数
    - 根据阈值决定是否放行执行
    - 将验证结果附加到 state，供追踪中间件记录
    
    使用方法：
        verification_middleware = DecisionVerificationMiddleware(config)
        agent = create_agent(
            model,
            tools,
            middleware=[
                session_middleware,
                verification_middleware,  # 在 tracing 之前
                tracing_middleware,
                ...
            ]
        )
    """
    
    state_schema = dict
    
    def __init__(self, config: Dict[str, Any]):
        """初始化决策验证中间件
        
        Args:
            config: 验证配置字典，必须包含 enabled, threshold, weights, target_tools
        
        Raises:
            ValueError: 如果配置缺失或无效
        """
        super().__init__()
        self.tools = []
        
        if not config:
            raise ValueError("决策验证中间件配置不能为空，必须从 config.yaml 读取")
        
        # 验证必需字段
        required_fields = ['enabled', 'threshold', 'weights', 'target_tools']
        for field in required_fields:
            if field not in config:
                raise ValueError(f"决策验证配置缺少必需字段: {field}")
        
        self.config = config
        
        # 从环境变量读取 LOGPROBS_ENABLED 设置，默认为 True
        self.logprobs_enabled = os.getenv('LOGPROBS_ENABLED', 'true').lower() in ('true', '1', 'yes')
        
        if self.logprobs_enabled:
            logger.info(f"DecisionVerificationMiddleware 初始化: threshold={self.config['threshold']}, logprobs验证已启用")
        else:
            logger.info(f"DecisionVerificationMiddleware 初始化: logprobs验证已禁用（环境变量 LOGPROBS_ENABLED=false），所有工具调用将直接放行")
    
    def _extract_logprobs_from_response(
        self, 
        request: ToolCallRequest
    ) -> Optional[Dict[str, Any]]:
        """从工具调用的原始响应中提取 logprobs
        
        Args:
            request: 工具调用请求对象
            
        Returns:
            logprobs 字典，如果不可用则返回 None
        """
        try:
            # 从 runtime 的消息历史中找到最近的 AIMessage
            # 注意：工具调用发生在 AIMessage 之后，我们需要回溯找到触发本次工具调用的 AIMessage
            state = request.state
            if not state or 'messages' not in state:
                return None
            
            messages = state['messages']
            
            # 倒序查找最近的 AIMessage
            for i, msg in enumerate(reversed(messages)):
                if isinstance(msg, AIMessage):
                    # 检查是否有 response_metadata 和 logprobs
                    metadata = getattr(msg, 'response_metadata', {})
                    if metadata and 'logprobs' in metadata:
                        logprobs = metadata['logprobs']
                        if logprobs and 'content' in logprobs:
                            logger.info(f"成功提取 logprobs: {len(logprobs.get('content', []))} 个 token")
                        else:
                            logger.warning(f"logprobs 格式异常: {type(logprobs)}")
                        return logprobs
                    break
            
            return None
        except Exception as e:
            logger.warning(f"提取 logprobs 失败: {e}", exc_info=True)
            return None
    
    def _parse_checkpoint_confidences(
        self,
        tool_input: Dict[str, Any],
        logprobs_data: Optional[Dict[str, Any]],
        tool_name: str = 'open_position'
    ) -> Dict[str, Dict[str, float]]:
        """解析每个检查点的置信度
        
        Args:
            tool_input: 工具输入参数（包含检查点的 true/false 值）
            logprobs_data: 从响应中提取的 logprobs 数据
            tool_name: 工具名称，用于确定检查点列表
            
        Returns:
            检查点置信度字典，格式: {checkpoint_name: {'value': bool, 'p_true': float, 'p_false': float}}
            
        Raises:
            RuntimeError: 如果 logprobs 数据不可用
        """
        if not logprobs_data:
            raise RuntimeError(
                "无法获取模型 logprobs 数据，决策验证失败。"
                "请确保模型配置中启用了 logprobs=True"
            )
        
        checkpoints = {}
        
        # 根据工具类型选择检查点列表
        if tool_name == 'open_position':
            checkpoint_names = [
                'multi_timeframe_aligned',
                'tp_sl_ratio_valid',
                'volume_confirmed',
                'trend_strength_sufficient',
            ]
        elif tool_name == 'close_position':
            checkpoint_names = [
                'trend_reversed',
                'structure_broken',
                'volume_confirmed',
                'timing_reasonable',
            ]
        else:
            checkpoint_names = []
        
        for name in checkpoint_names:
            if name not in tool_input:
                continue
            
            value = tool_input[name]
            
            # 从 logprobs 中提取置信度
            p_true, p_false = self._extract_boolean_probs(logprobs_data, name, value)
            checkpoints[name] = {
                'value': value,
                'p_true': p_true,
                'p_false': p_false,
                'source': 'logprobs'
            }
            logger.info(f"检查点 {name}: value={value}, p_true={p_true:.3f}")
        
        logger.info(f"成功解析 {len(checkpoints)} 个检查点")
        return checkpoints
    
    def _extract_boolean_probs(
        self,
        logprobs_data: Dict[str, Any],
        param_name: str,
        value: bool
    ) -> tuple[float, float]:
        """从 logprobs 数据中提取布尔值的概率
        
        从模型的 logprobs 输出中解析 'true' 或 'false' token 的概率。
        
        Args:
            logprobs_data: logprobs 原始数据
            param_name: 参数名称（用于日志）
            value: 参数的实际值
            
        Returns:
            (p_true, p_false) 概率元组
            
        Raises:
            RuntimeError: 如果无法从 logprobs 中提取布尔概率
        """
        import math
        
        content_logprobs = logprobs_data.get('content', [])
        if not content_logprobs:
            raise RuntimeError(f"logprobs 数据中没有 content 字段或为空")
        
        # 在 logprobs 序列中查找 'true'/'false' token
        for token_info in content_logprobs:
            token = str(token_info.get('token', '')).lower().strip()
            
            if token in ('true', 'false'):
                logprob = token_info.get('logprob')
                if logprob is None:
                    continue
                
                # logprob 转换为概率: p = exp(logprob)
                prob = math.exp(logprob)
                
                if token == 'true':
                    return (prob, 1.0 - prob)
                else:  # token == 'false'
                    return (1.0 - prob, prob)
        
        # 如果没有找到 true/false token，说明模型输出格式异常
        raise RuntimeError(
            f"无法在 logprobs 中找到 'true' 或 'false' token 用于参数 {param_name}。"
            f"检查到的 token: {[t.get('token') for t in content_logprobs[:10]]}"
        )
    
    def _extract_numeric_confidence(
        self,
        logprobs_data: Dict[str, Any],
        numeric_value: int
    ) -> float:
        """从 logprobs 数据中提取数值的置信度
        
        对于数值参数（如 profitability_confidence_score），计算模型输出该数值的置信度。
        策略：找到数值对应的 token 序列，取其 logprobs 的平均 exp 值。
        
        Args:
            logprobs_data: logprobs 原始数据
            numeric_value: 参数的实际数值
            
        Returns:
            数值的置信度 (0-1)，无法提取时返回 0.5（中性）
        """
        import math
        
        content_logprobs = logprobs_data.get('content', [])
        if not content_logprobs:
            logger.warning("logprobs 数据为空，数值置信度返回中性值 0.5")
            return 0.5
        
        # 将数值转为字符串，可能是单个 token 或多个 token（如 "85" 可能是 "8"+"5" 或单个 "85"）
        target_str = str(numeric_value)
        
        # 查找包含目标数值的 token（可能完全匹配或部分匹配）
        matched_probs = []
        for i, token_info in enumerate(content_logprobs):
            token = str(token_info.get('token', '')).strip()
            
            # 如果 token 是数字且与目标匹配（完全匹配或为目标的一部分）
            if token.isdigit() and (token == target_str or token in target_str or target_str.startswith(token)):
                logprob = token_info.get('logprob')
                if logprob is not None:
                    prob = math.exp(logprob)
                    matched_probs.append(prob)
        
        if not matched_probs:
            logger.warning(f"未找到数值 {numeric_value} 对应的 token，置信度返回中性值 0.5")
            return 0.5
        
        # 取平均概率作为置信度
        confidence = sum(matched_probs) / len(matched_probs)
        return confidence
    
    def _calculate_weighted_score(
        self,
        checkpoints: Dict[str, Dict[str, float]],
        tool_name: str
    ) -> float:
        """计算加权平均置信度分数
        
        Args:
            checkpoints: 检查点置信度字典
            tool_name: 工具名称，用于选择对应的权重配置
            
        Returns:
            加权平均分数 (0-1)
            
        Raises:
            KeyError: 如果工具名称在权重配置中不存在
        """
        # 获取该工具对应的权重配置（新格式：每个工具独立配置）
        weights_config = self.config['weights']
        if tool_name not in weights_config:
            raise KeyError(
                f"工具 {tool_name} 在决策验证配置中没有对应的权重配置。"
                f"请在 config.yaml 的 decision_verification.weights 中添加 {tool_name} 的配置。"
                f"当前已配置的工具: {list(weights_config.keys())}"
            )
        weights = weights_config[tool_name]
        
        total_weight = 0.0
        weighted_sum = 0.0
        
        for name, data in checkpoints.items():
            if name not in weights:
                continue
            weight = weights[name]
            # 使用 p_true 作为该检查点的分数（认为 true 是我们期望的）
            score = data['p_true']
            contribution = weight * score
            weighted_sum += contribution
            total_weight += weight
        
        if total_weight == 0:
            logger.warning("总权重为 0，返回分数 0")
            return 0.0
        
        final_score = weighted_sum / total_weight
        logger.info(f"加权置信度: {final_score:.3f} (阈值: {self.config['threshold']:.2f})")
        
        return final_score
    
    def _should_pass(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        logprobs_data: Optional[Dict[str, Any]]
    ) -> tuple[bool, Dict[str, Any]]:
        """判断工具调用是否应该放行
        
        Args:
            tool_name: 工具名称
            tool_input: 工具输入参数
            logprobs_data: logprobs 数据
            
        Returns:
            (should_pass, verification_result) 元组
            
        Raises:
            RuntimeError: 如果验证过程中发生错误
        """
        # 检查工具是否需要验证
        if tool_name not in self.config['target_tools']:
            return (True, {'verified': False, 'reason': 'tool not in target list'})
        
        # 特殊处理：open_position(side="NULL") 不需要验证
        # 这是用于标记开仓阶段完成的信号，不是真正的开仓操作
        if tool_name == 'open_position' and tool_input.get('side') == 'NULL':
            logger.info("open_position(side=NULL) 跳过决策验证（仅标记阶段完成）")
            return (True, {'verified': False, 'reason': 'side=NULL, skip verification'})
        
        # 解析检查点置信度（会在无法获取 logprobs 时抛出异常）
        checkpoints = self._parse_checkpoint_confidences(tool_input, logprobs_data, tool_name)
        
        if not checkpoints:
            raise RuntimeError(f"工具 {tool_name} 未找到任何检查点参数，无法进行决策验证")
        
        # 计算加权分数
        weighted_score = self._calculate_weighted_score(checkpoints, tool_name)
        threshold = self.config['threshold']
        
        passed = weighted_score >= threshold
        
        verification_result = {
            'verified': True,
            'checkpoints': checkpoints,
            'weighted_score': weighted_score,
            'threshold': threshold,
            'passed': passed,
        }
        
        # 打印验证结果摘要
        result_text = "通过" if passed else "拒绝"
        logger.info(f"决策验证 [{tool_name}]: {result_text} (分数={weighted_score:.3f}, 阈值={threshold:.3f})")
        
        return (passed, verification_result)
    
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        """拦截工具调用，进行决策验证
        
        Args:
            request: 工具调用请求
            handler: 实际执行工具的 handler
            
        Returns:
            ToolMessage 或 Command
        """
        # 如果中间件未启用或 logprobs 验证被禁用，直接放行
        if not self.config['enabled'] or not self.logprobs_enabled:
            return handler(request)
        
        tool_name = request.tool.name if request.tool else request.tool_call.get('name', 'unknown')
        tool_input = request.tool_call.get('args', {})
        
        # 提取 logprobs
        logprobs_data = self._extract_logprobs_from_response(request)
        
        # 判断是否应该放行
        try:
            should_pass, verification_result = self._should_pass(tool_name, tool_input, logprobs_data)
        except (RuntimeError, KeyError) as e:
            logger.error(f"决策验证失败: {e}")
            return ToolMessage(
                content=json.dumps({'error': 'VERIFICATION_FAILED', 'message': f"决策验证失败: {e}"}, ensure_ascii=False),
                tool_call_id=request.tool_call.get('id', ''),
            )
        
        # 将验证结果附加到 state，供 tracing middleware 记录
        state = request.state
        if state:
            # 将验证结果临时存储到 state 中（用特殊键）
            # tracing middleware 会读取并附加到 tool_call 记录中
            state['_last_verification_result'] = verification_result
        
        if not should_pass:
            # 拒绝执行，返回错误消息
            error_msg = (
                f"决策验证未通过：置信度分数 {verification_result['weighted_score']:.3f} "
                f"低于阈值 {verification_result['threshold']:.3f}。\n"
                f"请重新评估当前的市场情况，寻找其他币种的交易机会。"
            )
            logger.warning(f"拒绝工具调用: {tool_name}, {error_msg}")
            
            # 返回错误 ToolMessage
            return ToolMessage(
                content=json.dumps({'error': 'VERIFICATION_FAILED', 'message': error_msg}, ensure_ascii=False),
                tool_call_id=request.tool_call.get('id', ''),
            )
        
        # 放行，执行实际工具
        return handler(request)
    
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        """异步版本：拦截工具调用，进行决策验证"""
        # 验证逻辑是同步的，直接调用同步版本
        # 注意：这里需要将 async handler 包装为同步调用
        # 如果中间件未启用或 logprobs 验证被禁用，直接放行
        if not self.config['enabled'] or not self.logprobs_enabled:
            return await handler(request)
        
        tool_name = request.tool.name if request.tool else request.tool_call.get('name', 'unknown')
        tool_input = request.tool_call.get('args', {})
        
        logprobs_data = self._extract_logprobs_from_response(request)
        try:
            should_pass, verification_result = self._should_pass(tool_name, tool_input, logprobs_data)
        except (RuntimeError, KeyError) as e:
            logger.error(f"决策验证失败: {e}")
            return ToolMessage(
                content=json.dumps({'error': 'VERIFICATION_FAILED', 'message': f"决策验证失败: {e}"}, ensure_ascii=False),
                tool_call_id=request.tool_call.get('id', ''),
            )
        
        state = request.state
        if state:
            state['_last_verification_result'] = verification_result
        
        if not should_pass:
            error_msg = (
                f"决策验证未通过：置信度分数 {verification_result['weighted_score']:.3f} "
                f"低于阈值 {verification_result['threshold']:.3f}。\n"
                f"请重新评估当前的市场情况，寻找其他币种的交易机会。"
            )
            logger.warning(f"拒绝工具调用: {tool_name}, {error_msg}")
            
            return ToolMessage(
                content=json.dumps({'error': 'VERIFICATION_FAILED', 'message': error_msg}, ensure_ascii=False),
                tool_call_id=request.tool_call.get('id', ''),
            )
        
        return await handler(request)

