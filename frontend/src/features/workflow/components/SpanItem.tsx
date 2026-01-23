import { useMemo } from 'react';
import { 
  Workflow, 
  ChevronRight, 
  ChevronDown, 
  CheckCircle2, 
  XCircle, 
  Loader2,
  Clock
} from 'lucide-react';
import type { WorkflowSpan, WorkflowSpanChild, WorkflowArtifact } from '../../../types';
import { formatDuration } from '../../../utils';
import { getNodeDisplayName } from '../utils/workflowHelpers';
import { ChildItem } from './ChildItem';
import type { SelectedNode } from './DetailPanel';

interface SpanItemProps {
  span: WorkflowSpan;
  totalDuration: number;
  startOffset: number;
  depth?: number;
  expandedSpans: Set<string>;
  toggleSpan: (spanId: string) => void;
  selectedSymbol: string | null;
  timelineStartTime?: number;
  selectedNode: SelectedNode;
  onSelectNode: (node: SelectedNode) => void;
  allArtifacts: WorkflowArtifact[];
}

export function SpanItem({
  span,
  totalDuration,
  // startOffset, // 暂时未使用
  depth = 0,
  expandedSpans,
  toggleSpan,
  selectedSymbol,
  // timelineStartTime, // 暂时未使用
  selectedNode,
  onSelectNode,
  allArtifacts,
}: SpanItemProps) {
  const isExpanded = expandedSpans.has(span.span_id);
  const hasChildren = span.children.length > 0 || span.artifacts.length > 0;
  const hasNestedSpans = span.nested_spans && span.nested_spans.length > 0;
  const isExpandable = hasChildren || hasNestedSpans;

  const isFiltered = selectedSymbol && span.symbol && span.symbol !== selectedSymbol;

  // 合并模型调用的逻辑
  const mergedChildren = useMemo(() => {
    const children = span.children || [];
    
    // 重新实现的 clean 版本
    const cleanResult: (WorkflowSpanChild | { type: 'model_call_group', before: WorkflowSpanChild, after?: WorkflowSpanChild, children: WorkflowSpanChild[] })[] = [];
    const processedIndices = new Set<number>();
    
    for (let idx = 0; idx < children.length; idx++) {
      if (processedIndices.has(idx)) continue;
      
      const child = children[idx];
      const payload = child.payload as Record<string, unknown> | undefined;
      
      if (child.type === 'model_call' && payload?.phase === 'before') {
        const modelSpanId = payload.model_span_id;
        let afterIdx = -1;
        
        for (let k = idx + 1; k < children.length; k++) {
          const nextChild = children[k];
          const nextPayload = nextChild.payload as Record<string, unknown> | undefined;
          if (nextChild.type === 'model_call' && nextPayload?.phase === 'after' && nextPayload?.model_span_id === modelSpanId) {
            afterIdx = k;
            break;
          }
        }
        
        if (afterIdx !== -1) {
          processedIndices.add(afterIdx);
          cleanResult.push({
            type: 'model_call_group',
            before: child,
            after: children[afterIdx],
            children: []
          });
        } else {
          // 只有 before 没有 after
          cleanResult.push({
            type: 'model_call_group',
            before: child,
            children: []
          });
        }
      } else if (child.type === 'model_call' && payload?.phase === 'after') {
        // 孤立的 after（理论上不应该发生，除非 before 丢失）
        // 忽略或显示
      } else {
        cleanResult.push(child);
      }
    }
    
    return cleanResult;
  }, [span.children]);

  if (isFiltered) return null;

  const isSelected = selectedNode?.type === 'span' && selectedNode.data.span_id === span.span_id;

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'success': return <CheckCircle2 size={14} className="text-emerald-500" />;
      case 'error': return <XCircle size={14} className="text-red-500" />;
      case 'running': return <Loader2 size={14} className="text-blue-500 animate-spin" />;
      default: return <div className="w-3.5 h-3.5 rounded-full bg-zinc-700" />;
    }
  };

  return (
    <div className="select-none">
      <div
        className={`flex items-center gap-2 py-1.5 px-2 rounded cursor-pointer transition-colors group ${
          isSelected ? 'bg-zinc-800 border-l-2 border-blue-500' : 'hover:bg-zinc-900 border-l-2 border-transparent'
        }`}
        style={{ paddingLeft: `${depth * 12 + 8}px` }}
        onClick={(e) => {
          e.stopPropagation();
          onSelectNode({ type: 'span', data: span });
          if (isExpandable && !isExpanded) toggleSpan(span.span_id);
        }}
      >
        <div 
          className="flex-shrink-0 w-4 h-4 flex items-center justify-center text-zinc-500 hover:text-zinc-300"
          onClick={(e) => {
            e.stopPropagation();
            if (isExpandable) toggleSpan(span.span_id);
          }}
        >
          {isExpandable ? (
            isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />
          ) : <div className="w-4" />}
        </div>

        <div className="flex items-center gap-2 flex-1 min-w-0">
          <Workflow size={14} className="text-zinc-400" />
          <span className={`text-sm font-medium truncate ${isSelected ? 'text-zinc-100' : 'text-zinc-300'}`}>
            {getNodeDisplayName(span.node)}
          </span>
          {span.symbol && (
            <span className="px-1.5 py-0.5 text-[10px] rounded bg-zinc-800 text-zinc-400 border border-zinc-700">
              {span.symbol}
            </span>
          )}
        </div>

        <div className="flex items-center gap-3">
          {span.duration_ms && (
            <span className="text-xs text-zinc-500 flex items-center gap-1">
              <Clock size={10} />
              {formatDuration(span.duration_ms)}
            </span>
          )}
          {getStatusIcon(span.status)}
        </div>
      </div>

      {isExpanded && isExpandable && (
        <div>
          {hasNestedSpans && (
            <div>
              {span.nested_spans.map((nestedSpan) => {
                // 计算相对时间偏移用于显示（如果需要）
                // const nestedStartTime = nestedSpan.start_time
                //   ? new Date(nestedSpan.start_time).getTime()
                //   : 0;
                // const baseTime = timelineStartTime || (span.start_time ? new Date(span.start_time).getTime() : 0);
                // const nestedOffset = nestedStartTime - baseTime;

                return (
                  <SpanItem
                    key={nestedSpan.span_id}
                    span={nestedSpan}
                    totalDuration={totalDuration}
                    startOffset={0} // 暂时未使用
                    depth={depth + 1}
                    expandedSpans={expandedSpans}
                    toggleSpan={toggleSpan}
                    selectedSymbol={selectedSymbol}
                    // timelineStartTime={timelineStartTime} // 暂时未使用
                    selectedNode={selectedNode}
                    onSelectNode={onSelectNode}
                    allArtifacts={allArtifacts}
                  />
                );
              })}
            </div>
          )}

          <div className="flex flex-col relative">
            {/* Tree line */}
            <div 
              className="absolute top-0 bottom-0 border-l border-zinc-800" 
              style={{ left: `${depth * 12 + 15}px` }} 
            />
            
            {mergedChildren.map((child, idx) => (
              <ChildItem 
                key={idx} 
                child={child} 
                depth={depth + 1}
                allArtifacts={allArtifacts}
                selectedNode={selectedNode}
                onSelectNode={onSelectNode}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
