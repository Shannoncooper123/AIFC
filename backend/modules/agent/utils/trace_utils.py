"""
Trace 工具模块 - 提供完整的 trace 功能

主要功能：
1. Trace Context - 线程/协程安全的 trace 上下文管理
   - workflow_trace_context: 上下文管理器，设置 workflow run_id 作用域
   - get_current_workflow_run_id: 获取当前 workflow run_id

2. Trace Node - 节点装饰器
   - traced_node: 装饰器，自动为节点函数添加 trace 功能

3. Trace Agent - Agent 封装
   - create_trace_agent: 封装 create_agent，自动注入 trace middleware
   - TracedAgentWrapper: Agent 包装器，自动在 invoke/ainvoke 时创建 agent 级别的 trace

使用方式：
    # 1. 在 workflow 入口处设置上下文
    from modules.agent.utils.trace_utils import workflow_trace_context
    
    with workflow_trace_context(workflow_run_id):
        result = workflow.invoke(...)
    
    # 2. 在引擎层获取 run_id
    from modules.agent.utils.trace_utils import get_current_workflow_run_id
    
    run_id = get_current_workflow_run_id()  # 自动获取当前上下文中的 run_id
    
    # 3. 使用节点装饰器
    from modules.agent.utils.trace_utils import traced_node
    
    @traced_node("context_injection")
    def context_injection_node(state: AgentState, *, config: RunnableConfig) -> Dict[str, Any]:
        ...
    
    # 4. 创建带 trace 的 agent
    from modules.agent.utils.trace_utils import create_trace_agent
    
    subagent = create_trace_agent(
        model=model,
        tools=tools,
        system_prompt=prompt,
        node_name="my_node",
    )
    
    result = subagent.invoke({"messages": [...]}, config=config)
"""
import contextvars
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple

from langchain.agents import create_agent
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from modules.agent.utils.workflow_trace_storage import (
    now_iso,
    calculate_duration_ms,
    generate_trace_id,
    record_trace,
    record_trace_start,
)


# =============================================================================
# Trace Context - 线程/协程安全的 trace 上下文管理
# =============================================================================

_workflow_run_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'workflow_run_id', default=None
)


def get_current_workflow_run_id() -> Optional[str]:
    """
    获取当前 workflow run_id（线程/协程安全）
    
    Returns:
        当前上下文中的 workflow_run_id，如果未设置则返回 None
    """
    return _workflow_run_id.get()


def set_current_workflow_run_id(run_id: Optional[str]) -> contextvars.Token:
    """
    设置当前 workflow run_id
    
    Args:
        run_id: workflow run_id
        
    Returns:
        Token 用于后续恢复上下文
    """
    return _workflow_run_id.set(run_id)


@contextmanager
def workflow_trace_context(run_id: str) -> Generator[None, None, None]:
    """
    上下文管理器：设置 workflow run_id 作用域
    
    在上下文内部，引擎层可以通过 get_current_workflow_run_id() 获取 run_id。
    退出上下文后自动恢复之前的值。
    
    Args:
        run_id: workflow run_id
        
    Yields:
        None
        
    Example:
        with workflow_trace_context(workflow_run_id):
            # 在这个作用域内，引擎层可以获取到 run_id
            result = workflow.invoke(...)
    """
    token = set_current_workflow_run_id(run_id)
    try:
        yield
    finally:
        _workflow_run_id.reset(token)


# =============================================================================
# Trace 内部工具函数
# =============================================================================

def _get_trace_context(config: RunnableConfig) -> Tuple[Optional[str], Optional[str]]:
    """从 RunnableConfig 中提取 trace context"""
    if not config:
        return None, None
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    return configurable.get("workflow_run_id"), configurable.get("current_trace_id")


def _inject_trace_to_config(config: RunnableConfig, workflow_run_id: str, current_trace_id: str) -> RunnableConfig:
    """将 trace context 注入到 config"""
    if not config:
        config = {}
    configurable = dict(config.get("configurable", {}))
    configurable["workflow_run_id"] = workflow_run_id
    configurable["current_trace_id"] = current_trace_id
    new_config = dict(config)
    new_config["configurable"] = configurable
    return RunnableConfig(**new_config)


# =============================================================================
# Trace Node - 节点装饰器
# =============================================================================

def traced_node(node_name: str):
    """
    装饰器：自动为节点函数添加 trace 记录
    
    功能：
    1. 从 RunnableConfig 获取 trace context (workflow_run_id, parent_trace_id)
    2. 生成节点级 trace_id
    3. 将新 trace_id 注入到传递给节点函数的 config 中
    4. 节点执行完成后自动记录 trace（成功或失败）
    
    用法：
        @traced_node("context_injection")
        def context_injection_node(state: AgentState, *, config: RunnableConfig) -> Dict[str, Any]:
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(state: Any, *, config: RunnableConfig = None) -> Dict[str, Any]:
            workflow_run_id, parent_trace_id = _get_trace_context(config)
            
            symbol = None
            if hasattr(state, "current_symbol"):
                symbol = state.current_symbol
            elif isinstance(state, dict):
                symbol = state.get("current_symbol")
            
            current_trace_id = generate_trace_id("node")
            start_time = now_iso()
            
            new_config = config
            if workflow_run_id:
                new_config = _inject_trace_to_config(config, workflow_run_id, current_trace_id)
                record_trace_start(
                    workflow_run_id=workflow_run_id,
                    trace_id=current_trace_id,
                    parent_trace_id=parent_trace_id,
                    trace_type="node",
                    name=node_name,
                    start_time=start_time,
                    symbol=symbol,
                )
            
            status = "success"
            error_msg = None
            output_summary = None
            
            try:
                result = func(state, config=new_config)
                
                if isinstance(result, dict):
                    output_summary = {
                        k: bool(v) if isinstance(v, (dict, list)) else v 
                        for k, v in result.items() 
                        if k != "messages"
                    }
                
                return result
            except Exception as e:
                status = "error"
                error_msg = str(e)
                raise
            finally:
                if workflow_run_id:
                    end_time = now_iso()
                    record_trace(
                        workflow_run_id=workflow_run_id,
                        trace_id=current_trace_id,
                        parent_trace_id=parent_trace_id,
                        trace_type="node",
                        name=node_name,
                        status=status,
                        start_time=start_time,
                        end_time=end_time,
                        duration_ms=calculate_duration_ms(start_time, end_time),
                        symbol=symbol,
                        payload={"output_summary": output_summary} if output_summary else None,
                        error=error_msg,
                    )
        
        return wrapper
    return decorator


# =============================================================================
# Trace Agent - Agent 封装
# =============================================================================

class TracedAgentWrapper:
    """Agent 包装器，自动在 invoke/ainvoke 时创建 agent 级别的 trace"""
    
    def __init__(self, agent: Any, node_name: str):
        self._agent = agent
        self._node_name = node_name
    
    def _extract_symbol(self, input_data: Dict[str, Any]) -> Optional[str]:
        """从输入数据中提取 symbol"""
        if isinstance(input_data, dict):
            messages = input_data.get("messages", [])
            if messages and hasattr(messages[0], "additional_kwargs"):
                return messages[0].additional_kwargs.get("symbol")
        return None
    
    def _start_trace(self, config: RunnableConfig, symbol: Optional[str]) -> tuple:
        """开始 trace 记录，返回 (workflow_run_id, agent_trace_id, parent_trace_id, start_time, child_config)"""
        workflow_run_id, parent_trace_id = _get_trace_context(config)
        
        if not workflow_run_id:
            return None, None, None, None, config
        
        agent_trace_id = generate_trace_id("agent")
        start_time = now_iso()
        child_config = _inject_trace_to_config(config, workflow_run_id, agent_trace_id)
        
        record_trace_start(
            workflow_run_id=workflow_run_id,
            trace_id=agent_trace_id,
            parent_trace_id=parent_trace_id,
            trace_type="agent",
            name=self._node_name,
            start_time=start_time,
            symbol=symbol,
        )
        
        return workflow_run_id, agent_trace_id, parent_trace_id, start_time, child_config
    
    def _end_trace(
        self,
        workflow_run_id: str,
        agent_trace_id: str,
        parent_trace_id: Optional[str],
        start_time: str,
        symbol: Optional[str],
        status: str,
        error_msg: Optional[str],
    ) -> None:
        """结束 trace 记录"""
        if not workflow_run_id:
            return
        
        end_time = now_iso()
        record_trace(
            workflow_run_id=workflow_run_id,
            trace_id=agent_trace_id,
            parent_trace_id=parent_trace_id,
            trace_type="agent",
            name=self._node_name,
            status=status,
            start_time=start_time,
            end_time=end_time,
            duration_ms=calculate_duration_ms(start_time, end_time),
            symbol=symbol,
            error=error_msg,
        )
    
    def invoke(self, input_data: Dict[str, Any], config: RunnableConfig = None, **kwargs) -> Dict[str, Any]:
        """同步调用 agent"""
        symbol = self._extract_symbol(input_data)
        workflow_run_id, agent_trace_id, parent_trace_id, start_time, child_config = self._start_trace(config, symbol)
        
        if not workflow_run_id:
            return self._agent.invoke(input_data, config=config, **kwargs)
        
        status = "success"
        error_msg = None
        
        try:
            return self._agent.invoke(input_data, config=child_config, **kwargs)
        except Exception as e:
            status = "error"
            error_msg = str(e)
            raise
        finally:
            self._end_trace(workflow_run_id, agent_trace_id, parent_trace_id, start_time, symbol, status, error_msg)
    
    async def ainvoke(self, input_data: Dict[str, Any], config: RunnableConfig = None, **kwargs) -> Dict[str, Any]:
        """异步调用 agent（contextvars 会自动传播到 async task）"""
        symbol = self._extract_symbol(input_data)
        workflow_run_id, agent_trace_id, parent_trace_id, start_time, child_config = self._start_trace(config, symbol)
        
        if not workflow_run_id:
            return await self._agent.ainvoke(input_data, config=config, **kwargs)
        
        status = "success"
        error_msg = None
        
        try:
            return await self._agent.ainvoke(input_data, config=child_config, **kwargs)
        except Exception as e:
            status = "error"
            error_msg = str(e)
            raise
        finally:
            self._end_trace(workflow_run_id, agent_trace_id, parent_trace_id, start_time, symbol, status, error_msg)
    
    def __getattr__(self, name: str) -> Any:
        return getattr(self._agent, name)


def create_trace_agent(
    model: ChatOpenAI,
    tools: List[Any],
    *,
    system_prompt: Optional[str] = None,
    node_name: str = "unknown",
    debug: bool = False,
    **kwargs
) -> TracedAgentWrapper:
    """
    封装 create_agent，自动注入 WorkflowTraceMiddleware
    
    返回的 agent 在 invoke 时会自动：
    1. 创建 agent 级别的 trace
    2. 记录 model_call trace
    3. 记录 tool_call trace
    4. 从工具返回的多模态内容中提取并保存图片 artifact
    """
    from modules.agent.middleware.workflow_trace_middleware import WorkflowTraceMiddleware
    
    trace_mw = WorkflowTraceMiddleware(node_name)
    
    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        middleware=[trace_mw],
        debug=debug,
        **kwargs
    )
    
    return TracedAgentWrapper(agent, node_name)
