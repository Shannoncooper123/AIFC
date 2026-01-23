import { 
  Wrench, 
  Bot, 
  Clock, 
  CheckCircle2, 
  XCircle,
  FileJson
} from 'lucide-react';
import type { WorkflowSpanChild, WorkflowArtifact } from '../../../types';
import { formatDuration } from '../../../utils';
import type { SelectedNode } from './DetailPanel';

interface ChildItemProps {
  child: WorkflowSpanChild | { 
    type: 'model_call_group'; 
    before: WorkflowSpanChild; 
    after?: WorkflowSpanChild;
    children?: WorkflowSpanChild[];
  };
  depth: number;
  allArtifacts: WorkflowArtifact[];
  selectedNode: SelectedNode;
  onSelectNode: (node: SelectedNode) => void;
}

export function ChildItem({ 
  child, 
  depth, 
  // allArtifacts, // 暂时未使用
  selectedNode,
  onSelectNode
}: ChildItemProps) {
  // 处理合并后的模型调用
  if ('type' in child && child.type === 'model_call_group') {
    const { before, after } = child;
    const isSelected = selectedNode?.type === 'model' && 
      selectedNode.data.before.ts === before.ts;

    const payload = before.payload as Record<string, unknown> | undefined;
    const seq = payload?.seq as number | undefined;
    
    // 计算耗时
    let durationMs = 0;
    if (before.ts && after?.ts) {
      const start = new Date(before.ts).getTime();
      const end = new Date(after.ts).getTime();
      durationMs = end - start;
    }

    return (
      <div
        className={`flex items-center gap-2 py-1.5 px-2 rounded cursor-pointer transition-colors ${
          isSelected ? 'bg-zinc-800 border-l-2 border-blue-500' : 'hover:bg-zinc-900 border-l-2 border-transparent'
        }`}
        style={{ paddingLeft: `${depth * 12 + 8}px` }}
        onClick={(e) => {
          e.stopPropagation();
          onSelectNode({ type: 'model', data: { before, after } });
        }}
      >
        <div className="w-4 flex justify-center">
          <Bot size={14} className="text-zinc-400" />
        </div>
        
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <span className={`text-sm font-medium truncate ${isSelected ? 'text-zinc-100' : 'text-zinc-300'}`}>
            Model Call {seq ? `#${seq}` : ''}
          </span>
        </div>

        <div className="flex items-center gap-3">
          {durationMs > 0 && (
            <span className="text-xs text-zinc-500 flex items-center gap-1">
              <Clock size={10} />
              {formatDuration(durationMs)}
            </span>
          )}
          <CheckCircle2 size={14} className="text-emerald-500" />
        </div>
      </div>
    );
  }

  // 处理普通工具调用
  const toolChild = child as WorkflowSpanChild;
  const isSelected = selectedNode?.type === 'tool' && 
    selectedNode.data.ts === toolChild.ts;

  const getIcon = () => {
    if (toolChild.type === 'tool_call') return <Wrench size={14} className="text-zinc-400" />;
    return <FileJson size={14} className="text-zinc-400" />;
  };

  const getName = () => {
    if (toolChild.type === 'tool_call') return toolChild.tool_name;
    return toolChild.type;
  };

  const getStatusIcon = (status?: string) => {
    switch (status) {
      case 'success': return <CheckCircle2 size={14} className="text-emerald-500" />;
      case 'error': return <XCircle size={14} className="text-red-500" />;
      default: return <div className="w-3.5 h-3.5 rounded-full bg-zinc-700" />;
    }
  };

  return (
    <div
      className={`flex items-center gap-2 py-1.5 px-2 rounded cursor-pointer transition-colors ${
        isSelected ? 'bg-zinc-800 border-l-2 border-blue-500' : 'hover:bg-zinc-900 border-l-2 border-transparent'
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
        <span className={`text-sm truncate ${isSelected ? 'text-zinc-100' : 'text-zinc-300'}`}>
          {getName()}
        </span>
        {toolChild.symbol && (
          <span className="px-1.5 py-0.5 text-[10px] rounded bg-zinc-800 text-zinc-400 border border-zinc-700">
            {toolChild.symbol}
          </span>
        )}
      </div>

      <div className="flex items-center gap-3">
        {toolChild.duration_ms && (
          <span className="text-xs text-zinc-500 flex items-center gap-1">
            <Clock size={10} />
            {formatDuration(toolChild.duration_ms)}
          </span>
        )}
        {getStatusIcon(toolChild.status)}
      </div>
    </div>
  );
}
