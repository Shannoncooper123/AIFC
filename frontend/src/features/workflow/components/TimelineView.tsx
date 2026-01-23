import { useState, useMemo, useCallback } from 'react';
import type { WorkflowTimeline, WorkflowSpan, WorkflowArtifact } from '../../../types';
import { SpanItem } from './SpanItem';
import { DetailPanel, type SelectedNode } from './DetailPanel';

interface TimelineViewProps {
  timeline: WorkflowTimeline;
  selectedSymbol: string | null;
}

function collectAllSpanIds(spans: WorkflowSpan[]): string[] {
  const ids: string[] = [];
  for (const span of spans) {
    ids.push(span.span_id);
    if (span.nested_spans && span.nested_spans.length > 0) {
      ids.push(...collectAllSpanIds(span.nested_spans));
    }
  }
  return ids;
}

function collectAllArtifacts(spans: WorkflowSpan[]): WorkflowArtifact[] {
  const artifacts: WorkflowArtifact[] = [];
  for (const span of spans) {
    artifacts.push(...span.artifacts);
    if (span.nested_spans && span.nested_spans.length > 0) {
      artifacts.push(...collectAllArtifacts(span.nested_spans));
    }
  }
  return artifacts;
}

export function TimelineView({ timeline, selectedSymbol }: TimelineViewProps) {
  const [expandedSpans, setExpandedSpans] = useState<Set<string>>(new Set());
  const [selectedNode, setSelectedNode] = useState<SelectedNode>(null);

  const toggleSpan = useCallback((spanId: string) => {
    setExpandedSpans((prev) => {
      const next = new Set(prev);
      if (next.has(spanId)) {
        next.delete(spanId);
      } else {
        next.add(spanId);
      }
      return next;
    });
  }, []);

  const allSpanIds = useMemo(() => collectAllSpanIds(timeline.spans), [timeline.spans]);
  const allArtifacts = useMemo(() => collectAllArtifacts(timeline.spans), [timeline.spans]);

  const expandAll = useCallback(() => {
    setExpandedSpans(new Set(allSpanIds));
  }, [allSpanIds]);

  const collapseAll = useCallback(() => {
    setExpandedSpans(new Set());
  }, []);

  const totalDuration = timeline.duration_ms || 1;
  const timelineStartTime = timeline.start_time
    ? new Date(timeline.start_time).getTime()
    : undefined;

  const spansWithOffset = useMemo(() => {
    if (!timeline.start_time)
      return timeline.spans.map((s) => ({ span: s, offset: 0 }));

    const startTime = new Date(timeline.start_time).getTime();
    return timeline.spans.map((span) => {
      const spanStart = span.start_time
        ? new Date(span.start_time).getTime()
        : startTime;
      return {
        span,
        offset: spanStart - startTime,
      };
    });
  }, [timeline]);

  return (
    <div className="flex h-[calc(100vh-200px)] min-h-[500px] bg-zinc-950 rounded-lg overflow-hidden border border-zinc-800">
      <div className="w-[420px] flex-shrink-0 border-r border-zinc-800 flex flex-col">
        <div className="flex justify-end p-2 border-b border-zinc-800 bg-zinc-900/50">
          <div className="flex gap-1">
            <button
              onClick={expandAll}
              className="px-2 py-1 text-xs bg-zinc-800 hover:bg-zinc-700 rounded text-zinc-300 transition-colors"
            >
              Expand All
            </button>
            <button
              onClick={collapseAll}
              className="px-2 py-1 text-xs bg-zinc-800 hover:bg-zinc-700 rounded text-zinc-300 transition-colors"
            >
              Collapse All
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-2 bg-zinc-950">
          {spansWithOffset.map(({ span, offset }) => (
            <SpanItem
              key={span.span_id}
              span={span}
              totalDuration={totalDuration}
              startOffset={offset}
              expandedSpans={expandedSpans}
              toggleSpan={toggleSpan}
              selectedSymbol={selectedSymbol}
              timelineStartTime={timelineStartTime}
              selectedNode={selectedNode}
              onSelectNode={setSelectedNode}
              allArtifacts={allArtifacts}
            />
          ))}
        </div>
      </div>

      <div className="flex-1 bg-zinc-900 overflow-hidden">
        <DetailPanel selectedNode={selectedNode} />
      </div>
    </div>
  );
}
