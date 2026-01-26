import { useState, useMemo, useCallback, useRef } from 'react';
import { AlertTriangle } from 'lucide-react';
import type { WorkflowTimeline, WorkflowTraceItem, WorkflowArtifact } from '../../../types';
import { TraceItem } from './TraceItem';
import { DetailPanel, type SelectedNode } from './DetailPanel';

interface TimelineViewProps {
  timeline: WorkflowTimeline;
  selectedSymbol: string | null;
  uniqueSymbols?: string[];
  onSymbolSelect?: (symbol: string | null) => void;
}

interface FlatTraceItem {
  trace: WorkflowTraceItem;
  depth: number;
  parentId?: string;
}

function collectAllTraceIds(traces: WorkflowTraceItem[]): string[] {
  const ids: string[] = [];
  for (const trace of traces) {
    ids.push(trace.trace_id);
    if (trace.children && trace.children.length > 0) {
      ids.push(...collectAllTraceIds(trace.children));
    }
  }
  return ids;
}

function collectAllArtifacts(traces: WorkflowTraceItem[]): WorkflowArtifact[] {
  const artifacts: WorkflowArtifact[] = [];
  for (const trace of traces) {
    artifacts.push(...trace.artifacts);
    if (trace.children && trace.children.length > 0) {
      artifacts.push(...collectAllArtifacts(trace.children));
    }
  }
  return artifacts;
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function collectErrorPathIds(traces: WorkflowTraceItem[]): string[] {
  const ids: string[] = [];
  
  function traverse(traceList: WorkflowTraceItem[]): boolean {
    let hasErrorInChildren = false;
    for (const trace of traceList) {
      const childHasError = trace.children && trace.children.length > 0 
        ? traverse(trace.children) 
        : false;
      
      if (trace.status === 'error' || childHasError) {
        ids.push(trace.trace_id);
        hasErrorInChildren = true;
      }
    }
    return hasErrorInChildren;
  }
  
  traverse(traces);
  return ids;
}

function findFirstErrorTrace(traces: WorkflowTraceItem[]): WorkflowTraceItem | null {
  for (const trace of traces) {
    if (trace.status === 'error') return trace;
    if (trace.children && trace.children.length > 0) {
      const found = findFirstErrorTrace(trace.children);
      if (found) return found;
    }
  }
  return null;
}

function flattenTraces(
  traces: WorkflowTraceItem[], 
  expandedTraces: Set<string>, 
  depth: number = 0,
  parentId?: string
): FlatTraceItem[] {
  const result: FlatTraceItem[] = [];
  
  for (const trace of traces) {
    result.push({ trace, depth, parentId });
    
    if (expandedTraces.has(trace.trace_id) && trace.children && trace.children.length > 0) {
      result.push(...flattenTraces(trace.children, expandedTraces, depth + 1, trace.trace_id));
    }
  }
  
  return result;
}

function hasAnyError(traces: WorkflowTraceItem[]): boolean {
  for (const trace of traces) {
    if (trace.status === 'error') return true;
    if (trace.children && trace.children.length > 0) {
      if (hasAnyError(trace.children)) return true;
    }
  }
  return false;
}

export function TimelineView({ timeline, selectedSymbol, uniqueSymbols, onSymbolSelect }: TimelineViewProps) {
  const errorPathIds = useMemo(() => collectErrorPathIds(timeline.traces), [timeline.traces]);
  
  const initialExpanded = useMemo(() => {
    return errorPathIds.length > 0 ? new Set(errorPathIds) : new Set<string>();
  }, [errorPathIds]);
  
  const [expandedTraces, setExpandedTraces] = useState<Set<string>>(initialExpanded);
  const [selectedNode, setSelectedNode] = useState<SelectedNode>(null);
  const [focusedTraceId, setFocusedTraceId] = useState<string | null>(null);
  
  const timelineContainerRef = useRef<HTMLDivElement>(null);
  const traceRefs = useRef<Map<string, HTMLDivElement>>(new Map());

  const toggleTrace = useCallback((traceId: string) => {
    setExpandedTraces((prev) => {
      const next = new Set(prev);
      if (next.has(traceId)) {
        next.delete(traceId);
      } else {
        next.add(traceId);
      }
      return next;
    });
  }, []);

  const allTraceIds = useMemo(() => collectAllTraceIds(timeline.traces), [timeline.traces]);
  const allArtifacts = useMemo(() => collectAllArtifacts(timeline.traces), [timeline.traces]);
  const hasErrors = useMemo(() => hasAnyError(timeline.traces), [timeline.traces]);
  
  const flatTraces = useMemo(
    () => flattenTraces(timeline.traces, expandedTraces),
    [timeline.traces, expandedTraces]
  );

  const isSuccess = timeline.status === 'completed' || timeline.status === 'success';

  const expandAll = useCallback(() => {
    setExpandedTraces(new Set(allTraceIds));
  }, [allTraceIds]);

  const collapseAll = useCallback(() => {
    setExpandedTraces(new Set());
  }, []);

  const jumpToError = useCallback(() => {
    const firstErrorTrace = findFirstErrorTrace(timeline.traces);
    if (firstErrorTrace) {
      const pathIds = collectErrorPathIds(timeline.traces);
      setExpandedTraces((prev) => {
        const next = new Set(prev);
        pathIds.forEach((id) => next.add(id));
        return next;
      });
      
      setSelectedNode({ type: 'trace', data: firstErrorTrace });
      setFocusedTraceId(firstErrorTrace.trace_id);
      
      setTimeout(() => {
        const traceElement = traceRefs.current.get(firstErrorTrace.trace_id);
        if (traceElement) {
          traceElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      }, 100);
    }
  }, [timeline.traces]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (flatTraces.length === 0) return;
    
    const currentIndex = focusedTraceId 
      ? flatTraces.findIndex((item) => item.trace.trace_id === focusedTraceId)
      : -1;
    
    switch (e.key) {
      case 'ArrowDown': {
        e.preventDefault();
        const nextIndex = currentIndex < flatTraces.length - 1 ? currentIndex + 1 : 0;
        const nextTrace = flatTraces[nextIndex];
        setFocusedTraceId(nextTrace.trace.trace_id);
        const traceElement = traceRefs.current.get(nextTrace.trace.trace_id);
        if (traceElement) {
          traceElement.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
        break;
      }
      case 'ArrowUp': {
        e.preventDefault();
        const prevIndex = currentIndex > 0 ? currentIndex - 1 : flatTraces.length - 1;
        const prevTrace = flatTraces[prevIndex];
        setFocusedTraceId(prevTrace.trace.trace_id);
        const traceElement = traceRefs.current.get(prevTrace.trace.trace_id);
        if (traceElement) {
          traceElement.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
        break;
      }
      case 'ArrowRight': {
        e.preventDefault();
        if (focusedTraceId && !expandedTraces.has(focusedTraceId)) {
          const currentTrace = flatTraces.find((item) => item.trace.trace_id === focusedTraceId);
          if (currentTrace && currentTrace.trace.children?.length > 0) {
            toggleTrace(focusedTraceId);
          }
        }
        break;
      }
      case 'ArrowLeft': {
        e.preventDefault();
        if (focusedTraceId && expandedTraces.has(focusedTraceId)) {
          toggleTrace(focusedTraceId);
        }
        break;
      }
      case 'Enter': {
        e.preventDefault();
        if (focusedTraceId) {
          const currentTrace = flatTraces.find((item) => item.trace.trace_id === focusedTraceId);
          if (currentTrace) {
            setSelectedNode({ type: 'trace', data: currentTrace.trace });
          }
        }
        break;
      }
    }
  }, [flatTraces, focusedTraceId, expandedTraces, toggleTrace]);

  const registerTraceRef = useCallback((traceId: string, element: HTMLDivElement | null) => {
    if (element) {
      traceRefs.current.set(traceId, element);
    } else {
      traceRefs.current.delete(traceId);
    }
  }, []);

  const totalDuration = timeline.duration_ms || 1;

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
          {timeline.traces.map((trace) => (
            <TraceItem
              key={trace.trace_id}
              trace={trace}
              totalDuration={totalDuration}
              expandedTraces={expandedTraces}
              toggleTrace={toggleTrace}
              selectedSymbol={selectedSymbol}
              selectedNode={selectedNode}
              onSelectNode={setSelectedNode}
              allArtifacts={allArtifacts}
              focusedTraceId={focusedTraceId}
              onFocusTrace={setFocusedTraceId}
              registerTraceRef={registerTraceRef}
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
