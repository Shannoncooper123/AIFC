import json
import os
from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.models.schemas import (
    WorkflowRunsResponse,
    WorkflowRunSummary,
    WorkflowRunDetailResponse,
    WorkflowRunEvent,
    WorkflowArtifact,
    WorkflowTimelineResponse,
    WorkflowTimeline,
    WorkflowSpan,
    WorkflowSpanChild,
)
from modules.agent.utils.workflow_trace_storage import get_trace_path, get_artifacts_dir


router = APIRouter(prefix="/api/workflow", tags=["workflow"])


def _read_events() -> List[Dict[str, Any]]:
    """读取所有 trace 事件"""
    trace_path = get_trace_path()
    if not os.path.exists(trace_path):
        return []
    events: List[Dict[str, Any]] = []
    with open(trace_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def _summarize_runs(events: List[Dict[str, Any]]) -> List[WorkflowRunSummary]:
    """汇总运行记录"""
    runs: Dict[str, WorkflowRunSummary] = {}
    run_start_times: Dict[str, int] = {}
    run_end_times: Dict[str, int] = {}
    
    for event in events:
        run_id = event.get("run_id")
        if not run_id:
            continue
        if run_id not in runs:
            runs[run_id] = WorkflowRunSummary(
                run_id=run_id,
                start_time=None,
                end_time=None,
                duration_ms=None,
                status=None,
                symbols=[],
                pending_count=0,
                nodes_count=0,
                tool_calls_count=0,
                model_calls_count=0,
                artifacts_count=0,
            )
        run = runs[run_id]
        event_type = event.get("type")
        
        if event_type == "run_start":
            run.start_time = event.get("ts")
            run_start_times[run_id] = event.get("timestamp_ms", 0)
            alert = event.get("alert", {}) or {}
            run.symbols = alert.get("symbols", []) or []
            run.pending_count = int(alert.get("pending_count", 0) or 0)
        elif event_type == "run_end":
            run.end_time = event.get("ts")
            run_end_times[run_id] = event.get("timestamp_ms", 0)
            run.status = event.get("status")
        elif event_type == "span_start":
            node = event.get("node", "")
            if not node.startswith("tool:"):
                run.nodes_count += 1
        elif event_type == "node_event" and event.get("phase") == "start":
            run.nodes_count += 1
        elif event_type == "tool_call":
            run.tool_calls_count += 1
        elif event_type == "model_call":
            run.model_calls_count += 1
        elif event_type == "artifact":
            run.artifacts_count += 1
    
    for run_id, run in runs.items():
        start_ts = run_start_times.get(run_id, 0)
        end_ts = run_end_times.get(run_id, 0)
        if start_ts and end_ts:
            run.duration_ms = end_ts - start_ts
    
    return list(runs.values())


def _build_timeline(run_id: str, events: List[Dict[str, Any]]) -> WorkflowTimeline:
    """构建时间线树形结构"""
    run_events = [e for e in events if e.get("run_id") == run_id]
    run_events.sort(key=lambda e: (e.get("seq", 0), e.get("timestamp_ms", 0)))
    
    timeline = WorkflowTimeline(
        run_id=run_id,
        start_time=None,
        end_time=None,
        duration_ms=None,
        status=None,
        symbols=[],
        spans=[],
    )
    
    spans_map: Dict[str, WorkflowSpan] = {}
    span_children: Dict[str, List[WorkflowSpanChild]] = {}
    span_artifacts: Dict[str, List[WorkflowArtifact]] = {}
    
    for event in run_events:
        event_type = event.get("type")
        
        if event_type == "run_start":
            timeline.start_time = event.get("ts")
            alert = event.get("alert", {}) or {}
            timeline.symbols = alert.get("symbols", []) or []
            
        elif event_type == "run_end":
            timeline.end_time = event.get("ts")
            timeline.status = event.get("status")
            
        elif event_type == "span_start":
            span_id = event.get("span_id")
            if span_id:
                span = WorkflowSpan(
                    span_id=span_id,
                    parent_span_id=event.get("parent_span_id"),
                    node=event.get("node", "unknown"),
                    symbol=event.get("symbol"),
                    start_time=event.get("ts"),
                    end_time=None,
                    duration_ms=None,
                    status="running",
                    error=None,
                    output_summary=None,
                    children=[],
                    artifacts=[],
                )
                spans_map[span_id] = span
                span_children[span_id] = []
                span_artifacts[span_id] = []
                
        elif event_type == "span_end":
            span_id = event.get("span_id")
            if span_id and span_id in spans_map:
                span = spans_map[span_id]
                span.end_time = event.get("ts")
                span.duration_ms = event.get("duration_ms")
                span.status = event.get("status", "success")
                span.error = event.get("error")
                span.output_summary = event.get("output_summary")
                
        elif event_type == "tool_call":
            span_id = event.get("span_id")
            payload = event.get("payload", {})
            child = WorkflowSpanChild(
                type="tool_call",
                ts=event.get("ts"),
                seq=event.get("seq", 0),
                tool_name=event.get("tool_name") or payload.get("tool_name"),
                symbol=event.get("symbol"),
                duration_ms=None,
                status="success" if payload.get("success", True) else "error",
                error=payload.get("error") if not payload.get("success", True) else None,
                payload=payload,
            )
            if span_id and span_id in span_children:
                span_children[span_id].append(child)
            else:
                for sid in reversed(list(spans_map.keys())):
                    span_children[sid].append(child)
                    break
                    
        elif event_type == "model_call":
            span_id = event.get("span_id")
            payload = event.get("payload", {})
            child = WorkflowSpanChild(
                type="model_call",
                ts=event.get("ts"),
                seq=event.get("seq", 0),
                tool_name=None,
                symbol=event.get("symbol"),
                duration_ms=None,
                status="success",
                error=None,
                payload=payload,
            )
            if span_id and span_id in span_children:
                span_children[span_id].append(child)
            else:
                for sid in reversed(list(spans_map.keys())):
                    span_children[sid].append(child)
                    break
                    
        elif event_type == "artifact":
            payload = event.get("payload", {})
            span_id = event.get("span_id") or payload.get("span_id")
            artifact = WorkflowArtifact(
                artifact_id=payload.get("artifact_id", ""),
                run_id=run_id,
                type=payload.get("type", "unknown"),
                file_path=payload.get("file_path", ""),
                span_id=span_id,
                symbol=payload.get("symbol"),
                interval=payload.get("interval"),
                created_at=payload.get("created_at"),
            )
            if span_id and span_id in span_artifacts:
                span_artifacts[span_id].append(artifact)
    
    for span_id, span in spans_map.items():
        span.children = span_children.get(span_id, [])
        span.artifacts = span_artifacts.get(span_id, [])
    
    child_spans_map: Dict[str, List[WorkflowSpan]] = {}
    root_spans = []
    
    for span_id, span in spans_map.items():
        parent_id = span.parent_span_id
        if parent_id and parent_id in spans_map:
            if parent_id not in child_spans_map:
                child_spans_map[parent_id] = []
            child_spans_map[parent_id].append(span)
        else:
            root_spans.append(span)
    
    def attach_nested_spans(span: WorkflowSpan) -> None:
        """递归地将子 spans 附加到父 span 的 nested_spans 字段"""
        nested = child_spans_map.get(span.span_id, [])
        nested.sort(key=lambda s: s.start_time or "")
        for child_span in nested:
            attach_nested_spans(child_span)
        span.nested_spans = nested
    
    for span in root_spans:
        attach_nested_spans(span)
    
    root_spans.sort(key=lambda s: s.start_time or "")
    
    if timeline.start_time and timeline.end_time:
        try:
            start_dt = datetime.fromisoformat(timeline.start_time.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(timeline.end_time.replace("Z", "+00:00"))
            timeline.duration_ms = int((end_dt - start_dt).total_seconds() * 1000)
        except Exception:
            pass
    
    timeline.spans = root_spans
    
    return timeline


@router.get("/runs", response_model=WorkflowRunsResponse)
async def list_runs(limit: int = Query(default=50, ge=1, le=500)):
    """获取 workflow 运行列表"""
    events = _read_events()
    runs = _summarize_runs(events)
    runs_sorted = sorted(runs, key=lambda r: r.start_time or "", reverse=True)[:limit]
    return WorkflowRunsResponse(runs=runs_sorted, total=len(runs_sorted))


@router.get("/runs/{run_id}", response_model=WorkflowRunDetailResponse)
async def get_run(run_id: str):
    """获取 workflow 运行详情（原始事件列表）"""
    events = _read_events()
    run_events = [e for e in events if e.get("run_id") == run_id]
    if not run_events:
        raise HTTPException(status_code=404, detail=f"运行记录不存在: {run_id}")
    run_events.sort(key=lambda e: (e.get("seq", 0), e.get("timestamp_ms", 0)))
    return WorkflowRunDetailResponse(
        run_id=run_id,
        events=[WorkflowRunEvent(**e) for e in run_events],
    )


@router.get("/runs/{run_id}/timeline", response_model=WorkflowTimelineResponse)
async def get_run_timeline(run_id: str):
    """获取 workflow 运行时间线（树形结构）"""
    events = _read_events()
    run_events = [e for e in events if e.get("run_id") == run_id]
    if not run_events:
        raise HTTPException(status_code=404, detail=f"运行记录不存在: {run_id}")
    timeline = _build_timeline(run_id, events)
    return WorkflowTimelineResponse(timeline=timeline)


@router.get("/runs/{run_id}/artifacts", response_model=List[WorkflowArtifact])
async def list_run_artifacts(run_id: str):
    """获取 workflow 运行的 artifacts"""
    events = _read_events()
    artifacts = []
    for e in events:
        if e.get("type") == "artifact" and e.get("run_id") == run_id:
            payload = e.get("payload") or {}
            artifacts.append(WorkflowArtifact(**payload))
    return artifacts


@router.get("/artifacts/{artifact_id}")
async def get_artifact(artifact_id: str):
    """获取 artifact 文件"""
    events = _read_events()
    for e in events:
        if e.get("type") == "artifact":
            payload = e.get("payload") or {}
            if payload.get("artifact_id") == artifact_id:
                file_path = payload.get("file_path")
                if not file_path or not os.path.exists(file_path):
                    raise HTTPException(status_code=404, detail="文件不存在")
                return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="Artifact 不存在")
