import { useMemo } from 'react';
import {
  Clock,
  Bot,
  Wrench,
  Image,
  CheckCircle2,
  XCircle,
  Loader2,
} from 'lucide-react';
import type { WorkflowTimeline, WorkflowSpan, WorkflowArtifact } from '../../../types';
import { formatDuration } from '../../../utils';
import { getStatusColor, getStatusBgColor } from '../utils/workflowHelpers';

interface ExecutionSummaryProps {
  timeline: WorkflowTimeline;
  allArtifacts: WorkflowArtifact[];
}

/**
 * 获取状态图标组件
 * @param status - 状态值
 * @returns 对应的图标组件
 */
function getStatusIcon(status: string) {
  switch (status) {
    case 'success':
      return <CheckCircle2 size={20} className="text-emerald-500" />;
    case 'error':
      return <XCircle size={20} className="text-rose-500" />;
    case 'running':
      return <Loader2 size={20} className="text-yellow-400 animate-spin" />;
    default:
      return <Clock size={20} className="text-neutral-400" />;
  }
}

/**
 * 获取状态显示文本
 * @param status - 状态值
 * @returns 状态文本
 */
function getStatusText(status: string): string {
  switch (status) {
    case 'success':
      return 'Success';
    case 'error':
      return 'Error';
    case 'running':
      return 'Running';
    default:
      return 'Unknown';
  }
}

/**
 * 统计所有 model_call 和 tool_call 数量
 * @param spans - 工作流 span 列表
 * @returns 统计结果
 */
function countCalls(spans: WorkflowSpan[]): { modelCalls: number; toolCalls: number } {
  let modelCalls = 0;
  let toolCalls = 0;

  function traverse(spanList: WorkflowSpan[]) {
    for (const span of spanList) {
      for (const child of span.children) {
        if (child.type === 'model_call') {
          modelCalls++;
        } else if (child.type === 'tool_call') {
          toolCalls++;
        }
      }
      if (span.nested_spans && span.nested_spans.length > 0) {
        traverse(span.nested_spans);
      }
    }
  }

  traverse(spans);
  return { modelCalls: Math.ceil(modelCalls / 2), toolCalls };
}

/**
 * 提取最后一个 AI 响应内容
 * @param spans - 工作流 span 列表
 * @returns 最后的 AI 响应内容
 */
function extractLastAIResponse(spans: WorkflowSpan[]): string | null {
  let lastResponse: string | null = null;
  let lastTimestamp = 0;

  function traverse(spanList: WorkflowSpan[]) {
    for (const span of spanList) {
      for (const child of span.children) {
        if (child.type === 'model_call') {
          const payload = child.payload as Record<string, unknown> | undefined;
          const phase = payload?.phase as string | undefined;
          const responseContent = payload?.response_content as string | undefined;
          
          if (phase === 'after' && responseContent) {
            const childTs = child.ts ? new Date(child.ts).getTime() : 0;
            if (childTs > lastTimestamp) {
              lastTimestamp = childTs;
              lastResponse = responseContent;
            }
          }
        }
      }
      if (span.nested_spans && span.nested_spans.length > 0) {
        traverse(span.nested_spans);
      }
    }
  }

  traverse(spans);
  return lastResponse;
}

/**
 * 执行摘要组件 - 显示工作流运行的概览信息
 */
export function ExecutionSummary({ timeline, allArtifacts }: ExecutionSummaryProps) {
  const status = timeline.status || 'unknown';
  
  const { modelCalls, toolCalls } = useMemo(
    () => countCalls(timeline.spans),
    [timeline.spans]
  );

  const lastAIResponse = useMemo(
    () => extractLastAIResponse(timeline.spans),
    [timeline.spans]
  );

  return (
    <div className="bg-[#1a1a1a] rounded-lg border border-neutral-800 p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div
            className={`flex items-center gap-2 px-4 py-2 rounded-lg border ${getStatusBgColor(status)}`}
          >
            {getStatusIcon(status)}
            <span className={`font-semibold ${getStatusColor(status)}`}>
              {getStatusText(status)}
            </span>
          </div>
          
          <div className="flex items-center gap-2 text-neutral-400">
            <Clock size={18} />
            <span className="text-2xl font-bold text-white">
              {formatDuration(timeline.duration_ms)}
            </span>
          </div>
        </div>

        <div className="text-xs text-neutral-500 font-mono">
          {timeline.run_id}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="bg-[#141414] rounded-lg border border-neutral-800 p-4 flex items-center gap-4">
          <div className="p-3 rounded-lg bg-purple-500/10 border border-purple-500/20">
            <Bot size={24} className="text-purple-400" />
          </div>
          <div>
            <div className="text-2xl font-bold text-white">{modelCalls}</div>
            <div className="text-sm text-neutral-400">Model Calls</div>
          </div>
        </div>

        <div className="bg-[#141414] rounded-lg border border-neutral-800 p-4 flex items-center gap-4">
          <div className="p-3 rounded-lg bg-orange-500/10 border border-orange-500/20">
            <Wrench size={24} className="text-orange-400" />
          </div>
          <div>
            <div className="text-2xl font-bold text-white">{toolCalls}</div>
            <div className="text-sm text-neutral-400">Tool Calls</div>
          </div>
        </div>

        <div className="bg-[#141414] rounded-lg border border-neutral-800 p-4 flex items-center gap-4">
          <div className="p-3 rounded-lg bg-cyan-500/10 border border-cyan-500/20">
            <Image size={24} className="text-cyan-400" />
          </div>
          <div>
            <div className="text-2xl font-bold text-white">{allArtifacts.length}</div>
            <div className="text-sm text-neutral-400">Artifacts</div>
          </div>
        </div>
      </div>

      {lastAIResponse && (
        <div className="space-y-2">
          <div className="text-sm font-medium text-neutral-400">Final Conclusion</div>
          <div className="bg-[#141414] rounded-lg border border-neutral-800 p-4 max-h-48 overflow-y-auto">
            <p className="text-sm text-neutral-300 whitespace-pre-wrap leading-relaxed">
              {lastAIResponse}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
