"""SubAgent Session 管理中间件 - 独立trace到临时文件"""
from __future__ import annotations
from typing import TYPE_CHECKING, Any, Dict
from datetime import datetime, timezone
import json
from pathlib import Path

from langchain.agents.middleware.types import AgentMiddleware, AgentState, PrivateStateAttr
from langgraph.channels.untracked_value import UntrackedValue
from typing_extensions import NotRequired, Annotated

from agent.utils.decision_trace_storage import get_current_session_id
from monitor_module.utils.logger import get_logger

if TYPE_CHECKING:
    from langgraph.runtime import Runtime

logger = get_logger('agent.subagent_session_middleware')


class SubAgentSessionState(AgentState):
    """SubAgent Session State Schema"""
    
    # SubAgent专用字段
    _subagent_name: NotRequired[Annotated[str | None, UntrackedValue, PrivateStateAttr]]
    _parent_session_id: NotRequired[Annotated[str | None, UntrackedValue, PrivateStateAttr]]
    _subagent_session_id: NotRequired[Annotated[str | None, UntrackedValue, PrivateStateAttr]]
    _subagent_start_time: NotRequired[Annotated[str | None, UntrackedValue, PrivateStateAttr]]
    
    # Tool调用记录(由ToolCallTracingMiddleware填充)
    _session_tool_calls: NotRequired[Annotated[list[Dict[str, Any]], UntrackedValue, PrivateStateAttr]]
    _session_tool_seq: NotRequired[Annotated[int, UntrackedValue, PrivateStateAttr]]


class SubAgentSessionMiddleware(AgentMiddleware[SubAgentSessionState, Any]):
    """SubAgent专用的Session管理中间件
    
    职责:
    - 在SubAgent开始时初始化独立的session
    - 在SubAgent结束后将trace写入临时文件(而非主trace文件)
    - 文件命名: {parent_session_id}_subagent_{subagent_name}.json
    
    主控Agent的SessionManagementMiddleware会在最后合并这些临时文件
    """
    
    state_schema = SubAgentSessionState
    
    def __init__(self, subagent_name: str, parent_session_id: str, temp_dir: Path):
        """初始化SubAgent Session中间件
        
        Args:
            subagent_name: SubAgent名称(如'open_position', 'position_management')
            parent_session_id: 主控Agent的session_id
            temp_dir: 临时文件目录
        """
        super().__init__()
        self.subagent_name = subagent_name
        self.parent_session_id = parent_session_id
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.tools = []
        
        logger.info(f"SubAgent[{subagent_name}] Session中间件已初始化")
    
    def before_agent(self, state: SubAgentSessionState, runtime: Runtime) -> dict[str, Any] | None:
        """SubAgent开始前: 初始化session追踪"""
        subagent_session_id = f"{self.parent_session_id}_subagent_{self.subagent_name}"
        start_time = datetime.now(timezone.utc).isoformat()
        
        logger.info(f"SubAgent[{self.subagent_name}] Session开始: {subagent_session_id}")
        
        return {
            '_subagent_name': self.subagent_name,
            '_parent_session_id': self.parent_session_id,
            '_subagent_session_id': subagent_session_id,
            '_subagent_start_time': start_time,
            '_session_tool_calls': [],
            '_session_tool_seq': 0,
        }
    
    def after_agent(self, state: SubAgentSessionState, runtime: Runtime) -> dict[str, Any] | None:
        """SubAgent结束后: 将trace写入临时文件"""
        subagent_session_id = state.get('_subagent_session_id')
        if not subagent_session_id:
            logger.warning(f"SubAgent[{self.subagent_name}] Session ID未找到,跳过trace记录")
            return None
        
        start_time = state.get('_subagent_start_time')
        end_time = datetime.now(timezone.utc).isoformat()
        tool_calls = state.get('_session_tool_calls', [])
        
        # 提取position_id
        related_positions = list(set(
            tc.get('position_id') 
            for tc in tool_calls 
            if tc.get('position_id')
        ))
        
        # 生成摘要
        summary_parts = []
        for tc in tool_calls:
            if tc.get('tool_name') == 'open_position' and tc.get('success'):
                summary_parts.append(f"开仓 {tc.get('input', {}).get('symbol', 'unknown')}")
            elif tc.get('tool_name') == 'close_position' and tc.get('success'):
                summary_parts.append(f"平仓 {tc.get('input', {}).get('symbol', 'unknown')}")
            elif tc.get('tool_name') == 'update_tp_sl' and tc.get('success'):
                summary_parts.append(f"调整TP/SL {tc.get('input', {}).get('symbol', 'unknown')}")
        
        summary = '; '.join(summary_parts) if summary_parts else f"{len(tool_calls)} tool calls"
        
        # 构造SubAgent trace数据
        subagent_trace = {
            'subagent_name': self.subagent_name,
            'subagent_session_id': subagent_session_id,
            'parent_session_id': self.parent_session_id,
            'start_time': start_time,
            'end_time': end_time,
            'tool_calls': tool_calls,
            'related_positions': related_positions,
            'summary': summary,
        }
        
        # 写入临时文件
        temp_file = self.temp_dir / f"{subagent_session_id}.json"
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(subagent_trace, f, ensure_ascii=False, indent=2)
            
            logger.info(
                f"SubAgent[{self.subagent_name}] trace已保存: {temp_file.name}, "
                f"{len(tool_calls)} tool calls, positions: {related_positions}"
            )
        except Exception as e:
            logger.error(f"SubAgent[{self.subagent_name}] trace保存失败: {e}", exc_info=True)
        
        return None
    
    async def aafter_agent(self, state: SubAgentSessionState, runtime: Runtime) -> dict[str, Any] | None:
        """异步版本: SubAgent结束后保存trace"""
        return self.after_agent(state, runtime)

