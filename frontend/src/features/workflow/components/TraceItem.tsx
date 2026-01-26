import { useMemo } from 'react';
import { 
  ChevronRight, 
  ChevronDown, 
  CheckCircle2, 
  XCircle, 
  Loader2,
  Workflow,
  Box,
  Bot,
  Brain,
  Wrench,
  Image,
  Circle,
} from 'lucide-react';
import type { WorkflowTraceItem, WorkflowArtifact, TraceType } from '../../../types';
import { formatDuration } from '../../../utils';
import { getNodeDisplayName, getTraceTypeColor } from '../utils/workflowHelpers';
import type { SelectedNode } from './DetailPanel';

interface TraceItemProps {
  trace: WorkflowTraceItem;
  totalDuration: number;
  depth?: number;
  expandedTraces: Set<string>;
  toggleTrace: (traceId: string) => void;
  selectedSymbol: string | null;
  selectedNode: SelectedNode;
  onSelectNode: (node: SelectedNode) => void;
  allArtifacts: WorkflowArtifact[];
  focusedTraceId?: string | null;
  onFocusTrace?: (traceId: string) => void;
  registerTraceRef?: (traceId: string, element: HTMLDivElement | null) => void;
}

const getStatusBorderColor = (status: string | undefined) => {
  switch (status) {
    case 'success': return 'border-l-emerald-500/50';
    case 'error': return 'border-l-rose-500/50';
    case 'running': return 'border-l-yellow-500/50';
    default: return 'border-l-transparent';
  }
};

const truncateError = (error: string | undefined, maxLength: number = 50): string => {
  if (!error) return '';
  return error.length > maxLength ? `${error.slice(0, maxLength)}...` : error;
};

const getTraceIcon = (type: TraceType) => {
  const iconProps = { size: 14 };
  switch (type) {
    case 'workflow': return <Workflow {...iconProps} />;
    case 'node': return <Box {...iconProps} />;
    case 'agent': return <Bot {...iconProps} />;
    case 'model_call': return <Brain {...iconProps} />;
    case 'tool_call': return <Wrench {...iconProps} />;
    case 'artifact': return <Image {...iconProps} />;
    default: return <Circle {...iconProps} />;
  }
};

const getStatusIcon = (status: string | undefined) => {
  switch (status) {
    case 'success': return <CheckCircle2 size={14} className="text-emerald-500/60" />;
    case 'error': return <XCircle size={14} className="text-rose-500/60" />;
    case 'running': return <Loader2 size={14} className="text-yellow-500/60 animate-spin" />;
    default: return null;
  }
};

export function TraceItem({
  trace,
  totalDuration,
  depth = 0,
  expandedTraces,
  toggleTrace,
  selectedSymbol,
  selectedNode,
  onSelectNode,
  allArtifacts,
  focusedTraceId,
  onFocusTrace,
  registerTraceRef,
}: TraceItemProps) {
  const isExpanded = expandedTraces.has(trace.trace_id);
  const hasChildren = trace.children.length > 0;
  const isExpandable = hasChildren;

  const isFiltered = selectedSymbol && trace.symbol && trace.symbol !== selectedSymbol;

  const displayName = useMemo(() => {
    if (trace.type === 'node' || trace.type === 'agent') {
      return getNodeDisplayName(trace.name);
    }
    if (trace.type === 'tool_call') {
      return trace.name;
    }
    if (trace.type === 'model_call') {
      const seq = trace.payload?.seq;
      return seq ? `模型调用 #${seq}` : '模型调用';
    }
    return trace.name;
  }, [trace]);

  if (isFiltered) return null;

  const isSelected = selectedNode?.type === 'trace' && selectedNode.data.trace_id === trace.trace_id;
  const isFocused = focusedTraceId === trace.trace_id;

  const iconColorClass = getTraceTypeColor(trace.type);

  return (
    <div 
      className="select-none"
      ref={(el) => registerTraceRef?.(trace.trace_id, el)}
    >
      <div
        className={`flex items-center gap-2 py-1.5 px-2 rounded cursor-pointer transition-all duration-200 group border-l-2 ${getStatusBorderColor(trace.status)} ${
          isSelected ? 'bg-blue-900/20 border-l-neutral-400' : isFocused ? 'bg-neutral-800/50 ring-1 ring-neutral-600' : 'hover:bg-neutral-900'
        }`}
        style={{ paddingLeft: `${depth * 12 + 8}px` }}
        onClick={(e) => {
          e.stopPropagation();
          onSelectNode({ type: 'trace', data: trace });
          onFocusTrace?.(trace.trace_id);
          if (isExpandable && !isExpanded) toggleTrace(trace.trace_id);
        }}
      >
        <div 
          className="flex-shrink-0 w-4 h-4 flex items-center justify-center text-neutral-500 hover:text-neutral-300 transition-all duration-200"
          onClick={(e) => {
            e.stopPropagation();
            if (isExpandable) toggleTrace(trace.trace_id);
          }}
        >
          {isExpandable ? (
            isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />
          ) : <div className="w-4" />}
        </div>

        <div className="flex flex-col flex-1 min-w-0 gap-0.5">
          <div className="flex items-center gap-2">
            <span className={iconColorClass}>
              {getTraceIcon(trace.type)}
            </span>
            <span className={`text-sm font-semibold truncate ${isSelected ? 'text-white' : 'text-neutral-200'}`}>
              {displayName}
            </span>
          </div>
          {trace.symbol && (
            <div className="flex items-center gap-2 pl-6">
              <span className="px-1.5 py-0.5 text-[10px] rounded bg-neutral-800/50 text-neutral-500 border border-neutral-700/50">
                {trace.symbol}
              </span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          {trace.duration_ms != null && trace.duration_ms > 0 && (
            <span className="text-xs text-neutral-500">
              {formatDuration(trace.duration_ms)}
            </span>
          )}
          {getStatusIcon(trace.status)}
        </div>
      </div>

      {trace.status === 'error' && trace.error && (
        <div 
          className="text-xs text-rose-400/80 truncate pl-8 py-0.5"
          style={{ paddingLeft: `${depth * 12 + 32}px` }}
          title={trace.error}
        >
          {truncateError(trace.error)}
        </div>
      )}

      {isExpanded && isExpandable && (
        <div>
          <div className="flex flex-col relative">
            <div 
              className="absolute top-0 bottom-0 border-l border-neutral-700/50" 
              style={{ left: `${depth * 12 + 15}px` }} 
            />
            
            {trace.children.map((childTrace) => (
              <TraceItem
                key={childTrace.trace_id}
                trace={childTrace}
                totalDuration={totalDuration}
                depth={depth + 1}
                expandedTraces={expandedTraces}
                toggleTrace={toggleTrace}
                selectedSymbol={selectedSymbol}
                selectedNode={selectedNode}
                onSelectNode={onSelectNode}
                allArtifacts={allArtifacts}
                focusedTraceId={focusedTraceId}
                onFocusTrace={onFocusTrace}
                registerTraceRef={registerTraceRef}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
