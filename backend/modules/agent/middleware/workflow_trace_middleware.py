from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable

from langchain.agents.middleware.types import (
    AgentMiddleware,
)
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.types import Command

from modules.agent.utils.workflow_trace_storage import (
    append_event,
    get_current_run_id,
    get_current_span_id,
    record_tool_call,
    save_image_artifact,
)
from modules.monitor.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from langchain.tools.tool_node import ToolCallRequest

logger = get_logger("agent.workflow_trace_middleware")


def _serialize_message(msg: Any) -> dict:
    """序列化消息为可存储的格式"""
    if isinstance(msg, HumanMessage):
        return {"role": "human", "content": str(msg.content)[:1000]}
    elif isinstance(msg, AIMessage):
        result = {"role": "ai", "content": str(msg.content)[:1000] if msg.content else ""}
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            result["tool_calls"] = [
                {"name": tc.get("name", "unknown"), "args_keys": list(tc.get("args", {}).keys())}
                for tc in msg.tool_calls
            ]
        return result
    elif isinstance(msg, ToolMessage):
        content = str(msg.content)
        if len(content) > 500:
            content = content[:500] + "..."
        return {"role": "tool", "tool_call_id": getattr(msg, "tool_call_id", ""), "content": content}
    elif isinstance(msg, SystemMessage):
        return {"role": "system", "content": str(msg.content)[:500]}
    else:
        return {"role": "unknown", "content": str(msg)[:500]}


class WorkflowTraceMiddleware(AgentMiddleware[dict, Any]):
    def __init__(self, node_name: str):
        super().__init__()
        self.node_name = node_name
        self.tools = []
        self._current_model_span_id: str | None = None
        self._model_call_seq = 0

    def before_model(self, state: dict, runtime: Any) -> dict[str, Any] | None:
        """模型调用前记录输入状态"""
        run_id = get_current_run_id()
        if not run_id:
            return None

        self._model_call_seq += 1
        self._current_model_span_id = f"model_call_{uuid.uuid4().hex[:8]}"

        messages = state.get("messages", [])

        recent_messages = messages[-10:] if len(messages) > 10 else messages
        serialized_messages = [_serialize_message(m) for m in recent_messages]

        last_message = messages[-1] if messages else None
        last_message_type = type(last_message).__name__ if last_message else "None"

        pending_tool_results = []
        for msg in reversed(messages):
            if isinstance(msg, ToolMessage):
                pending_tool_results.append({
                    "tool_call_id": getattr(msg, "tool_call_id", ""),
                    "content_preview": str(msg.content)[:200] if msg.content else ""
                })
            elif isinstance(msg, AIMessage):
                break

        payload = {
            "phase": "before",
            "model_span_id": self._current_model_span_id,
            "seq": self._model_call_seq,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_messages": len(messages),
            "last_message_type": last_message_type,
            "recent_messages": serialized_messages,
            "pending_tool_results": pending_tool_results[:5],
        }

        append_event({
            "type": "model_call",
            "run_id": run_id,
            "span_id": get_current_span_id(),
            "ts": datetime.now(timezone.utc).isoformat(),
            "node": self.node_name,
            "payload": payload,
        })

        return None

    async def abefore_model(self, state: dict, runtime: Any) -> dict[str, Any] | None:
        return self.before_model(state, runtime)

    def after_model(self, state: dict, runtime: Any) -> dict[str, Any] | None:
        """模型调用后记录输出"""
        run_id = get_current_run_id()
        if not run_id:
            return None

        messages = state.get("messages", [])
        last_message = messages[-1] if messages else None

        ai_content = ""
        tool_calls_info = []
        next_action = "unknown"

        if isinstance(last_message, AIMessage):
            ai_content = str(last_message.content)[:2000] if last_message.content else ""
            if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                tool_calls_info = [
                    {
                        "name": tc.get("name", "unknown"),
                        "id": tc.get("id", ""),
                        "args": {k: str(v)[:100] for k, v in tc.get("args", {}).items()}
                    }
                    for tc in last_message.tool_calls
                ]
                next_action = "tool_calls"
            else:
                next_action = "end"

        payload = {
            "phase": "after",
            "model_span_id": self._current_model_span_id,
            "seq": self._model_call_seq,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "response_content": ai_content,
            "tool_calls": tool_calls_info,
            "next_action": next_action,
        }

        append_event({
            "type": "model_call",
            "run_id": run_id,
            "span_id": get_current_span_id(),
            "ts": datetime.now(timezone.utc).isoformat(),
            "node": self.node_name,
            "payload": payload,
        })

        # 注意：不在此处重置 _current_model_span_id
        # 因为 tool_call 会在 after_model 之后执行，需要保留 model_span_id 用于关联
        # model_span_id 会在下一次 before_model 时自动更新

        return None

    async def aafter_model(self, state: dict, runtime: Any) -> dict[str, Any] | None:
        return self.after_model(state, runtime)

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        tool_name = request.tool.name if request.tool else request.tool_call.get("name", "unknown")
        tool_input = request.tool_call.get("args", {})
        tool_call_id = request.tool_call.get("id", "")
        call_time = datetime.now(timezone.utc).isoformat()

        success = True
        result = None
        try:
            result = handler(request)
            if isinstance(result, ToolMessage):
                tool_output = result.content
            else:
                tool_output = str(result)
        except Exception as e:
            success = False
            tool_output = {"error": str(e)}
            logger.error(f"Tool {tool_name} 调用失败: {e}")
            raise

        run_id = get_current_run_id()
        if run_id:
            if tool_name == "get_kline_image":
                self._save_image_artifact_from_output(run_id, tool_output)
            sanitized_output = self._sanitize_tool_output(tool_name, tool_output)
            record_tool_call(
                run_id,
                self.node_name,
                {
                    "tool_name": tool_name,
                    "tool_call_id": tool_call_id,
                    "input": tool_input,
                    "output": sanitized_output,
                    "timestamp": call_time,
                    "success": success,
                    "model_span_id": self._current_model_span_id,
                },
            )

        return result

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        tool_name = request.tool.name if request.tool else request.tool_call.get("name", "unknown")
        tool_input = request.tool_call.get("args", {})
        tool_call_id = request.tool_call.get("id", "")
        call_time = datetime.now(timezone.utc).isoformat()

        success = True
        result = None
        try:
            result = await handler(request)
            if isinstance(result, ToolMessage):
                tool_output = result.content
            else:
                tool_output = str(result)
        except Exception as e:
            success = False
            tool_output = {"error": str(e)}
            logger.error(f"Tool {tool_name} 调用失败: {e}")
            raise

        run_id = get_current_run_id()
        if run_id:
            if tool_name == "get_kline_image":
                self._save_image_artifact_from_output(run_id, tool_output)
            sanitized_output = self._sanitize_tool_output(tool_name, tool_output)
            record_tool_call(
                run_id,
                self.node_name,
                {
                    "tool_name": tool_name,
                    "tool_call_id": tool_call_id,
                    "input": tool_input,
                    "output": sanitized_output,
                    "timestamp": call_time,
                    "success": success,
                    "model_span_id": self._current_model_span_id,
                },
            )

        return result

    def _sanitize_tool_output(self, tool_name: str, tool_output: Any) -> Any:
        if tool_name != "get_kline_image":
            return tool_output
        try:
            if isinstance(tool_output, str):
                data = json.loads(tool_output)
                if isinstance(data, dict) and "image_data" in data:
                    data["image_data"] = "[omitted]"
                    return data
        except Exception:
            return tool_output
        return tool_output

    def _save_image_artifact_from_output(self, run_id: str, tool_output: Any) -> None:
        try:
            data = json.loads(tool_output) if isinstance(tool_output, str) else tool_output
            if isinstance(data, dict) and data.get("image_data") and data.get("success"):
                symbol = data.get("symbol", "unknown")
                intervals = data.get("intervals", ["unknown"])
                interval = intervals[0] if intervals else "unknown"
                save_image_artifact(run_id, symbol, interval, data["image_data"])
        except Exception as e:
            logger.debug(f"保存图像 artifact 失败: {e}")
