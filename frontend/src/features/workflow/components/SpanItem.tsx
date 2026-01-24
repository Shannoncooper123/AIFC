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
  depth = 0,
  expandedSpans,
  toggleSpan,
  selectedSymbol,
  selectedNode,
  onSelectNode,
  allArtifacts,
}: SpanItemProps) {
  const isExpanded = expandedSpans.has(span.span_id);
  const hasChildren = span.children.length > 0 || span.artifacts.length > 0;
  const hasNestedSpans = span.nested_spans && span.nested_spans.length > 0;
  const isExpandable = hasChildren || hasNestedSpans;

  const isFiltered = selectedSymbol && span.symbol && span.symbol !== selectedSymbol;

  const mergedChildren = useMemo(() => {
    const children = span.children || [];
    if (children.length === 0) return [];
    
    const cleanResult: (WorkflowSpanChild | { type: 'model_call_group', before: WorkflowSpanChild, after?: WorkflowSpanChild, children: WorkflowSpanChild[] })[] = [];
    const processedIndices = new Set<number>();
    
    const modelCallGroups = new Map<string, { before: WorkflowSpanChild; after?: WorkflowSpanChild; children: WorkflowSpanChild[]; beforeIdx: number }>();
    
    for (let idx = 0; idx < children.length; idx++) {
      const child = children[idx];
      const payload = child.payload as Record<string, unknown> | undefined;
      
      if (child.type === 'model_call' && payload?.phase === 'before') {
        const modelSpanId = payload.model_span_id as string;
        if (modelSpanId) {
          modelCallGroups.set(modelSpanId, {
            before: child,
            children: [],
            beforeIdx: idx
          });
          processedIndices.add(idx);
        }
      } else if (child.type === 'model_call' && payload?.phase === 'after') {
        const modelSpanId = payload.model_span_id as string;
        if (modelSpanId && modelCallGroups.has(modelSpanId)) {
          modelCallGroups.get(modelSpanId)!.after = child;
          processedIndices.add(idx);
        }
      }
    }
    
    for (let idx = 0; idx < children.length; idx++) {
      const child = children[idx];
      if (processedIndices.has(idx)) continue;
      
      if (child.type === 'tool_call') {
        const modelSpanId = child.model_span_id || (child.payload as Record<string, unknown> | undefined)?.model_span_id as string;
        
        if (modelSpanId && modelCallGroups.has(modelSpanId)) {
          modelCallGroups.get(modelSpanId)!.children.push(child);
          processedIndices.add(idx);
        } else {
          let foundGroup = false;
          const childTs = child.ts ? new Date(child.ts).getTime() : 0;
          
          const sortedGroupEntries = Array.from(modelCallGroups.entries())
            .sort((a, b) => a[1].beforeIdx - b[1].beforeIdx);
          
          for (let i = sortedGroupEntries.length - 1; i >= 0; i--) {
            const [, group] = sortedGroupEntries[i];
            const beforeTs = group.before.ts ? new Date(group.before.ts).getTime() : 0;
            const afterTs = group.after?.ts ? new Date(group.after.ts).getTime() : Infinity;
            
            if (childTs >= beforeTs && childTs <= afterTs) {
              group.children.push(child);
              processedIndices.add(idx);
              foundGroup = true;
              break;
            }
          }
          
          if (!foundGroup && sortedGroupEntries.length > 0) {
            for (let i = sortedGroupEntries.length - 1; i >= 0; i--) {
              const [, group] = sortedGroupEntries[i];
              const beforeTs = group.before.ts ? new Date(group.before.ts).getTime() : 0;
              
              if (childTs >= beforeTs) {
                group.children.push(child);
                processedIndices.add(idx);
                foundGroup = true;
                break;
              }
            }
          }
        }
      }
    }
    
    const sortedGroups = Array.from(modelCallGroups.entries())
      .sort((a, b) => a[1].beforeIdx - b[1].beforeIdx);
    
    let groupIndex = 0;
    for (let idx = 0; idx < children.length; idx++) {
      if (processedIndices.has(idx)) {
        if (groupIndex < sortedGroups.length && sortedGroups[groupIndex][1].beforeIdx === idx) {
          const [, group] = sortedGroups[groupIndex];
          cleanResult.push({
            type: 'model_call_group',
            before: group.before,
            after: group.after,
            children: group.children
          });
          groupIndex++;
        }
        continue;
      }
      cleanResult.push(children[idx]);
    }
    
    return cleanResult;
  }, [span.children]);

  if (isFiltered) return null;

  const isSelected = selectedNode?.type === 'span' && selectedNode.data.span_id === span.span_id;

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'success': return <CheckCircle2 size={14} className="text-emerald-500/80" />;
      case 'error': return <XCircle size={14} className="text-rose-500/80" />;
      case 'running': return <Loader2 size={14} className="text-neutral-400 animate-spin" />;
      default: return <div className="w-3.5 h-3.5 rounded-full bg-neutral-700" />;
    }
  };

  return (
    <div className="select-none">
      <div
        className={`flex items-center gap-2 py-1.5 px-2 rounded cursor-pointer transition-all duration-200 group ${
          isSelected ? 'bg-neutral-800 border-l-2 border-neutral-400' : 'hover:bg-neutral-900 border-l-2 border-transparent'
        }`}
        style={{ paddingLeft: `${depth * 12 + 8}px` }}
        onClick={(e) => {
          e.stopPropagation();
          onSelectNode({ type: 'span', data: span });
          if (isExpandable && !isExpanded) toggleSpan(span.span_id);
        }}
      >
        <div 
          className="flex-shrink-0 w-4 h-4 flex items-center justify-center text-neutral-500 hover:text-neutral-300 transition-all duration-200"
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
          <Workflow size={14} className="text-neutral-400" />
          <span className={`text-sm font-medium truncate ${isSelected ? 'text-white' : 'text-neutral-300'}`}>
            {getNodeDisplayName(span.node)}
          </span>
          {span.symbol && (
            <span className="px-1.5 py-0.5 text-[10px] rounded bg-neutral-800 text-neutral-400 border border-neutral-700">
              {span.symbol}
            </span>
          )}
        </div>

        <div className="flex items-center gap-3">
          {span.duration_ms && (
            <span className="text-xs text-neutral-500 flex items-center gap-1">
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
                return (
                  <SpanItem
                    key={nestedSpan.span_id}
                    span={nestedSpan}
                    totalDuration={totalDuration}
                    startOffset={0}
                    depth={depth + 1}
                    expandedSpans={expandedSpans}
                    toggleSpan={toggleSpan}
                    selectedSymbol={selectedSymbol}
                    selectedNode={selectedNode}
                    onSelectNode={onSelectNode}
                    allArtifacts={allArtifacts}
                  />
                );
              })}
            </div>
          )}

          <div className="flex flex-col relative">
            <div 
              className="absolute top-0 bottom-0 border-l border-neutral-800" 
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
