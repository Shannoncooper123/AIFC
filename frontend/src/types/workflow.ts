/**
 * Workflow 相关类型定义
 */

export interface WorkflowRunSummary {
  run_id: string;
  start_time?: string;
  end_time?: string;
  duration_ms?: number;
  status?: string;
  symbols: string[];
  pending_count: number;
  nodes_count: number;
  tool_calls_count: number;
  model_calls_count: number;
  artifacts_count: number;
}

export interface WorkflowRunEvent {
  type: string;
  run_id: string;
  ts: string;
  seq?: number;
  timestamp_ms?: number;
  span_id?: string;
  parent_span_id?: string;
  node?: string;
  phase?: string;
  symbol?: string;
  tool_name?: string;
  duration_ms?: number;
  payload?: Record<string, unknown>;
  status?: string;
  error?: string;
  output_summary?: Record<string, unknown>;
}

/**
 * Trace 类型枚举
 */
export type TraceType = 'workflow' | 'node' | 'agent' | 'model_call' | 'tool_call' | 'artifact';

/**
 * Workflow Trace 项（新的层级化结构）
 */
export interface WorkflowTraceItem {
  trace_id: string;
  parent_trace_id?: string;
  type: TraceType;
  name: string;
  symbol?: string;
  start_time?: string;
  end_time?: string;
  duration_ms?: number;
  status?: string;
  error?: string;
  payload?: Record<string, unknown>;
  children: WorkflowTraceItem[];
  artifacts: WorkflowArtifact[];
}

export interface WorkflowArtifact {
  artifact_id: string;
  run_id: string;
  type: string;
  file_path: string;
  trace_id?: string;
  parent_trace_id?: string;
  span_id?: string;
  symbol?: string;
  interval?: string;
  image_id?: string;
  created_at?: string;
}

export interface WorkflowTimeline {
  run_id: string;
  start_time?: string;
  end_time?: string;
  duration_ms?: number;
  status?: string;
  symbols: string[];
  traces: WorkflowTraceItem[];
}

/**
 * 以下为兼容旧接口的类型定义
 */
export interface WorkflowSpanChild {
  type: 'tool_call' | 'model_call';
  ts: string;
  seq: number;
  tool_name?: string;
  symbol?: string;
  duration_ms?: number;
  status?: string;
  error?: string;
  payload?: Record<string, unknown>;
  model_span_id?: string;
}

export interface WorkflowSpan {
  span_id: string;
  parent_span_id?: string;
  node: string;
  symbol?: string;
  start_time: string;
  end_time?: string;
  duration_ms?: number;
  status: string;
  error?: string;
  output_summary?: Record<string, unknown>;
  children: WorkflowSpanChild[];
  artifacts: WorkflowArtifact[];
  nested_spans: WorkflowSpan[];
}
