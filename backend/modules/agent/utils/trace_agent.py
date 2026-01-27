"""
Trace Agent 封装 - 自动注入 trace middleware 的 create_agent 封装

使用方式：
    from modules.agent.utils.trace_agent import create_trace_agent
    
    subagent = create_trace_agent(
        model=model,
        tools=tools,
        system_prompt=prompt,
        node_name="my_node",
    )
    
    result = subagent.invoke({"messages": [...]}, config=config)
"""
from typing import Any, Dict, List, Optional

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


def _get_trace_context(config: RunnableConfig) -> tuple:
    """从 config 获取 trace context"""
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
