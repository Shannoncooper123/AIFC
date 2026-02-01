#!/usr/bin/env python3
"""
迁移脚本：将旧版单文件 workflow_trace.jsonl 拆分为新的分层存储格式

新格式：
- workflow_index.jsonl: 索引文件，存储每个 workflow 的摘要信息
- workflow_traces/: 目录，按 workflow_run_id 分文件存储详细 trace

使用方式：
    cd backend
    python scripts/migrate_workflow_traces.py
    
    # 或指定源文件
    python scripts/migrate_workflow_traces.py --source modules/data/workflow_trace.jsonl
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.config.settings import load_config, get_config


def migrate_workflow_traces(source_path: str, dry_run: bool = False) -> None:
    """
    迁移 workflow trace 数据
    
    Args:
        source_path: 源文件路径（旧版单文件）
        dry_run: 是否只预览不实际写入
    """
    if not os.path.exists(source_path):
        print(f"❌ 源文件不存在: {source_path}")
        return
    
    cfg = get_config()
    agent_cfg = cfg.get("agent", {})
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    index_path = agent_cfg.get("workflow_index_path", "modules/data/workflow_index.jsonl")
    if not os.path.isabs(index_path):
        index_path = os.path.join(base_dir, index_path)
    
    traces_dir = agent_cfg.get("workflow_traces_dir", "modules/data/workflow_traces")
    if not os.path.isabs(traces_dir):
        traces_dir = os.path.join(base_dir, traces_dir)
    
    print(f"📂 源文件: {source_path}")
    print(f"📂 索引文件: {index_path}")
    print(f"📂 Trace 目录: {traces_dir}")
    print()
    
    events_by_run: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    workflow_summaries: Dict[str, Dict[str, Any]] = {}
    total_events = 0
    parse_errors = 0
    
    print("📖 读取源文件...")
    with open(source_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                total_events += 1
                
                workflow_run_id = event.get("workflow_run_id")
                if not workflow_run_id:
                    continue
                
                events_by_run[workflow_run_id].append(event)
                
                event_type = event.get("type")
                status = event.get("status")
                
                if workflow_run_id not in workflow_summaries:
                    workflow_summaries[workflow_run_id] = {
                        "run_id": workflow_run_id,
                        "start_time": None,
                        "end_time": None,
                        "duration_ms": None,
                        "status": None,
                        "symbols": [],
                        "pending_count": 0,
                        "nodes_count": 0,
                        "tool_calls_count": 0,
                        "model_calls_count": 0,
                        "artifacts_count": 0,
                    }
                
                summary = workflow_summaries[workflow_run_id]
                
                if event_type == "workflow":
                    if status == "running":
                        summary["start_time"] = event.get("start_time")
                        payload = event.get("payload", {})
                        alert = payload.get("alert", {})
                        summary["symbols"] = alert.get("symbols", [])
                        summary["pending_count"] = alert.get("pending_count", 0)
                    else:
                        summary["end_time"] = event.get("end_time")
                        summary["duration_ms"] = event.get("duration_ms")
                        summary["status"] = status
                        if not summary["start_time"]:
                            summary["start_time"] = event.get("start_time")
                elif event_type == "node":
                    summary["nodes_count"] += 1
                elif event_type == "tool_call":
                    summary["tool_calls_count"] += 1
                elif event_type == "model_call":
                    summary["model_calls_count"] += 1
                elif event_type == "artifact":
                    summary["artifacts_count"] += 1
                    
            except json.JSONDecodeError as e:
                parse_errors += 1
                print(f"  ⚠️ 第 {line_num} 行解析失败: {e}")
                continue
    
    print(f"✅ 读取完成: {total_events} 条事件, {len(events_by_run)} 个 workflow")
    if parse_errors > 0:
        print(f"  ⚠️ {parse_errors} 条解析失败")
    print()
    
    if dry_run:
        print("🔍 预览模式 (--dry-run)，不实际写入文件")
        print()
        print("将创建以下文件:")
        print(f"  - {index_path} ({len(workflow_summaries)} 条记录)")
        for run_id in sorted(events_by_run.keys())[:10]:
            trace_path = os.path.join(traces_dir, f"{run_id}.jsonl")
            print(f"  - {trace_path} ({len(events_by_run[run_id])} 条事件)")
        if len(events_by_run) > 10:
            print(f"  ... 还有 {len(events_by_run) - 10} 个文件")
        return
    
    print("📝 创建目录...")
    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    os.makedirs(traces_dir, exist_ok=True)
    
    print("📝 写入索引文件...")
    sorted_summaries = sorted(
        workflow_summaries.values(),
        key=lambda s: s.get("start_time") or "",
        reverse=True
    )
    with open(index_path, "w", encoding="utf-8") as f:
        for summary in sorted_summaries:
            f.write(json.dumps(summary, ensure_ascii=False) + "\n")
    print(f"  ✅ 写入 {len(sorted_summaries)} 条索引记录")
    
    print("📝 写入 trace 文件...")
    for run_id, events in events_by_run.items():
        trace_path = os.path.join(traces_dir, f"{run_id}.jsonl")
        events_sorted = sorted(events, key=lambda e: e.get("timestamp_ms", 0))
        with open(trace_path, "w", encoding="utf-8") as f:
            for event in events_sorted:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
    print(f"  ✅ 写入 {len(events_by_run)} 个 trace 文件")
    
    print()
    print("🎉 迁移完成!")
    print()
    print("后续步骤:")
    print(f"  1. 验证新文件是否正确生成")
    print(f"  2. 测试 API 是否正常工作")
    print(f"  3. 可选：备份并删除旧文件 {source_path}")


def main():
    parser = argparse.ArgumentParser(
        description="迁移 workflow trace 数据到新的分层存储格式"
    )
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="源文件路径（默认从 config.yaml 读取 workflow_trace_path）"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预览模式，不实际写入文件"
    )
    
    args = parser.parse_args()
    
    load_config()
    cfg = get_config()
    
    if args.source:
        source_path = args.source
    else:
        agent_cfg = cfg.get("agent", {})
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        source_path = agent_cfg.get("workflow_trace_path", "modules/data/workflow_trace.jsonl")
        if not os.path.isabs(source_path):
            source_path = os.path.join(base_dir, source_path)
    
    migrate_workflow_traces(source_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
