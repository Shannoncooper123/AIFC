"""Session 生命周期管理中间件"""
from __future__ import annotations
from typing import TYPE_CHECKING, Any, Dict
from datetime import datetime, timezone
import json
from pathlib import Path

from langchain.agents.middleware.types import AgentMiddleware, AgentState, PrivateStateAttr
from langgraph.channels.untracked_value import UntrackedValue
from typing_extensions import NotRequired, Annotated

from agent.utils.decision_trace_storage import (
    append_session_trace,
    get_current_session_id,
)
from config.settings import get_config
from monitor_module.utils.logger import get_logger

if TYPE_CHECKING:
    from langgraph.runtime import Runtime

logger = get_logger('agent.session_management_middleware')


class SessionManagementState(AgentState):
    """Session 管理中间件的 State Schema
    
    扩展 AgentState，添加 session 追踪字段。
    使用 UntrackedValue 和 PrivateStateAttr 确保这些字段不会被持久化或暴露给外部。
    """
    
    # Session 基本信息
    _session_id: NotRequired[Annotated[str | None, UntrackedValue, PrivateStateAttr]]
    _session_start_time: NotRequired[Annotated[str | None, UntrackedValue, PrivateStateAttr]]
    _session_alert_info: NotRequired[Annotated[Dict[str, Any] | None, UntrackedValue, PrivateStateAttr]]
    
    # Tool 调用记录（由 ToolCallTracingMiddleware 填充）
    _session_tool_calls: NotRequired[Annotated[list[Dict[str, Any]], UntrackedValue, PrivateStateAttr]]
    _session_tool_seq: NotRequired[Annotated[int, UntrackedValue, PrivateStateAttr]]


class SessionManagementMiddleware(AgentMiddleware[SessionManagementState, Any]):
    """Session 生命周期管理中间件
    
    职责：
    - 在 agent 开始前初始化 session（生成 ID、记录开始时间）
    - 在 agent 结束后保存完整的 session 数据到文件
    - 提取涉及的 position_id 和生成摘要
    
    不负责：
    - 工具调用的记录（由 ToolCallTracingMiddleware 负责）
    
    使用方法：
        session_middleware = SessionManagementMiddleware(latest_alert=alert_data)
        agent = create_agent(model, tools, middleware=[session_middleware, ...])
    """
    
    state_schema = SessionManagementState
    
    def __init__(self, latest_alert: Dict[str, Any] | None = None):
        """初始化 Session 管理中间件
        
        Args:
            latest_alert: 最新告警数据（可选），用于记录 session 的触发来源
        """
        super().__init__()
        self.latest_alert = latest_alert
        self.tools = []  # 不注册额外工具
    
    def before_agent(self, state: SessionManagementState, runtime: Runtime) -> dict[str, Any] | None:
        """Agent 开始前：初始化 session 追踪
        
        生成 session_id，记录开始时间和告警信息。
        """
        session_id = get_current_session_id()
        start_time = datetime.now(timezone.utc).isoformat()
        
        # 提取告警信息（如果有）
        alert_info = None
        if self.latest_alert:
            alert_info = {
                'ts': self.latest_alert.get('ts'),
                'interval': self.latest_alert.get('interval'),
                'symbols': [e.get('symbol') for e in self.latest_alert.get('entries', [])],
            }
        
        logger.info(f"Session 开始: {session_id}")
        
        return {
            '_session_id': session_id,
            '_session_start_time': start_time,
            '_session_alert_info': alert_info,
            '_session_tool_calls': [],
            '_session_tool_seq': 0,
        }
    
    def _merge_subagent_traces(self, session_id: str) -> list[Dict[str, Any]]:
        """合并所有SubAgent的trace文件
        
        Args:
            session_id: 主控Agent的session_id
            
        Returns:
            合并后的SubAgent tool_calls列表
        """
        cfg = get_config()
        # 从日志文件路径推导出logs目录
        log_file_path = Path(cfg['agent']['position_history_path'])
        logs_dir = log_file_path.parent
        temp_dir = logs_dir / 'subagent_traces'
        
        if not temp_dir.exists():
            logger.info("SubAgent trace目录不存在,跳过合并")
            return []
        
        # 查找所有相关的SubAgent trace文件
        pattern = f"{session_id}_subagent_*.json"
        subagent_files = list(temp_dir.glob(pattern))
        
        if not subagent_files:
            logger.info("未找到SubAgent trace文件")
            return []
        
        logger.info(f"找到 {len(subagent_files)} 个SubAgent trace文件")
        
        merged_tool_calls = []
        
        for trace_file in sorted(subagent_files):
            try:
                with open(trace_file, 'r', encoding='utf-8') as f:
                    subagent_trace = json.load(f)
                
                subagent_name = subagent_trace.get('subagent_name', 'unknown')
                tool_calls = subagent_trace.get('tool_calls', [])
                
                # 标记这些tool_calls来自SubAgent
                for tc in tool_calls:
                    if 'subagent' not in tc:
                        tc['subagent'] = subagent_name
                
                merged_tool_calls.extend(tool_calls)
                
                logger.info(
                    f"已合并SubAgent[{subagent_name}]: {len(tool_calls)} tool calls, "
                    f"positions: {subagent_trace.get('related_positions', [])}"
                )
                
                # 删除临时文件
                trace_file.unlink()
                
            except Exception as e:
                logger.error(f"合并SubAgent trace失败 [{trace_file.name}]: {e}", exc_info=True)
        
        return merged_tool_calls
    
    def after_agent(self, state: SessionManagementState, runtime: Runtime) -> dict[str, Any] | None:
        """Agent 结束后：保存完整 session 到 trace 文件
        
        汇总所有 tool 调用（包括SubAgent的），写入 agent_decision_trace.json。
        """
        session_id = state.get('_session_id')
        if not session_id:
            logger.warning("Session ID 未找到，跳过 trace 记录")
            return None
        
        start_time = state.get('_session_start_time')
        end_time = datetime.now(timezone.utc).isoformat()
        alert_info = state.get('_session_alert_info')
        tool_calls = state.get('_session_tool_calls', [])
        
        # 合并SubAgent的tool_calls
        subagent_tool_calls = self._merge_subagent_traces(session_id)
        if subagent_tool_calls:
            logger.info(f"从SubAgent合并了 {len(subagent_tool_calls)} 个tool_calls")
            tool_calls = tool_calls + subagent_tool_calls
        
        # 提取SubAgent的结论信息（从主控agent的tool_calls中提取）
        subagent_conclusions = {}
        for tc in tool_calls:
            tool_name = tc.get('tool_name', '')
            if tool_name in ['analyze_and_open_positions', 'manage_and_protect_positions']:
                conclusion_text = tc.get('output', '')
                subagent_conclusions[tool_name] = {
                    'timestamp': tc.get('timestamp'),
                    'success': tc.get('success', False),
                    'conclusion': conclusion_text,  # SubAgent的完整返回文本
                    'seq': tc.get('seq'),
                }
                logger.info(
                    f"提取SubAgent结论 [{tool_name}]: "
                    f"seq={tc.get('seq')}, 长度={len(conclusion_text)}字符, "
                    f"success={tc.get('success', False)}"
                )
        
        # 提取所有涉及的 position_id
        related_positions = list(set(
            tc.get('position_id') 
            for tc in tool_calls 
            if tc.get('position_id')
        ))
        
        # 生成简要摘要（基于 tool 调用）
        summary_parts = []
        for tc in tool_calls:
            if tc.get('tool_name') == 'open_position' and tc.get('success'):
                summary_parts.append(f"开仓 {tc.get('input', {}).get('symbol', 'unknown')}")
            elif tc.get('tool_name') == 'close_position' and tc.get('success'):
                summary_parts.append(f"平仓 {tc.get('input', {}).get('symbol', 'unknown')}")
            elif tc.get('tool_name') == 'update_tp_sl' and tc.get('success'):
                summary_parts.append(f"调整 TP/SL {tc.get('input', {}).get('symbol', 'unknown')}")
        
        summary = '; '.join(summary_parts) if summary_parts else f"{len(tool_calls)} tool calls"
        
        # 构造 session 数据
        session_data = {
            'session_id': session_id,
            'start_time': start_time,
            'end_time': end_time,
            'alert_info': alert_info,
            'tool_calls': tool_calls,
            'subagent_conclusions': subagent_conclusions,  # 新增：SubAgent的结论
            'related_positions': related_positions,
            'summary': summary,
        }
        
        # 写入 trace 文件
        cfg = get_config()
        trace_file = cfg['agent']['decision_trace_path']
        
        success = append_session_trace(session_data, trace_file)
        
        if success:
            subagent_summary = ', '.join([f"{name}(✓)" if data['success'] else f"{name}(✗)" 
                                         for name, data in subagent_conclusions.items()])
            logger.info(
                f"Session 已保存: {session_id}, "
                f"{len(tool_calls)} tool calls (含SubAgent), "
                f"SubAgent结论: [{subagent_summary}], "
                f"positions: {related_positions}"
            )
        else:
            logger.error(f"Session 保存失败: {session_id}")
        
        return None
    
    async def aafter_agent(self, state: SessionManagementState, runtime: Runtime) -> dict[str, Any] | None:
        """异步版本：Agent 结束后保存 session"""
        # 直接调用同步版本（文件 I/O 在这里不是瓶颈）
        return self.after_agent(state, runtime)

