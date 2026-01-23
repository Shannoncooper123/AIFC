import { useState } from 'react';
import { 
  Copy, 
  Check, 
  Bot, 
  Wrench, 
  Workflow, 
  AlertCircle 
} from 'lucide-react';
import type { WorkflowSpan, WorkflowSpanChild } from '../../../types';

export type SelectedNode = 
  | { type: 'span'; data: WorkflowSpan }
  | { type: 'tool'; data: WorkflowSpanChild }
  | { type: 'model'; data: { before: WorkflowSpanChild; after?: WorkflowSpanChild } }
  | null;

interface DetailPanelProps {
  selectedNode: SelectedNode;
}

function CodeBlock({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="relative group rounded-md bg-zinc-950 border border-zinc-800 overflow-hidden">
      <div className="absolute right-2 top-2 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          onClick={handleCopy}
          className="p-1.5 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-white transition-colors"
        >
          {copied ? <Check size={14} /> : <Copy size={14} />}
        </button>
      </div>
      <pre className="p-4 overflow-x-auto text-xs font-mono text-zinc-300 leading-relaxed">
        {code}
      </pre>
    </div>
  );
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
        active
          ? 'border-blue-500 text-zinc-100'
          : 'border-transparent text-zinc-500 hover:text-zinc-300'
      }`}
    >
      {children}
    </button>
  );
}

export function DetailPanel({ selectedNode }: DetailPanelProps) {
  const [activeTab, setActiveTab] = useState<'input' | 'output'>('input');

  if (!selectedNode) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-zinc-500 gap-3">
        <Workflow size={48} className="opacity-20" />
        <p className="text-sm">Select a node to view details</p>
      </div>
    );
  }

  const renderContent = () => {
    switch (selectedNode.type) {
      case 'span': {
        const { data } = selectedNode;
        return (
          <div className="space-y-6">
            <div className="flex items-center gap-3 pb-4 border-b border-zinc-800">
              <div className="p-2 rounded bg-zinc-800">
                <Workflow size={20} className="text-blue-400" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-zinc-100">{data.node}</h3>
                <div className="flex items-center gap-2 text-xs text-zinc-500">
                  <span className="font-mono">{data.span_id}</span>
                  {data.symbol && (
                    <span className="px-1.5 py-0.5 rounded bg-zinc-800 border border-zinc-700 text-zinc-400">
                      {data.symbol}
                    </span>
                  )}
                </div>
              </div>
            </div>

            <div className="space-y-4">
              {activeTab === 'input' ? (
                <div>
                  <h4 className="text-sm font-medium text-zinc-400 mb-2">Input Context</h4>
                  <div className="p-4 rounded-md bg-zinc-900 border border-zinc-800 text-sm text-zinc-500 italic">
                    Span inputs are not explicitly tracked in the current trace version.
                    View the "Input" tab of the parent run or specific tool calls for data flow.
                  </div>
                </div>
              ) : (
                <div>
                  <h4 className="text-sm font-medium text-zinc-400 mb-2">Span Info</h4>
                  <CodeBlock 
                    code={JSON.stringify({
                      span_id: data.span_id,
                      parent_span_id: data.parent_span_id,
                      node: data.node,
                      symbol: data.symbol,
                      start_time: data.start_time,
                      end_time: data.end_time,
                      duration_ms: data.duration_ms,
                      status: data.status,
                      error: data.error,
                      output_summary: data.output_summary
                    }, null, 2)} 
                  />
                </div>
              )}
            </div>
          </div>
        );
      }

      case 'model': {
        const { before, after } = selectedNode.data;
        const beforePayload = before.payload as Record<string, unknown> | undefined;
        const afterPayload = after?.payload as Record<string, unknown> | undefined;

        const recentMessages = (beforePayload?.recent_messages || []) as any[];
        const toolCalls = (afterPayload?.tool_calls || []) as any[];
        const responseContent = afterPayload?.response_content;

        return (
          <div className="space-y-6">
            <div className="flex items-center gap-3 pb-4 border-b border-zinc-800">
              <div className="p-2 rounded bg-zinc-800">
                <Bot size={20} className="text-purple-400" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-zinc-100">Model Call</h3>
                <div className="flex items-center gap-2 text-xs text-zinc-500">
                  <span>{Number(beforePayload?.total_messages) || 0} messages</span>
                  <span>•</span>
                  <span>{String(beforePayload?.model_span_id ?? '')}</span>
                </div>
              </div>
            </div>

            <div className="space-y-4">
              {activeTab === 'input' ? (
                <div>
                  <h4 className="text-sm font-medium text-zinc-400 mb-2">Messages</h4>
                  <div className="space-y-3">
                    {recentMessages.map((msg, idx) => (
                      <div key={idx} className="flex gap-3 text-sm">
                        <div className={`w-16 shrink-0 text-xs font-mono uppercase mt-1 ${
                          msg.role === 'human' ? 'text-blue-400' :
                          msg.role === 'ai' ? 'text-green-400' :
                          msg.role === 'tool' ? 'text-yellow-400' :
                          'text-zinc-500'
                        }`}>
                          {msg.role}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="p-3 rounded bg-zinc-900 border border-zinc-800 text-zinc-300 whitespace-pre-wrap">
                            {msg.content || <span className="text-zinc-600 italic">(empty content)</span>}
                          </div>
                          {msg.tool_calls && msg.tool_calls.length > 0 && (
                            <div className="mt-2 ml-2 pl-3 border-l-2 border-zinc-800 space-y-2">
                              {msg.tool_calls.map((tc: any, i: number) => (
                                <div key={i} className="text-xs">
                                  <span className="text-yellow-500 font-mono">{tc.name}</span>
                                  <span className="text-zinc-500 mx-1">args:</span>
                                  <span className="text-zinc-400 font-mono">{JSON.stringify(tc.args_keys)}</span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="space-y-6">
                  {responseContent ? (
                    <div>
                      <h4 className="text-sm font-medium text-zinc-400 mb-2">Response Content</h4>
                      <div className="p-4 rounded bg-zinc-900 border border-zinc-800 text-zinc-300 whitespace-pre-wrap text-sm">
                        {responseContent as string}
                      </div>
                    </div>
                  ) : (
                    <div className="p-4 rounded bg-zinc-900 border border-zinc-800 text-zinc-500 text-sm italic">
                      No text content generated
                    </div>
                  )}

                  {toolCalls.length > 0 && (
                    <div>
                      <h4 className="text-sm font-medium text-zinc-400 mb-2">Tool Calls</h4>
                      <div className="space-y-3">
                        {toolCalls.map((tc, idx) => (
                          <div key={idx} className="rounded border border-zinc-800 overflow-hidden">
                            <div className="px-3 py-2 bg-zinc-900 border-b border-zinc-800 flex items-center justify-between">
                              <span className="text-sm font-medium text-yellow-500 font-mono">{tc.name}</span>
                              <span className="text-xs text-zinc-500 font-mono">{tc.id}</span>
                            </div>
                            <div className="p-3 bg-zinc-950">
                              <CodeBlock code={JSON.stringify(tc.args, null, 2)} />
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  
                  {!after && (
                    <div className="flex items-center gap-2 p-3 rounded bg-yellow-500/10 text-yellow-500 text-sm border border-yellow-500/20">
                      <AlertCircle size={16} />
                      Waiting for model response...
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        );
      }

      case 'tool': {
        const { data } = selectedNode;
        const payload = data.payload as Record<string, unknown> | undefined;
        const input = payload?.input;
        const output = payload?.output;
        
        return (
          <div className="space-y-6">
            <div className="flex items-center gap-3 pb-4 border-b border-zinc-800">
              <div className="p-2 rounded bg-zinc-800">
                <Wrench size={20} className="text-orange-400" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-zinc-100">{data.tool_name}</h3>
                <div className="flex items-center gap-2 text-xs text-zinc-500">
                  <span className="font-mono">{data.ts}</span>
                  {data.duration_ms && (
                    <>
                      <span>•</span>
                      <span>{data.duration_ms}ms</span>
                    </>
                  )}
                </div>
              </div>
            </div>

            <div className="space-y-4">
              {activeTab === 'input' ? (
                <div>
                  <h4 className="text-sm font-medium text-zinc-400 mb-2">Arguments</h4>
                  <CodeBlock code={JSON.stringify(input, null, 2)} />
                </div>
              ) : (
                <div>
                  <h4 className="text-sm font-medium text-zinc-400 mb-2">Result</h4>
                  <CodeBlock code={JSON.stringify(output, null, 2)} />
                </div>
              )}
            </div>
          </div>
        );
      }
    }
  };

  return (
    <div className="h-full flex flex-col bg-zinc-900">
      <div className="flex border-b border-zinc-800 px-4">
        <TabButton active={activeTab === 'input'} onClick={() => setActiveTab('input')}>
          Input
        </TabButton>
        <TabButton active={activeTab === 'output'} onClick={() => setActiveTab('output')}>
          Output
        </TabButton>
      </div>
      <div className="flex-1 overflow-y-auto p-6">
        {renderContent()}
      </div>
    </div>
  );
}
