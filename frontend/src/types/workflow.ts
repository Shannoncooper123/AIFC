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
}

export interface WorkflowArtifact {
  artifact_id: string;
  run_id: string;
  type: string;
  file_path: string;
  span_id?: string;
  symbol?: string;
  interval?: string;
  created_at?: string;
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

export interface WorkflowTimeline {
  run_id: string;
  start_time?: string;
  end_time?: string;
  duration_ms?: number;
  status?: string;
  symbols: string[];
  spans: WorkflowSpan[];
}
