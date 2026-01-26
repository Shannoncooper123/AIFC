"""
Trace 工具函数 - 提供节点装饰器

主要功能：
- traced_node: 装饰器，自动为节点函数添加 trace 功能
"""
from functools import wraps
from typing import Any, Callable, Dict, Optional, Tuple

from langchain_core.runnables import RunnableConfig

from modules.agent.utils.workflow_trace_storage import (
    now_iso,
    calculate_duration_ms,
    generate_trace_id,
    record_trace,
    record_trace_start,
)


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
