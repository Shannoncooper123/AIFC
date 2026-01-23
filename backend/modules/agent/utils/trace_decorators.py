"""Workflow Trace 装饰器模块 - 支持层级化 span 追踪"""
from functools import wraps
from typing import Callable, Dict, Any, Optional

from modules.agent.utils.workflow_trace_storage import (
    get_current_run_id,
    get_current_span_id,
    set_current_symbol,
    start_span,
    end_span,
    record_node_event,
)


def traced_node(node_name: str):
    """
    装饰器：自动为 node 函数记录 span 开始/结束事件
    
    支持层级化追踪，自动提取 symbol 信息
    
    用法：
        @traced_node("single_symbol_analysis")
        def single_symbol_analysis_node(state: AgentState, *, config: RunnableConfig):
            ...
    
    Args:
        node_name: 节点名称，用于 trace 记录
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(state, *args, **kwargs):
            run_id = get_current_run_id()
            config = kwargs.get("config")
            if not config and args:
                config = args[0]
            if not run_id and config:
                configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
                run_id = configurable.get("run_id")
            
            symbol = None
            if hasattr(state, "current_symbol"):
                symbol = state.current_symbol
            elif isinstance(state, dict):
                symbol = state.get("current_symbol")
            
            if symbol:
                set_current_symbol(symbol)
            
            parent_span_id = get_current_span_id()
            span_id = None
            
            if run_id:
                span_id = start_span(
                    run_id=run_id,
                    node=node_name,
                    parent_span_id=parent_span_id,
                    symbol=symbol,
                )
            
            try:
                result = func(state, *args, **kwargs)
                
                output_summary = {}
                if isinstance(result, dict):
                    output_summary["result_keys"] = list(result.keys())
                    if "analysis_results" in result and isinstance(result["analysis_results"], dict):
                        output_summary["analyzed_symbols"] = list(result["analysis_results"].keys())
                
                if run_id and span_id:
                    end_span(
                        run_id=run_id,
                        span_id=span_id,
                        status="success",
                        output_summary=output_summary,
                    )
                
                return result
                
            except Exception as e:
                if run_id and span_id:
                    end_span(
                        run_id=run_id,
                        span_id=span_id,
                        status="error",
                        error=str(e),
                    )
                raise
        
        return wrapper
    return decorator


def traced_tool(tool_name: str):
    """
    装饰器：为工具函数记录执行 span
    
    用法：
        @traced_tool("get_kline_image")
        def get_kline_image_tool(symbol: str, ...):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            run_id = get_current_run_id()
            parent_span_id = get_current_span_id()
            
            symbol = kwargs.get("symbol")
            if not symbol and args:
                symbol = args[0] if isinstance(args[0], str) else None
            
            span_id = None
            if run_id:
                span_id = start_span(
                    run_id=run_id,
                    node=f"tool:{tool_name}",
                    parent_span_id=parent_span_id,
                    symbol=symbol,
                )
            
            try:
                result = func(*args, **kwargs)
                
                if run_id and span_id:
                    end_span(
                        run_id=run_id,
                        span_id=span_id,
                        status="success",
                    )
                
                return result
                
            except Exception as e:
                if run_id and span_id:
                    end_span(
                        run_id=run_id,
                        span_id=span_id,
                        status="error",
                        error=str(e),
                    )
                raise
        
        return wrapper
    return decorator
