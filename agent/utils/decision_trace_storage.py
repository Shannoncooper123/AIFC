"""决策链路追踪数据存储工具"""
import json
import os
from typing import Dict, Any, List
from datetime import datetime, timezone
from monitor_module.utils.logger import get_logger

logger = get_logger('agent.decision_trace_storage')


def append_session_trace(session_data: Dict[str, Any], trace_file_path: str) -> bool:
    """追加一个 session 记录到 agent_decision_trace.json
    
    Args:
        session_data: session 数据字典，包含 session_id, start_time, end_time, tool_calls 等
        trace_file_path: trace 文件路径
        
    Returns:
        True 表示写入成功，False 表示失败
    """
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(trace_file_path), exist_ok=True)
        
        # 读取现有数据（如果文件存在）
        if os.path.exists(trace_file_path):
            try:
                with open(trace_file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if not isinstance(data, dict) or 'sessions' not in data:
                        data = {'sessions': []}
            except (json.JSONDecodeError, IOError):
                logger.warning(f"无法读取现有 trace 文件，将创建新文件: {trace_file_path}")
                data = {'sessions': []}
        else:
            data = {'sessions': []}
        
        # 追加新的 session 记录
        data['sessions'].append(session_data)
        
        # 写入文件（使用临时文件 + 原子替换，避免损坏）
        temp_path = trace_file_path + '.tmp'
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # 原子替换
        os.replace(temp_path, trace_file_path)
        
        logger.info(f"Session trace 已写入: {session_data.get('session_id')} -> {trace_file_path}")
        return True
        
    except Exception as e:
        logger.error(f"写入 session trace 失败: {e}", exc_info=True)
        return False


def get_current_session_id() -> str:
    """生成当前 session_id
    
    格式: sess_YYYYMMDD_HHMMSS_<random_suffix>
    
    Returns:
        session_id 字符串
    """
    import random
    import string
    
    now = datetime.now(timezone.utc)
    timestamp_part = now.strftime('%Y%m%d_%H%M%S')
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    
    return f"sess_{timestamp_part}_{random_suffix}"


def format_tool_call_record(
    seq: int,
    tool_name: str,
    tool_input: Dict[str, Any],
    tool_output: Any,
    timestamp: str,
    success: bool,
    position_id: str | None = None
) -> Dict[str, Any]:
    """格式化单个 tool 调用记录
    
    Args:
        seq: 调用序号（从 1 开始）
        tool_name: 工具名称
        tool_input: 工具输入参数
        tool_output: 工具返回结果
        timestamp: 调用时间戳（ISO 格式）
        success: 是否成功
        position_id: 相关的持仓 ID（如果有）
        
    Returns:
        格式化的 tool 调用记录字典
    """
    record = {
        'seq': seq,
        'tool_name': tool_name,
        'input': tool_input,
        'output': tool_output,
        'timestamp': timestamp,
        'success': success,
    }
    
    if position_id:
        record['position_id'] = position_id
    
    return record


def extract_position_id_from_tool_output(tool_name: str, tool_output: Any) -> str | None:
    """从 tool 输出中提取 position_id
    
    仅对 open_position/close_position/update_tp_sl 有效
    
    Args:
        tool_name: 工具名称
        tool_output: 工具返回结果（可能是 dict、JSON 字符串或其他）
        
    Returns:
        position_id 字符串，如果无法提取则返回 None
    """
    if tool_name not in ['open_position', 'close_position', 'update_tp_sl']:
        return None
    
    # 尝试解析 tool_output
    data = None
    
    if isinstance(tool_output, dict):
        data = tool_output
    elif isinstance(tool_output, str):
        # 尝试解析 JSON 字符串
        try:
            data = json.loads(tool_output)
        except (json.JSONDecodeError, ValueError):
            # 不是有效的 JSON，返回 None
            return None
    
    # 从 dict 中提取 id
    if isinstance(data, dict) and 'id' in data:
        return data['id']
    
    return None

