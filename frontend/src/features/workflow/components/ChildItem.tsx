import { useState } from 'react';
import { 
  Wrench, 
  Bot, 
  CheckCircle2, 
  XCircle,
  FileJson,
  ChevronRight,
  ChevronDown,
  Loader2
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

const getStatusBorderColor = (status?: string) => {
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

const getTokenCount = (payload: Record<string, unknown> | undefined): number | null => {
  if (!payload) return null;
  const usage = payload.usage as Record<string, unknown> | undefined;
  if (usage) {
    const total = usage.total_tokens || usage.totalTokens;
    if (typeof total === 'number') return total;
    const prompt = (usage.prompt_tokens || usage.promptTokens || 0) as number;
    const completion = (usage.completion_tokens || usage.completionTokens || 0) as number;
    if (prompt || completion) return prompt + completion;
  }
  const tokens = payload.total_tokens || payload.tokens || payload.token_count;
  if (typeof tokens === 'number') return tokens;
  return null;
};

const getStatusIcon = (status?: string) => {
  switch (status) {
    case 'success': return <CheckCircle2 size={14} className="text-emerald-500/60" />;
    case 'error': return <XCircle size={14} className="text-rose-500/60" />;
    case 'running': return <Loader2 size={14} className="text-yellow-500/60 animate-spin" />;
    default: return null;
  }
};

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

  return (
    <div>
      <div
        className={`flex items-center gap-2 py-1.5 px-2 rounded cursor-pointer transition-all duration-200 border-l-2 ${getStatusBorderColor(tool.status)} ${
          isSelected ? 'bg-blue-900/20 border-l-neutral-400' : 'hover:bg-neutral-900'
        }`}
        style={{ paddingLeft: `${depth * 12 + 8}px` }}
        onClick={(e) => {
          e.stopPropagation();
          onSelectNode({ type: 'tool', data: tool });
        }}
      >
        <div className="w-4 flex justify-center">
          <Wrench size={14} className="text-neutral-400" />
        </div>

        <div className="flex flex-col flex-1 min-w-0 gap-0.5">
          <div className="flex items-center gap-2">
            <span className={`text-sm font-semibold truncate ${isSelected ? 'text-white' : 'text-neutral-200'}`}>
              {tool.tool_name}
            </span>
          </div>
          {tool.symbol && (
            <div className="flex items-center gap-2 pl-0">
              <span className="px-1.5 py-0.5 text-[10px] rounded bg-neutral-800/50 text-neutral-500 border border-neutral-700/50">
                {tool.symbol}
              </span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          {tool.duration_ms && (
            <span className="text-xs text-neutral-500">
              {formatDuration(tool.duration_ms)}
            </span>
          )}
          {getStatusIcon(tool.status)}
        </div>
      </div>
      
      {tool.status === 'error' && tool.error && (
        <div 
          className="text-xs text-rose-400/80 truncate py-0.5"
          style={{ paddingLeft: `${depth * 12 + 32}px` }}
          title={tool.error}
        >
          {truncateError(tool.error)}
        </div>
      )}
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
    const afterPayload = after?.payload as Record<string, unknown> | undefined;
    const seq = payload?.seq as number | undefined;
    const tokenCount = getTokenCount(afterPayload) || getTokenCount(payload);
    
    let durationMs = 0;
    if (before.ts && after?.ts) {
      const start = new Date(before.ts).getTime();
      const end = new Date(after.ts).getTime();
      durationMs = end - start;
    }

    const hasToolCalls = toolCalls && toolCalls.length > 0;
    const hasError = after?.status === 'error' || before.status === 'error';
    const errorMessage = after?.error || before.error;
    const status = after?.status || (after ? 'success' : 'running');

    return (
      <div>
        <div
          className={`flex items-center gap-2 py-1.5 px-2 rounded cursor-pointer transition-all duration-200 border-l-2 ${getStatusBorderColor(status)} bg-neutral-900/30 ${
            isSelected ? 'bg-blue-900/20 border-l-neutral-400' : 'hover:bg-neutral-800/50'
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
          
          <div className="flex flex-col flex-1 min-w-0 gap-0.5">
            <div className="flex items-center gap-2">
              <Bot size={14} className="text-neutral-400" />
              <span className={`text-sm font-semibold truncate ${isSelected ? 'text-white' : 'text-neutral-200'}`}>
                Model Call {seq ? `#${seq}` : ''}
              </span>
            </div>
            {(tokenCount || hasToolCalls) && (
              <div className="flex items-center gap-2 pl-6">
                {tokenCount && (
                  <span className="px-1.5 py-0.5 text-[10px] rounded bg-neutral-800/50 text-neutral-500 border border-neutral-700/50">
                    {tokenCount.toLocaleString()} tokens
                  </span>
                )}
              </div>
            )}
          </div>

          <div className="flex items-center gap-2">
            {durationMs > 0 && (
              <span className="text-xs text-neutral-500">
                {formatDuration(durationMs)}
              </span>
            )}
            {getStatusIcon(status)}
          </div>
        </div>

        {hasError && errorMessage && (
          <div 
            className="text-xs text-rose-400/80 truncate py-0.5"
            style={{ paddingLeft: `${depth * 12 + 32}px` }}
            title={errorMessage}
          >
            {truncateError(errorMessage)}
          </div>
        )}

        {isExpanded && hasToolCalls && (
          <div className="relative">
            <div 
              className="absolute top-0 bottom-0 border-l border-neutral-700/50" 
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
    if (toolChild.type === 'tool_call') return <Wrench size={14} className="text-neutral-400" />;
    return <FileJson size={14} className="text-neutral-400" />;
  };

  const getName = () => {
    if (toolChild.type === 'tool_call') return toolChild.tool_name;
    return toolChild.type;
  };

  return (
    <div>
      <div
        className={`flex items-center gap-2 py-1.5 px-2 rounded cursor-pointer transition-all duration-200 border-l-2 ${getStatusBorderColor(toolChild.status)} ${
          isSelected ? 'bg-blue-900/20 border-l-neutral-400' : 'hover:bg-neutral-900'
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

        <div className="flex flex-col flex-1 min-w-0 gap-0.5">
          <div className="flex items-center gap-2">
            <span className={`text-sm font-semibold truncate ${isSelected ? 'text-white' : 'text-neutral-200'}`}>
              {getName()}
            </span>
          </div>
          {toolChild.symbol && (
            <div className="flex items-center gap-2 pl-0">
              <span className="px-1.5 py-0.5 text-[10px] rounded bg-neutral-800/50 text-neutral-500 border border-neutral-700/50">
                {toolChild.symbol}
              </span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          {toolChild.duration_ms && (
            <span className="text-xs text-neutral-500">
              {formatDuration(toolChild.duration_ms)}
            </span>
          )}
          {getStatusIcon(toolChild.status)}
        </div>
      </div>
      
      {toolChild.status === 'error' && toolChild.error && (
        <div 
          className="text-xs text-rose-400/80 truncate py-0.5"
          style={{ paddingLeft: `${depth * 12 + 32}px` }}
          title={toolChild.error}
        >
          {truncateError(toolChild.error)}
        </div>
      )}
    </div>
  );
}
