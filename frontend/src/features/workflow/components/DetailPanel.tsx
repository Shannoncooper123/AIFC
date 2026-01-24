import { useState } from 'react';
import { 
  Copy, 
  Check, 
  Bot, 
  Wrench, 
  Workflow, 
  AlertCircle,
  Image as ImageIcon
} from 'lucide-react';
import type { WorkflowSpan, WorkflowSpanChild, WorkflowArtifact } from '../../../types';

interface MessageItem {
  role: string;
  content?: string | Array<{ type: string; image_url?: { url: string } }>;
  tool_calls?: Array<{ name: string; args_keys: string[] }>;
}

interface ToolCallItem {
  name: string;
  id?: string;
  args?: Record<string, unknown>;
  args_keys?: string[];
}

export type SelectedNode = 
  | { type: 'span'; data: WorkflowSpan }
  | { type: 'tool'; data: WorkflowSpanChild }
  | { type: 'model'; data: { before: WorkflowSpanChild; after?: WorkflowSpanChild } }
  | null;

interface DetailPanelProps {
  selectedNode: SelectedNode;
  allArtifacts?: WorkflowArtifact[];
}

function CodeBlock({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="relative group rounded-md bg-[#141414] border border-neutral-800 overflow-hidden">
      <div className="absolute right-2 top-2 opacity-0 group-hover:opacity-100 transition-all duration-200">
        <button
          onClick={handleCopy}
          className="p-1.5 rounded bg-neutral-800 hover:bg-neutral-700 text-neutral-400 hover:text-white transition-all duration-200"
        >
          {copied ? <Check size={14} /> : <Copy size={14} />}
        </button>
      </div>
      <pre className="p-4 overflow-x-auto text-xs font-mono text-neutral-300 leading-relaxed">
        {code}
      </pre>
    </div>
  );
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 text-sm font-medium border-b-2 transition-all duration-200 ${
        active
          ? 'border-neutral-400 text-white'
          : 'border-transparent text-neutral-500 hover:text-neutral-300'
      }`}
    >
      {children}
    </button>
  );
}

function MessageContent({ content }: { content: string | Array<{ type: string; image_url?: { url: string } }> | undefined }) {
  if (!content) {
    return <span className="text-neutral-600 italic">(empty content)</span>;
  }

  if (typeof content === 'string') {
    return <>{content}</>;
  }

  if (Array.isArray(content)) {
    return (
      <div className="space-y-3">
        {content.map((item, idx) => {
          if (item.type === 'image_url' && item.image_url?.url) {
            const isBase64 = item.image_url.url.startsWith('data:image');
            return (
              <div key={idx} className="space-y-2">
                <div className="flex items-center gap-2 text-xs text-purple-400">
                  <ImageIcon size={14} />
                  <span>K线图图像</span>
                </div>
                {isBase64 ? (
                  <img 
                    src={item.image_url.url} 
                    alt="K-line chart" 
                    className="max-w-full rounded border border-neutral-700"
                  />
                ) : (
                  <div className="text-neutral-500 text-xs italic">
                    [图像URL: {item.image_url.url.substring(0, 50)}...]
                  </div>
                )}
              </div>
            );
          }
          if (item.type === 'text' && 'text' in item) {
            return <div key={idx}>{(item as { type: string; text: string }).text}</div>;
          }
          return <div key={idx} className="text-neutral-500 text-xs">[{item.type}]</div>;
        })}
      </div>
    );
  }

  return <span className="text-neutral-600 italic">(unknown content format)</span>;
}

function ImagePreview({ artifact }: { artifact: WorkflowArtifact }) {
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-xs text-purple-400">
        <ImageIcon size={14} />
        <span>{artifact.symbol} · {artifact.interval}</span>
      </div>
      {error ? (
        <div className="p-4 rounded bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
          图像加载失败
        </div>
      ) : (
        <img
          src={`/api/workflow/artifacts/${artifact.artifact_id}`}
          alt={`${artifact.symbol} ${artifact.interval}`}
          className={`max-w-full rounded border border-neutral-700 transition-opacity ${loaded ? 'opacity-100' : 'opacity-0'}`}
          onLoad={() => setLoaded(true)}
          onError={() => setError(true)}
        />
      )}
    </div>
  );
}

export function DetailPanel({ selectedNode, allArtifacts = [] }: DetailPanelProps) {
  const [activeTab, setActiveTab] = useState<'input' | 'output'>('input');

  if (!selectedNode) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-neutral-500 gap-3">
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
            <div className="flex items-center gap-3 pb-4 border-b border-neutral-800">
              <div className="p-2 rounded bg-neutral-800">
                <Workflow size={20} className="text-neutral-400" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-white">{data.node}</h3>
                <div className="flex items-center gap-2 text-xs text-neutral-500">
                  <span className="font-mono">{data.span_id}</span>
                  {data.symbol && (
                    <span className="px-1.5 py-0.5 rounded bg-neutral-800 border border-neutral-700 text-neutral-400">
                      {data.symbol}
                    </span>
                  )}
                </div>
              </div>
            </div>

            <div className="space-y-4">
              {activeTab === 'input' ? (
                <div>
                  <h4 className="text-sm font-medium text-neutral-400 mb-2">Input Context</h4>
                  <div className="p-4 rounded-md bg-[#1a1a1a] border border-neutral-800 text-sm text-neutral-500 italic">
                    Span inputs are not explicitly tracked in the current trace version.
                    View the "Input" tab of the parent run or specific tool calls for data flow.
                  </div>
                </div>
              ) : (
                <div>
                  <h4 className="text-sm font-medium text-neutral-400 mb-2">Span Info</h4>
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

        const recentMessages = (beforePayload?.recent_messages || []) as MessageItem[];
        const toolCalls = (afterPayload?.tool_calls || []) as ToolCallItem[];
        const responseContent = afterPayload?.response_content;

        return (
          <div className="space-y-6">
            <div className="flex items-center gap-3 pb-4 border-b border-neutral-800">
              <div className="p-2 rounded bg-neutral-800">
                <Bot size={20} className="text-purple-400/80" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-white">Model Call</h3>
                <div className="flex items-center gap-2 text-xs text-neutral-500">
                  <span>{Number(beforePayload?.total_messages) || 0} messages</span>
                  <span>•</span>
                  <span>{String(beforePayload?.model_span_id ?? '')}</span>
                </div>
              </div>
            </div>

            <div className="space-y-4">
              {activeTab === 'input' ? (
                <div>
                  <h4 className="text-sm font-medium text-neutral-400 mb-2">Messages</h4>
                  <div className="space-y-3">
                    {recentMessages.map((msg, idx) => (
                      <div key={idx} className="flex gap-3 text-sm">
                        <div className={`w-16 shrink-0 text-xs font-mono uppercase mt-1 ${
                          msg.role === 'human' ? 'text-neutral-400' :
                          msg.role === 'ai' ? 'text-emerald-500/80' :
                          msg.role === 'tool' ? 'text-yellow-400/80' :
                          'text-neutral-500'
                        }`}>
                          {msg.role}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="p-3 rounded bg-[#1a1a1a] border border-neutral-800 text-neutral-300 whitespace-pre-wrap">
                            <MessageContent content={msg.content} />
                          </div>
                          {msg.tool_calls && msg.tool_calls.length > 0 && (
                            <div className="mt-2 ml-2 pl-3 border-l-2 border-neutral-800 space-y-2">
                              {msg.tool_calls.map((tc, i: number) => (
                                <div key={i} className="text-xs">
                                  <span className="text-yellow-500/80 font-mono">{tc.name}</span>
                                  <span className="text-neutral-500 mx-1">args:</span>
                                  <span className="text-neutral-400 font-mono">{JSON.stringify(tc.args_keys)}</span>
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
                      <h4 className="text-sm font-medium text-neutral-400 mb-2">Response Content</h4>
                      <div className="p-4 rounded bg-[#1a1a1a] border border-neutral-800 text-neutral-300 whitespace-pre-wrap text-sm">
                        {responseContent as string}
                      </div>
                    </div>
                  ) : (
                    <div className="p-4 rounded bg-[#1a1a1a] border border-neutral-800 text-neutral-500 text-sm italic">
                      No text content generated
                    </div>
                  )}

                  {toolCalls.length > 0 && (
                    <div>
                      <h4 className="text-sm font-medium text-neutral-400 mb-2">Tool Calls</h4>
                      <div className="space-y-3">
                        {toolCalls.map((tc, idx) => (
                          <div key={idx} className="rounded border border-neutral-800 overflow-hidden">
                            <div className="px-3 py-2 bg-[#1a1a1a] border-b border-neutral-800 flex items-center justify-between">
                              <span className="text-sm font-medium text-yellow-500/80 font-mono">{tc.name}</span>
                              <span className="text-xs text-neutral-500 font-mono">{tc.id}</span>
                            </div>
                            <div className="p-3 bg-[#141414]">
                              <CodeBlock code={JSON.stringify(tc.args, null, 2)} />
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  
                  {!after && (
                    <div className="flex items-center gap-2 p-3 rounded bg-yellow-500/10 text-yellow-500/80 text-sm border border-yellow-500/20">
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
        const output = payload?.output as Record<string, unknown> | undefined;
        
        const isKlineImageTool = data.tool_name === 'get_kline_image';
        const toolSymbol = data.symbol || output?.symbol as string;
        const toolIntervals = output?.intervals as string[] | undefined;
        const toolInterval = toolIntervals?.[0];
        
        const matchingArtifact = isKlineImageTool 
          ? allArtifacts.find(a => 
              a.symbol === toolSymbol && 
              (!toolInterval || a.interval === toolInterval)
            )
          : undefined;
        
        return (
          <div className="space-y-6">
            <div className="flex items-center gap-3 pb-4 border-b border-neutral-800">
              <div className="p-2 rounded bg-neutral-800">
                <Wrench size={20} className="text-orange-400/80" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-white">{data.tool_name}</h3>
                <div className="flex items-center gap-2 text-xs text-neutral-500">
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
                  <h4 className="text-sm font-medium text-neutral-400 mb-2">Arguments</h4>
                  <CodeBlock code={JSON.stringify(input, null, 2)} />
                </div>
              ) : (
                <div className="space-y-4">
                  <h4 className="text-sm font-medium text-neutral-400 mb-2">Result</h4>
                  
                  {isKlineImageTool && matchingArtifact ? (
                    <div className="space-y-4">
                      <ImagePreview artifact={matchingArtifact} />
                      <div>
                        <h5 className="text-xs font-medium text-neutral-500 mb-2">Metadata</h5>
                        <CodeBlock code={JSON.stringify({
                          success: output?.success,
                          symbol: output?.symbol,
                          intervals: output?.intervals,
                          kline_count: output?.kline_count,
                        }, null, 2)} />
                      </div>
                    </div>
                  ) : (
                    <CodeBlock code={JSON.stringify(output, null, 2)} />
                  )}
                </div>
              )}
            </div>
          </div>
        );
      }
    }
  };

  return (
    <div className="h-full flex flex-col bg-[#1a1a1a]">
      <div className="flex border-b border-neutral-800 px-4">
        <TabButton active={activeTab === 'input'} onClick={() => setActiveTab('input')}>
          Input
        </TabButton>
        <TabButton active={activeTab === 'output'} onClick={() => setActiveTab('output')}>
          Output
        </TabButton>
      </div>
      <div className="flex-1 overflow-y-auto p-4 sm:p-6">
        {renderContent()}
      </div>
    </div>
  );
}
