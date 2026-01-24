import { useState, useMemo, useCallback } from 'react';
import type { WorkflowTimeline, WorkflowSpan, WorkflowArtifact } from '../../../types';
import { SpanItem } from './SpanItem';
import { DetailPanel, type SelectedNode } from './DetailPanel';

interface TimelineViewProps {
  timeline: WorkflowTimeline;
  selectedSymbol: string | null;
  uniqueSymbols?: string[];
  onSymbolSelect?: (symbol: string | null) => void;
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

export function TimelineView({ timeline, selectedSymbol, uniqueSymbols, onSymbolSelect }: TimelineViewProps) {
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
    <div className="flex flex-col lg:flex-row h-[calc(100vh-200px)] min-h-[500px] bg-[#141414] rounded-lg overflow-hidden border border-neutral-800">
      <div className="w-full lg:w-[420px] h-1/2 lg:h-full flex-shrink-0 border-b lg:border-b-0 lg:border-r border-neutral-800 flex flex-col">
        <div className="flex items-center gap-2 p-2 border-b border-neutral-800 bg-[#1a1a1a]">
          {uniqueSymbols && uniqueSymbols.length > 0 && onSymbolSelect ? (
            <div className="flex items-center gap-2 flex-1 min-w-0 overflow-x-auto">
              <span className="text-xs text-neutral-500 flex-shrink-0">筛选:</span>
              <div className="flex gap-1 flex-nowrap">
                <button
                  onClick={() => onSymbolSelect(null)}
                  className={`px-2 py-1 text-xs rounded border transition-all duration-200 whitespace-nowrap flex-shrink-0 ${
                    selectedSymbol === null
                      ? 'bg-neutral-700/50 border-neutral-500 text-white'
                      : 'border-neutral-700 text-neutral-400 hover:border-neutral-600'
                  }`}
                >
                  全部
                </button>
                {uniqueSymbols.map((symbol) => (
                  <button
                    key={symbol}
                    onClick={() => onSymbolSelect(symbol)}
                    className={`px-2 py-1 text-xs rounded border transition-all duration-200 whitespace-nowrap flex-shrink-0 ${
                      selectedSymbol === symbol
                        ? 'bg-neutral-700/50 border-neutral-500 text-white'
                        : 'border-neutral-700 text-neutral-400 hover:border-neutral-600'
                    }`}
                  >
                    {symbol}
                  </button>
                ))}
              </div>
            </div>
          ) : <div className="flex-1" />}
          <div className="flex gap-1 flex-shrink-0">
            <button
              onClick={expandAll}
              className="px-2 py-1 text-xs bg-neutral-800 hover:bg-neutral-700 rounded text-neutral-300 transition-all duration-200 whitespace-nowrap"
            >
              Expand
            </button>
            <button
              onClick={collapseAll}
              className="px-2 py-1 text-xs bg-neutral-800 hover:bg-neutral-700 rounded text-neutral-300 transition-all duration-200 whitespace-nowrap"
            >
              Collapse
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto overflow-x-auto p-2 bg-[#141414]">
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

      <div className="flex-1 bg-[#1a1a1a] overflow-hidden">
        <DetailPanel selectedNode={selectedNode} allArtifacts={allArtifacts} />
      </div>
    </div>
  );
}
