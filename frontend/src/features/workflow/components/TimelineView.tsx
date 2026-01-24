import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import { AlertTriangle } from 'lucide-react';
import type { WorkflowTimeline, WorkflowSpan, WorkflowArtifact } from '../../../types';
import { SpanItem } from './SpanItem';
import { DetailPanel, type SelectedNode } from './DetailPanel';

interface TimelineViewProps {
  timeline: WorkflowTimeline;
  selectedSymbol: string | null;
  uniqueSymbols?: string[];
  onSymbolSelect?: (symbol: string | null) => void;
}

interface FlatSpanItem {
  span: WorkflowSpan;
  depth: number;
  parentId?: string;
}

/**
 * 收集所有 span ID
 * @param spans - 工作流 span 列表
 * @returns span ID 数组
 */
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

/**
 * 收集所有 artifacts
 * @param spans - 工作流 span 列表
 * @returns artifacts 数组
 */
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

/**
 * 格式化持续时间
 * @param ms - 毫秒数
 * @returns 格式化后的时间字符串
 */
function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/**
 * 收集所有包含错误的 span 路径（需要展开的 span ID）
 * @param spans - 工作流 span 列表
 * @returns 需要展开的 span ID 集合
 */
function collectErrorPathIds(spans: WorkflowSpan[]): string[] {
  const ids: string[] = [];
  
  function traverse(spanList: WorkflowSpan[]): boolean {
    let hasErrorInChildren = false;
    for (const span of spanList) {
      const childHasError = span.nested_spans && span.nested_spans.length > 0 
        ? traverse(span.nested_spans) 
        : false;
      
      if (span.status === 'error' || childHasError) {
        ids.push(span.span_id);
        hasErrorInChildren = true;
      }
    }
    return hasErrorInChildren;
  }
  
  traverse(spans);
  return ids;
}

/**
 * 查找第一个错误 span
 * @param spans - 工作流 span 列表
 * @returns 第一个错误 span 或 null
 */
function findFirstErrorSpan(spans: WorkflowSpan[]): WorkflowSpan | null {
  for (const span of spans) {
    if (span.status === 'error') return span;
    if (span.nested_spans && span.nested_spans.length > 0) {
      const found = findFirstErrorSpan(span.nested_spans);
      if (found) return found;
    }
  }
  return null;
}

/**
 * 将嵌套的 span 结构扁平化为列表（用于键盘导航）
 * @param spans - 工作流 span 列表
 * @param expandedSpans - 已展开的 span ID 集合
 * @param depth - 当前深度
 * @param parentId - 父 span ID
 * @returns 扁平化的 span 列表
 */
function flattenSpans(
  spans: WorkflowSpan[], 
  expandedSpans: Set<string>, 
  depth: number = 0,
  parentId?: string
): FlatSpanItem[] {
  const result: FlatSpanItem[] = [];
  
  for (const span of spans) {
    result.push({ span, depth, parentId });
    
    if (expandedSpans.has(span.span_id) && span.nested_spans && span.nested_spans.length > 0) {
      result.push(...flattenSpans(span.nested_spans, expandedSpans, depth + 1, span.span_id));
    }
  }
  
  return result;
}

/**
 * 检查是否存在任何错误 span
 * @param spans - 工作流 span 列表
 * @returns 是否存在错误
 */
function hasAnyError(spans: WorkflowSpan[]): boolean {
  for (const span of spans) {
    if (span.status === 'error') return true;
    if (span.nested_spans && span.nested_spans.length > 0) {
      if (hasAnyError(span.nested_spans)) return true;
    }
  }
  return false;
}

export function TimelineView({ timeline, selectedSymbol, uniqueSymbols, onSymbolSelect }: TimelineViewProps) {
  const [expandedSpans, setExpandedSpans] = useState<Set<string>>(new Set());
  const [selectedNode, setSelectedNode] = useState<SelectedNode>(null);
  const [focusedSpanId, setFocusedSpanId] = useState<string | null>(null);
  
  const timelineContainerRef = useRef<HTMLDivElement>(null);
  const spanRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const hasAutoExpandedRef = useRef(false);

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
  const errorPathIds = useMemo(() => collectErrorPathIds(timeline.spans), [timeline.spans]);
  const hasErrors = useMemo(() => hasAnyError(timeline.spans), [timeline.spans]);
  
  const flatSpans = useMemo(
    () => flattenSpans(timeline.spans, expandedSpans),
    [timeline.spans, expandedSpans]
  );

  const isSuccess = timeline.status === 'completed' || timeline.status === 'success';

  useEffect(() => {
    if (!hasAutoExpandedRef.current && errorPathIds.length > 0) {
      setExpandedSpans(new Set(errorPathIds));
      hasAutoExpandedRef.current = true;
    }
  }, [errorPathIds]);

  const expandAll = useCallback(() => {
    setExpandedSpans(new Set(allSpanIds));
  }, [allSpanIds]);

  const collapseAll = useCallback(() => {
    setExpandedSpans(new Set());
  }, []);

  const jumpToError = useCallback(() => {
    const firstErrorSpan = findFirstErrorSpan(timeline.spans);
    if (firstErrorSpan) {
      const pathIds = collectErrorPathIds(timeline.spans);
      setExpandedSpans((prev) => {
        const next = new Set(prev);
        pathIds.forEach((id) => next.add(id));
        return next;
      });
      
      setSelectedNode({ type: 'span', data: firstErrorSpan });
      setFocusedSpanId(firstErrorSpan.span_id);
      
      setTimeout(() => {
        const spanElement = spanRefs.current.get(firstErrorSpan.span_id);
        if (spanElement) {
          spanElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      }, 100);
    }
  }, [timeline.spans]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (flatSpans.length === 0) return;
    
    const currentIndex = focusedSpanId 
      ? flatSpans.findIndex((item) => item.span.span_id === focusedSpanId)
      : -1;
    
    switch (e.key) {
      case 'ArrowDown': {
        e.preventDefault();
        const nextIndex = currentIndex < flatSpans.length - 1 ? currentIndex + 1 : 0;
        const nextSpan = flatSpans[nextIndex];
        setFocusedSpanId(nextSpan.span.span_id);
        const spanElement = spanRefs.current.get(nextSpan.span.span_id);
        if (spanElement) {
          spanElement.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
        break;
      }
      case 'ArrowUp': {
        e.preventDefault();
        const prevIndex = currentIndex > 0 ? currentIndex - 1 : flatSpans.length - 1;
        const prevSpan = flatSpans[prevIndex];
        setFocusedSpanId(prevSpan.span.span_id);
        const spanElement = spanRefs.current.get(prevSpan.span.span_id);
        if (spanElement) {
          spanElement.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
        break;
      }
      case 'ArrowRight': {
        e.preventDefault();
        if (focusedSpanId && !expandedSpans.has(focusedSpanId)) {
          const currentSpan = flatSpans.find((item) => item.span.span_id === focusedSpanId);
          if (currentSpan && (currentSpan.span.nested_spans?.length > 0 || currentSpan.span.children.length > 0)) {
            toggleSpan(focusedSpanId);
          }
        }
        break;
      }
      case 'ArrowLeft': {
        e.preventDefault();
        if (focusedSpanId && expandedSpans.has(focusedSpanId)) {
          toggleSpan(focusedSpanId);
        }
        break;
      }
      case 'Enter': {
        e.preventDefault();
        if (focusedSpanId) {
          const currentSpan = flatSpans.find((item) => item.span.span_id === focusedSpanId);
          if (currentSpan) {
            setSelectedNode({ type: 'span', data: currentSpan.span });
          }
        }
        break;
      }
    }
  }, [flatSpans, focusedSpanId, expandedSpans, toggleSpan]);

  const registerSpanRef = useCallback((spanId: string, element: HTMLDivElement | null) => {
    if (element) {
      spanRefs.current.set(spanId, element);
    } else {
      spanRefs.current.delete(spanId);
    }
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
    <div 
      className="flex flex-col lg:flex-row h-[calc(100vh-140px)] min-h-[600px] bg-[#141414] rounded-lg overflow-hidden border border-neutral-800"
      onKeyDown={handleKeyDown}
      tabIndex={0}
    >
      <div className="w-full lg:w-[380px] flex-shrink-0 border-b lg:border-b-0 lg:border-r border-neutral-800 flex flex-col overflow-x-auto">
        <div className="flex items-center gap-2 p-2 border-b border-neutral-800 bg-[#1a1a1a]">
          <div className="flex items-center gap-2 flex-shrink-0">
            <span 
              className={`w-2 h-2 rounded-full ${isSuccess ? 'bg-green-500' : 'bg-red-500'}`}
              title={isSuccess ? 'Success' : 'Error'}
            />
            <span className="text-xs text-neutral-400">
              {formatDuration(totalDuration)}
            </span>
          </div>

          {uniqueSymbols && uniqueSymbols.length > 0 && onSymbolSelect ? (
            <div className="flex items-center gap-1 flex-1 min-w-0 overflow-x-auto border-l border-neutral-700 pl-2 ml-1">
              <button
                onClick={() => onSymbolSelect(null)}
                className={`px-2 py-1 text-xs rounded border transition-all duration-200 whitespace-nowrap flex-shrink-0 ${
                  selectedSymbol === null
                    ? 'bg-neutral-800 border-neutral-700 text-neutral-300'
                    : 'border-neutral-700 text-neutral-400 hover:text-neutral-300'
                }`}
              >
                All
              </button>
              {uniqueSymbols.map((symbol) => (
                <button
                  key={symbol}
                  onClick={() => onSymbolSelect(symbol)}
                  className={`px-2 py-1 text-xs rounded border transition-all duration-200 whitespace-nowrap flex-shrink-0 ${
                    selectedSymbol === symbol
                      ? 'bg-neutral-800 border-neutral-700 text-neutral-300'
                      : 'border-neutral-700 text-neutral-400 hover:text-neutral-300'
                  }`}
                >
                  {symbol}
                </button>
              ))}
            </div>
          ) : <div className="flex-1" />}

          <div className="flex gap-1 flex-shrink-0">
            {hasErrors && (
              <button
                onClick={jumpToError}
                className="px-2 py-1 text-xs border border-neutral-700 bg-neutral-800 hover:bg-neutral-700 rounded text-red-400 transition-all duration-200 whitespace-nowrap flex items-center gap-1"
                title="Jump to first error"
              >
                <AlertTriangle size={12} />
                Error
              </button>
            )}
            <button
              onClick={expandAll}
              className="px-2 py-1 text-xs border border-neutral-700 bg-neutral-800 hover:bg-neutral-700 rounded text-neutral-400 transition-all duration-200 whitespace-nowrap"
            >
              Expand
            </button>
            <button
              onClick={collapseAll}
              className="px-2 py-1 text-xs border border-neutral-700 bg-neutral-800 hover:bg-neutral-700 rounded text-neutral-400 transition-all duration-200 whitespace-nowrap"
            >
              Collapse
            </button>
          </div>
        </div>

        <div 
          ref={timelineContainerRef}
          className="flex-1 overflow-y-auto p-2 bg-[#141414]"
        >
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
              focusedSpanId={focusedSpanId}
              onFocusSpan={setFocusedSpanId}
              registerSpanRef={registerSpanRef}
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
