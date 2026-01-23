"""Tool 调用追踪中间件"""
from __future__ import annotations
from typing import TYPE_CHECKING, Any, Callable
from datetime import datetime, timezone

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from agent.middleware.session_management_middleware import SessionManagementState
from agent.utils.decision_trace_storage import (
    format_tool_call_record,
    extract_position_id_from_tool_output,
)
from monitor_module.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Awaitable
    from langchain.tools.tool_node import ToolCallRequest

logger = get_logger('agent.tool_call_tracing_middleware')


class ToolCallTracingMiddleware(AgentMiddleware[SessionManagementState, Any]):
    """Tool 调用追踪中间件
    
    职责：
    - 拦截每个 tool 调用，记录输入和输出
    - 自动提取涉及持仓操作的 position_id
    - 将记录追加到 state 的 _session_tool_calls 列表中
    
    不负责：
    - Session 的创建和保存（由 SessionManagementMiddleware 负责）
    
    使用方法：
        tracing_middleware = ToolCallTracingMiddleware()
        agent = create_agent(
            model, 
            tools, 
            middleware=[session_middleware, tracing_middleware, ...]
        )
    
    注意：
        必须与 SessionManagementMiddleware 一起使用，且 SessionManagementMiddleware
        应该在中间件列表中排在前面，以确保 state 中已经初始化了 _session_tool_calls 等字段。
    """
    
    state_schema = SessionManagementState
    
    def __init__(self):
        """初始化 Tool 调用追踪中间件"""
        super().__init__()
        self.tools = []  # 不注册额外工具
    
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        """拦截 tool 调用，记录输入和输出
        
        Args:
            request: Tool 调用请求（包含 tool_call dict, tool, state, runtime）
            handler: 实际执行 tool 的 handler
            
        Returns:
            ToolMessage 或 Command
        """
        # 获取 tool 信息
        tool_name = request.tool.name if request.tool else request.tool_call.get('name', 'unknown')
        tool_input = request.tool_call.get('args', {})
        
        # 记录调用前时间
        call_time = datetime.now(timezone.utc).isoformat()
        
        # 执行实际 tool 调用
        success = True
        result = None
        try:
            result = handler(request)
            
            # 提取 tool 输出（从 ToolMessage 中提取 content）
            if isinstance(result, ToolMessage):
                tool_output = result.content
            else:
                tool_output = str(result)
                
        except Exception as e:
            success = False
            tool_output = {'error': str(e)}
            logger.error(f"Tool {tool_name} 调用失败: {e}")
            raise  # 重新抛出异常，让上层处理
        
        # 记录到 state（如果 state 可用）
        state = request.state
        if state and '_session_tool_calls' in state:
            # 递增序号
            seq = state.get('_session_tool_seq', 0) + 1
            state['_session_tool_seq'] = seq
            
            # 尝试提取 position_id（仅对持仓相关操作）
            position_id = extract_position_id_from_tool_output(tool_name, tool_output)
            
            # 格式化并追加记录
            tool_record = format_tool_call_record(
                seq=seq,
                tool_name=tool_name,
                tool_input=tool_input,
                tool_output=tool_output,
                timestamp=call_time,
                success=success,
                position_id=position_id,
            )
            
            # 附加决策验证结果（如果有）
            verification_result = state.get('_last_verification_result')
            if verification_result:
                tool_record['verification'] = verification_result
                # 清理临时数据
                state.pop('_last_verification_result', None)
            
            state['_session_tool_calls'].append(tool_record)
            
            logger.debug(f"Tool call 已记录: seq={seq}, tool={tool_name}, success={success}")
        
        return result
    
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        """异步版本：拦截 tool 调用，记录输入和输出
        
        Args:
            request: Tool 调用请求
            handler: 异步执行 tool 的 handler
            
        Returns:
            ToolMessage 或 Command
        """
        # 获取 tool 信息
        tool_name = request.tool.name if request.tool else request.tool_call.get('name', 'unknown')
        tool_input = request.tool_call.get('args', {})
        
        # 记录调用前时间
        call_time = datetime.now(timezone.utc).isoformat()
        
        # 执行实际 tool 调用
        success = True
        result = None
        try:
            result = await handler(request)
            
            # 提取 tool 输出
            if isinstance(result, ToolMessage):
                tool_output = result.content
            else:
                tool_output = str(result)
                
        except Exception as e:
            success = False
            tool_output = {'error': str(e)}
            logger.error(f"Tool {tool_name} 调用失败: {e}")
            raise
        
        # 记录到 state
        state = request.state
        if state and '_session_tool_calls' in state:
            seq = state.get('_session_tool_seq', 0) + 1
            state['_session_tool_seq'] = seq
            
            position_id = extract_position_id_from_tool_output(tool_name, tool_output)
            
            tool_record = format_tool_call_record(
                seq=seq,
                tool_name=tool_name,
                tool_input=tool_input,
                tool_output=tool_output,
                timestamp=call_time,
                success=success,
                position_id=position_id,
            )
            
            # 附加决策验证结果（如果有）
            verification_result = state.get('_last_verification_result')
            if verification_result:
                tool_record['verification'] = verification_result
                # 清理临时数据
                state.pop('_last_verification_result', None)
            
            state['_session_tool_calls'].append(tool_record)
            logger.debug(f"Tool call 已记录 (async): seq={seq}, tool={tool_name}, success={success}")
        
        return result

