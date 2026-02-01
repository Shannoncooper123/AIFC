"""工具辅助函数库
 
提供 Agent 工具的通用辅助函数，包括：
- 错误响应格式化
- 参数验证
- 引擎获取
"""
from typing import Any, Dict, List, Optional, Tuple

from modules.constants import VALID_INTERVALS
from modules.monitor.utils.logger import get_logger

logger = get_logger('agent.tools.utils')


def make_input_error(msg: str, feedback: str = "") -> Dict[str, Any]:
    """生成输入参数错误响应（Dict格式）
    
    Args:
        msg: 错误信息
        feedback: 当前分析进度（原路返回）
    
    Returns:
        包含error和feedback字段的字典
    """
    return {
        "error": f"TOOL_INPUT_ERROR: {msg}. 请修正参数后重试。",
        "feedback": feedback if isinstance(feedback, str) else ""
    }


def make_input_error_list(msg: str, feedback: str = "") -> List[Dict[str, Any]]:
    """生成输入参数错误响应（List格式，用于返回列表的工具）
    
    Args:
        msg: 错误信息
        feedback: 当前分析进度（原路返回）
    
    Returns:
        包含单个错误字典的列表
    """
    return [make_input_error(msg, feedback)]


def make_runtime_error(msg: str, feedback: str = "") -> Dict[str, Any]:
    """生成运行时错误响应（Dict格式）
    
    Args:
        msg: 错误信息
        feedback: 当前分析进度（原路返回）
    
    Returns:
        包含error和feedback字段的字典
    """
    return {
        "error": f"TOOL_RUNTIME_ERROR: {msg}",
        "feedback": feedback if isinstance(feedback, str) else ""
    }


def make_runtime_error_list(msg: str, feedback: str = "") -> List[Dict[str, Any]]:
    """生成运行时错误响应（List格式，用于返回列表的工具）
    
    Args:
        msg: 错误信息
        feedback: 当前分析进度（原路返回）
    
    Returns:
        包含单个错误字典的列表
    """
    return [make_runtime_error(msg, feedback)]


def validate_symbol(symbol: Any) -> Optional[str]:
    """验证交易对参数
    
    Args:
        symbol: 交易对参数
    
    Returns:
        错误信息字符串，验证通过返回None
    """
    if not isinstance(symbol, str) or not symbol:
        return "参数 symbol 必须为非空字符串，如 'BTCUSDT'"
    return None


def validate_interval(interval: Any) -> Optional[str]:
    """验证K线周期参数
    
    Args:
        interval: K线周期参数
    
    Returns:
        错误信息字符串，验证通过返回None
    """
    if not isinstance(interval, str) or not interval:
        return "参数 interval 必须为非空字符串，如 '15m' 或 '1h'"
    if interval not in VALID_INTERVALS:
        return f"无效的 interval: {interval}，支持: {', '.join(VALID_INTERVALS)}"
    return None


def validate_feedback(feedback: Any) -> Optional[str]:
    """验证feedback参数
    
    Args:
        feedback: feedback参数
    
    Returns:
        错误信息字符串，验证通过返回None
    """
    if not isinstance(feedback, str) or not feedback:
        return "参数 feedback 必须为非空字符串，详细分析当前的阶段，并且给出下一步的计划"
    return None


def validate_common_params(
    symbol: Any = None,
    interval: Any = None,
    feedback: Any = None
) -> Optional[str]:
    """批量验证常用参数
    
    Args:
        symbol: 交易对参数（可选）
        interval: K线周期参数（可选）
        feedback: feedback参数（可选）
    
    Returns:
        第一个验证失败的错误信息，全部通过返回None
    """
    if symbol is not None:
        error = validate_symbol(symbol)
        if error:
            return error
    
    if interval is not None:
        error = validate_interval(interval)
        if error:
            return error
    
    if feedback is not None:
        error = validate_feedback(feedback)
        if error:
            return error
    
    return None


def require_engine() -> Tuple[Any, Optional[str]]:
    """获取交易引擎实例
    
    Returns:
        (engine实例, 错误信息)，成功时错误信息为None，失败时engine为None
    """
    from modules.agent.engine import get_engine
    eng = get_engine()
    if eng is None:
        return None, "交易引擎未初始化"
    return eng, None
