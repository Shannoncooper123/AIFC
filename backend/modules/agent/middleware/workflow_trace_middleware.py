"""
Workflow Trace Middleware - 记录 Agent 的模型调用和工具调用

功能：
1. 在 model 调用前后记录 model_call trace
2. 在 tool 调用时记录 tool_call trace
3. 从多模态内容中提取并保存图片 artifact
4. 使用内容哈希为图像生成稳定的唯一 ID，实现去重和一致性匹配
"""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Callable

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.config import get_config
from langgraph.types import Command

from modules.agent.utils.workflow_trace_storage import (
    now_iso,
    calculate_duration_ms,
    generate_trace_id,
    record_trace,
    save_image_artifact,
)
from modules.monitor.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Awaitable
    from langchain.tools.tool_node import ToolCallRequest

logger = get_logger("agent.workflow_trace_middleware")


def _get_content_hash(base64_data: str) -> str:
    """基于图像内容生成唯一哈希值（取前12位）"""
    return hashlib.sha256(base64_data.encode()).hexdigest()[:12]


def _is_base64_image(url: str) -> bool:
    return isinstance(url, str) and url.startswith("data:image")


def _get_image_url_field(item: dict) -> tuple[str, str]:
    """从 image_url 项中提取 url 和 detail"""
    image_url = item.get("image_url", {})
    if isinstance(image_url, dict):
        return image_url.get("url", ""), image_url.get("detail", "auto")
    return "", "auto"


def _extract_base64_from_url(url: str) -> str | None:
    """从 data URL 中提取 base64 数据"""
    if not _is_base64_image(url):
        return None
    if "," not in url:
        return None
    base64_data = url.split(",", 1)[1]
    return base64_data if base64_data else None


class ImageRegistry:
    """图像注册表 - 基于内容哈希实现去重和稳定 ID
    
    核心特性：
    1. 同一张图像（相同内容）永远得到相同的 ID
    2. 自动去重，避免重复保存
    3. 支持附加元数据（symbol, interval）
    """
    
    def __init__(self):
        self._saved_ids: set[str] = set()
        self._pending_images: dict[str, dict] = {}
    
    def get_image_id(self, base64_data: str) -> str:
        """基于内容哈希生成图像 ID"""
        return f"img_{_get_content_hash(base64_data)}"
    
    def register(
        self,
        base64_data: str,
        symbol: str = "unknown",
        interval: str = "unknown",
    ) -> str:
        """注册图像，返回 image_id
        
        如果图像已保存，直接返回 ID（不重复保存）
        如果图像未保存，加入待保存队列
        """
        image_id = self.get_image_id(base64_data)
        
        if image_id in self._saved_ids:
            return image_id
        
        if image_id not in self._pending_images:
            self._pending_images[image_id] = {
                "base64_data": base64_data,
                "symbol": symbol,
                "interval": interval,
            }
        
        return image_id
    
    def get_pending_images(self) -> dict[str, dict]:
        """获取待保存的图像"""
        return self._pending_images.copy()
    
    def mark_saved(self, image_ids: list[str]) -> None:
        """标记图像已保存"""
        for image_id in image_ids:
            self._saved_ids.add(image_id)
            self._pending_images.pop(image_id, None)
    
    def clear_pending(self) -> None:
        """清空待保存队列"""
        self._pending_images.clear()


def _sanitize_multimodal_content(
    content: Any,
    registry: ImageRegistry,
    image_metas: list[dict] | None = None,
) -> Any:
    """清理多模态内容列表，为每个图像生成基于内容哈希的 ID
    
    Args:
        content: 多模态内容列表
        registry: 图像注册表
        image_metas: 图像元数据列表，按图像出现顺序对应，每项包含 symbol 和 interval
    """
    if not isinstance(content, list):
        return content
    
    result = []
    image_index = 0
    
    for item in content:
        if not isinstance(item, dict) or item.get("type") != "image_url":
            result.append(item)
            continue
        
        url, detail = _get_image_url_field(item)
        base64_data = _extract_base64_from_url(url)
        
        if not base64_data:
            result.append(item)
            continue
        
        symbol = "unknown"
        interval = "unknown"
        if image_metas and image_index < len(image_metas):
            meta = image_metas[image_index]
            symbol = meta.get("symbol", "unknown")
            interval = meta.get("interval", "unknown")
        
        image_id = registry.register(base64_data, symbol, interval)
        
        result.append({
            "type": "image_url",
            "image_url": {"url": f"[IMAGE:{image_id}]", "detail": detail}
        })
        image_index += 1
    
    return result


def _serialize_message(
    msg: Any,
    registry: ImageRegistry,
    tool_inputs: dict[str, dict] | None = None,
) -> dict:
    """序列化消息为可存储的格式，同时为图像生成稳定 ID
    
    Args:
        msg: 消息对象
        registry: 图像注册表
        tool_inputs: 工具输入缓存，key 为 tool_call_id，value 为 {symbol, interval}
    
    对于 HumanMessage，会从 additional_kwargs["_image_metas"] 中提取图像元数据。
    对于 ToolMessage，会从 tool_inputs 中根据 tool_call_id 获取元数据。
    """
    if isinstance(msg, HumanMessage):
        content = msg.content
        if isinstance(content, list):
            image_metas = msg.additional_kwargs.get("_image_metas") if msg.additional_kwargs else None
            content = _sanitize_multimodal_content(content, registry, image_metas)
        return {"role": "human", "content": content if isinstance(content, list) else str(content)}
    
    if isinstance(msg, AIMessage):
        result = {"role": "ai", "content": str(msg.content) if msg.content else ""}
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            result["tool_calls"] = [
                {"name": tc.get("name", "unknown"), "args_keys": list(tc.get("args", {}).keys()), "args": tc.get("args", {})}
                for tc in msg.tool_calls
            ]
        return result
    
    if isinstance(msg, ToolMessage):
        content = msg.content
        tool_call_id = getattr(msg, "tool_call_id", "")
        if isinstance(content, list):
            image_metas = None
            if tool_inputs and tool_call_id:
                tool_input = tool_inputs.get(tool_call_id, {})
                if tool_input:
                    image_metas = [{"symbol": tool_input.get("symbol", "unknown"), "interval": tool_input.get("interval", "unknown")}]
            content = _sanitize_multimodal_content(content, registry, image_metas)
        elif not isinstance(content, str):
            content = str(content)
        return {"role": "tool", "tool_call_id": tool_call_id, "content": content}
    
    if isinstance(msg, SystemMessage):
        return {"role": "system", "content": str(msg.content)}
    
    return {"role": "unknown", "content": str(msg)}


class WorkflowTraceMiddleware(AgentMiddleware[dict, Any]):
    """Agent Middleware 用于记录模型调用和工具调用的 trace
    
    使用基于内容哈希的图像 ID 方案：
    - 同一张图像在工具调用和模型调用中得到相同的 ID
    - 自动去重，避免重复保存
    - 前端可通过 image_id 正确匹配 artifact
    """
    
    def __init__(self, node_name: str):
        super().__init__()
        self.node_name = node_name
        self._cached_workflow_run_id: str | None = None
        self._cached_parent_trace_id: str | None = None
        self._current_model_trace_id: str | None = None
        self._current_model_start_time: str | None = None
        self._model_call_seq = 0
        self._image_registry = ImageRegistry()
        self._tool_inputs: dict[str, dict] = {}

    def _cache_trace_context(self, workflow_run_id: str | None, parent_trace_id: str | None) -> None:
        self._cached_workflow_run_id = workflow_run_id
        self._cached_parent_trace_id = parent_trace_id

    def _get_trace_context(self, runtime: Any = None) -> tuple[str | None, str | None]:
        """获取 trace context，优先使用缓存"""
        if self._cached_workflow_run_id:
            return self._cached_workflow_run_id, self._cached_parent_trace_id
        
        configurable = {}
        if runtime and hasattr(runtime, 'config'):
            config = getattr(runtime, 'config', None) or {}
            configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
        else:
            try:
                config = get_config()
                configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
            except Exception as e:
                logger.debug(f"获取 trace context 失败: {e}")
        
        workflow_run_id = configurable.get("workflow_run_id")
        parent_trace_id = configurable.get("current_trace_id")
        self._cache_trace_context(workflow_run_id, parent_trace_id)
        return workflow_run_id, parent_trace_id

    def before_model(self, state: dict, runtime: Any) -> dict[str, Any] | None:
        workflow_run_id, _ = self._get_trace_context()
        if not workflow_run_id:
            logger.debug(f"[{self.node_name}] before_model: 未获取到 workflow_run_id，跳过 trace")
            return None

        self._model_call_seq += 1
        self._current_model_trace_id = generate_trace_id("model")
        self._current_model_start_time = now_iso()
        logger.debug(f"[{self.node_name}] before_model: seq={self._model_call_seq}, trace_id={self._current_model_trace_id}")
        return None

    async def abefore_model(self, state: dict, runtime: Any) -> dict[str, Any] | None:
        return self.before_model(state, runtime)

    def after_model(self, state: dict, runtime: Any) -> dict[str, Any] | None:
        if not self._cached_workflow_run_id or not self._current_model_trace_id:
            return None
        
        logger.debug(f"[{self.node_name}] after_model: 记录 model_call trace")

        messages = state.get("messages", [])
        last_message = messages[-1] if messages else None
        
        serialized_messages = [_serialize_message(m, self._image_registry, self._tool_inputs) for m in messages]
        
        pending_images = self._image_registry.get_pending_images()
        if pending_images:
            self._save_pending_images(pending_images)

        ai_content = ""
        tool_calls_info = []
        next_action = "unknown"

        if isinstance(last_message, AIMessage):
            ai_content = str(last_message.content) if last_message.content else ""
            if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                tool_calls_info = [
                    {"name": tc.get("name", "unknown"), "id": tc.get("id", ""), "args": {k: str(v) for k, v in tc.get("args", {}).items()}}
                    for tc in last_message.tool_calls
                ]
                next_action = "tool_calls"
            else:
                next_action = "end"

        end_time = now_iso()
        record_trace(
            workflow_run_id=self._cached_workflow_run_id,
            trace_id=self._current_model_trace_id,
            parent_trace_id=self._cached_parent_trace_id,
            trace_type="model_call",
            name=f"{self.node_name}_model_{self._model_call_seq}",
            status="success",
            start_time=self._current_model_start_time,
            end_time=end_time,
            duration_ms=calculate_duration_ms(self._current_model_start_time, end_time),
            payload={
                "seq": self._model_call_seq,
                "messages": serialized_messages,
                "response_content": ai_content,
                "tool_calls": tool_calls_info,
                "next_action": next_action,
            },
        )
        return None

    async def aafter_model(self, state: dict, runtime: Any) -> dict[str, Any] | None:
        return self.after_model(state, runtime)

    def _save_pending_images(self, images: dict[str, dict]) -> None:
        """保存待处理的图像 artifact"""
        if not self._cached_workflow_run_id:
            return
        
        saved_ids = []
        for image_id, data in images.items():
            try:
                save_image_artifact(
                    workflow_run_id=self._cached_workflow_run_id,
                    parent_trace_id=self._current_model_trace_id or self._cached_parent_trace_id,
                    symbol=data["symbol"],
                    interval=data["interval"],
                    image_base64=data["base64_data"],
                    image_id=image_id,
                )
                saved_ids.append(image_id)
                logger.debug(f"[{self.node_name}] 保存图像 artifact: {image_id} ({data['symbol']} {data['interval']})")
            except Exception as e:
                logger.debug(f"保存图像 artifact 失败 {image_id}: {e}")
        
        self._image_registry.mark_saved(saved_ids)

    def _record_tool_call(
        self,
        tool_name: str,
        tool_input: dict,
        tool_call_id: str,
        tool_output: Any,
        start_time: str,
        success: bool,
        error_msg: str | None = None,
        request: Any = None,
    ) -> None:
        """记录工具调用 trace，并缓存工具输入用于后续 ToolMessage 处理"""
        workflow_run_id, parent_trace_id = self._get_trace_context(request.runtime if request else None)
        if not workflow_run_id:
            logger.debug(f"[{self.node_name}] _record_tool_call: 未获取到 workflow_run_id，跳过 trace")
            return
        
        logger.debug(f"[{self.node_name}] _record_tool_call: tool={tool_name}")

        tool_trace_id = generate_trace_id("tool")
        end_time = now_iso()

        symbol = tool_input.get("symbol", "unknown") if isinstance(tool_input, dict) else "unknown"
        interval = tool_input.get("interval", "unknown") if isinstance(tool_input, dict) else "unknown"
        
        if tool_call_id:
            self._tool_inputs[tool_call_id] = {"symbol": symbol, "interval": interval}
        
        sanitized_output = tool_output
        if isinstance(tool_output, list):
            tool_image_metas = [{"symbol": symbol, "interval": interval}]
            sanitized_output = _sanitize_multimodal_content(
                tool_output, self._image_registry, tool_image_metas
            )

        record_trace(
            workflow_run_id=workflow_run_id,
            trace_id=tool_trace_id,
            parent_trace_id=parent_trace_id,
            trace_type="tool_call",
            name=tool_name,
            status="success" if success else "error",
            start_time=start_time,
            end_time=end_time,
            duration_ms=calculate_duration_ms(start_time, end_time),
            symbol=symbol if symbol != "unknown" else None,
            payload={
                "tool_call_id": tool_call_id,
                "input": tool_input,
                "output": sanitized_output,
                "success": success,
            },
            error=error_msg,
        )

    @contextmanager
    def _tool_call_context(self, request: ToolCallRequest):
        """工具调用的上下文管理器"""
        tool_name = request.tool.name if request.tool else request.tool_call.get("name", "unknown")
        tool_input = request.tool_call.get("args", {})
        tool_call_id = request.tool_call.get("id", "")
        start_time = now_iso()

        context = {"success": True, "error_msg": None, "tool_output": None, "result": None}
        
        try:
            yield context
        except Exception as e:
            context["success"] = False
            context["error_msg"] = str(e)
            context["tool_output"] = {"error": str(e)}
            logger.error(f"Tool {tool_name} 调用失败: {e}")
            raise
        finally:
            self._record_tool_call(
                tool_name=tool_name,
                tool_input=tool_input,
                tool_call_id=tool_call_id,
                tool_output=context["tool_output"] if context["success"] else {"error": context["error_msg"]},
                start_time=start_time,
                success=context["success"],
                error_msg=context["error_msg"],
                request=request,
            )

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        with self._tool_call_context(request) as ctx:
            result = handler(request)
            ctx["tool_output"] = result.content if isinstance(result, ToolMessage) else str(result)
            ctx["result"] = result
        return ctx["result"]

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        with self._tool_call_context(request) as ctx:
            result = await handler(request)
            ctx["tool_output"] = result.content if isinstance(result, ToolMessage) else str(result)
            ctx["result"] = result
        return ctx["result"]
