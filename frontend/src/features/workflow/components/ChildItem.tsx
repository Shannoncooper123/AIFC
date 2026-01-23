import { useState } from 'react';
import { 
  Wrench, 
  Bot, 
  Clock, 
  CheckCircle2, 
  XCircle,
  FileJson,
  ChevronRight,
  ChevronDown
} from 'lucide-react';
import type { WorkflowSpanChild, WorkflowArtifact } from '../../../types';
import { formatDuration } from '../../../utils';
import type { SelectedNode } from './DetailPanel';

export interface ModelCallGroup {
  type: 'model_call_group';
  before: WorkflowSpanChild;
  after?: WorkflowSpanChild;
  children: WorkflowSpanChild[];
}

interface ChildItemProps {
  child: WorkflowSpanChild | ModelCallGroup;
  depth: number;
  allArtifacts: WorkflowArtifact[];
  selectedNode: SelectedNode;
  onSelectNode: (node: SelectedNode) => void;
}

function ToolCallItem({ 
  tool, 
  depth, 
  selectedNode, 
  onSelectNode 
}: { 
  tool: WorkflowSpanChild; 
  depth: number; 
  selectedNode: SelectedNode; 
  onSelectNode: (node: SelectedNode) => void;
}) {
  const isSelected = selectedNode?.type === 'tool' && selectedNode.data.ts === tool.ts;

  const getStatusIcon = (status?: string) => {
    switch (status) {
      case 'success': return <CheckCircle2 size={14} className="text-emerald-500/80" />;
      case 'error': return <XCircle size={14} className="text-rose-500/80" />;
      default: return <div className="w-3.5 h-3.5 rounded-full bg-neutral-700" />;
    }
  };

  return (
    <div
      className={`flex items-center gap-2 py-1.5 px-2 rounded cursor-pointer transition-all duration-200 ${
        isSelected ? 'bg-neutral-800 border-l-2 border-neutral-400' : 'hover:bg-neutral-900 border-l-2 border-transparent'
      }`}
      style={{ paddingLeft: `${depth * 12 + 8}px` }}
      onClick={(e) => {
        e.stopPropagation();
        onSelectNode({ type: 'tool', data: tool });
      }}
    >
      <div className="w-4 flex justify-center">
        <Wrench size={14} className="text-orange-400/80" />
      </div>

      <div className="flex items-center gap-2 flex-1 min-w-0">
        <span className={`text-sm truncate ${isSelected ? 'text-white' : 'text-neutral-300'}`}>
          {tool.tool_name}
        </span>
        {tool.symbol && (
          <span className="px-1.5 py-0.5 text-[10px] rounded bg-neutral-800 text-neutral-400 border border-neutral-700">
            {tool.symbol}
          </span>
        )}
      </div>

      <div className="flex items-center gap-3">
        {tool.duration_ms && (
          <span className="text-xs text-neutral-500 flex items-center gap-1">
            <Clock size={10} />
            {formatDuration(tool.duration_ms)}
          </span>
        )}
        {getStatusIcon(tool.status)}
      </div>
    </div>
  );
}

export function ChildItem({ 
  child, 
  depth, 
  selectedNode,
  onSelectNode
}: ChildItemProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  
  if ('type' in child && child.type === 'model_call_group') {
    const { before, after, children: toolCalls } = child;
    const isSelected = selectedNode?.type === 'model' && 
      selectedNode.data.before.ts === before.ts;

    const payload = before.payload as Record<string, unknown> | undefined;
    const seq = payload?.seq as number | undefined;
    
    let durationMs = 0;
    if (before.ts && after?.ts) {
      const start = new Date(before.ts).getTime();
      const end = new Date(after.ts).getTime();
      durationMs = end - start;
    }

    const hasToolCalls = toolCalls && toolCalls.length > 0;

    return (
      <div>
        <div
          className={`flex items-center gap-2 py-1.5 px-2 rounded cursor-pointer transition-all duration-200 ${
            isSelected ? 'bg-neutral-800 border-l-2 border-neutral-400' : 'hover:bg-neutral-900 border-l-2 border-transparent'
          }`}
          style={{ paddingLeft: `${depth * 12 + 8}px` }}
          onClick={(e) => {
            e.stopPropagation();
            onSelectNode({ type: 'model', data: { before, after } });
            if (hasToolCalls && !isExpanded) {
              setIsExpanded(true);
            }
          }}
        >
          <div 
            className="flex-shrink-0 w-4 h-4 flex items-center justify-center text-neutral-500 hover:text-neutral-300 transition-all duration-200"
            onClick={(e) => {
              e.stopPropagation();
              if (hasToolCalls) setIsExpanded(!isExpanded);
            }}
          >
            {hasToolCalls ? (
              isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />
            ) : <div className="w-4" />}
          </div>
          
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <Bot size={14} className="text-purple-400/80" />
            <span className={`text-sm font-medium truncate ${isSelected ? 'text-white' : 'text-neutral-300'}`}>
              Model Call {seq ? `#${seq}` : ''}
            </span>
            {hasToolCalls && (
              <span className="px-1.5 py-0.5 text-[10px] rounded bg-neutral-800 text-neutral-500 border border-neutral-700">
                {toolCalls.length} tool{toolCalls.length > 1 ? 's' : ''}
              </span>
            )}
          </div>

          <div className="flex items-center gap-3">
            {durationMs > 0 && (
              <span className="text-xs text-neutral-500 flex items-center gap-1">
                <Clock size={10} />
                {formatDuration(durationMs)}
              </span>
            )}
            <CheckCircle2 size={14} className="text-emerald-500/80" />
          </div>
        </div>

        {isExpanded && hasToolCalls && (
          <div className="relative">
            <div 
              className="absolute top-0 bottom-0 border-l border-neutral-800" 
              style={{ left: `${depth * 12 + 15}px` }} 
            />
            {toolCalls.map((tool, idx) => (
              <ToolCallItem
                key={`${tool.ts}-${idx}`}
                tool={tool}
                depth={depth + 1}
                selectedNode={selectedNode}
                onSelectNode={onSelectNode}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  const toolChild = child as WorkflowSpanChild;
  const isSelected = selectedNode?.type === 'tool' && 
    selectedNode.data.ts === toolChild.ts;

  const getIcon = () => {
    if (toolChild.type === 'tool_call') return <Wrench size={14} className="text-orange-400/80" />;
    return <FileJson size={14} className="text-neutral-400" />;
  };

  const getName = () => {
    if (toolChild.type === 'tool_call') return toolChild.tool_name;
    return toolChild.type;
  };

  const getStatusIcon = (status?: string) => {
    switch (status) {
      case 'success': return <CheckCircle2 size={14} className="text-emerald-500/80" />;
      case 'error': return <XCircle size={14} className="text-rose-500/80" />;
      default: return <div className="w-3.5 h-3.5 rounded-full bg-neutral-700" />;
    }
  };

  return (
    <div
      className={`flex items-center gap-2 py-1.5 px-2 rounded cursor-pointer transition-all duration-200 ${
        isSelected ? 'bg-neutral-800 border-l-2 border-neutral-400' : 'hover:bg-neutral-900 border-l-2 border-transparent'
      }`}
      style={{ paddingLeft: `${depth * 12 + 8}px` }}
      onClick={(e) => {
        e.stopPropagation();
        onSelectNode({ type: 'tool', data: toolChild });
      }}
    >
      <div className="w-4 flex justify-center">
        {getIcon()}
      </div>

      <div className="flex items-center gap-2 flex-1 min-w-0">
        <span className={`text-sm truncate ${isSelected ? 'text-white' : 'text-neutral-300'}`}>
          {getName()}
        </span>
        {toolChild.symbol && (
          <span className="px-1.5 py-0.5 text-[10px] rounded bg-neutral-800 text-neutral-400 border border-neutral-700">
            {toolChild.symbol}
          </span>
        )}
      </div>

      <div className="flex items-center gap-3">
        {toolChild.duration_ms && (
          <span className="text-xs text-neutral-500 flex items-center gap-1">
            <Clock size={10} />
            {formatDuration(toolChild.duration_ms)}
          </span>
        )}
        {getStatusIcon(toolChild.status)}
      </div>
    </div>
  );
}
