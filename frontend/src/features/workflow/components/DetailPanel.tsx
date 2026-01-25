import { useState, useMemo } from 'react';
import { 
  Copy, 
  Check, 
  ChevronRight,
  ChevronDown,
  Workflow,
  X,
  Maximize2
} from 'lucide-react';
import type { WorkflowSpan, WorkflowSpanChild, WorkflowArtifact } from '../../../types';
import { formatDuration, formatTime } from '../../../utils';

interface MessageItem {
  role: string;
  content?: string | unknown[];
  tool_calls?: MessageToolCall[];
}

interface ToolCallItem {
  name: string;
  id?: string;
  args?: Record<string, unknown>;
  args_keys?: string[];
}

interface MessageToolCall {
  name: string;
  args_keys?: string[];
  args?: Record<string, unknown>;
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

type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

function JsonSyntaxHighlight({ value, keyName }: { value: JsonValue; keyName?: string }) {
  const [isExpanded, setIsExpanded] = useState(true);
  
  const renderKey = () => {
    if (!keyName) return null;
    return <span className="text-[#9cdcfe]">"{keyName}"</span>;
  };

  if (value === null) {
    return (
      <span>
        {renderKey()}
        {keyName && <span className="text-neutral-500">: </span>}
        <span className="text-[#569cd6]">null</span>
      </span>
    );
  }
  
  if (typeof value === 'boolean') {
    return (
      <span>
        {renderKey()}
        {keyName && <span className="text-neutral-500">: </span>}
        <span className="text-[#569cd6]">{value.toString()}</span>
      </span>
    );
  }
  
  if (typeof value === 'number') {
    return (
      <span>
        {renderKey()}
        {keyName && <span className="text-neutral-500">: </span>}
        <span className="text-[#b5cea8]">{value}</span>
      </span>
    );
  }
  
  if (typeof value === 'string') {
    return (
      <span>
        {renderKey()}
        {keyName && <span className="text-neutral-500">: </span>}
        <span className="text-[#ce9178]">"{value}"</span>
      </span>
    );
  }

  if (Array.isArray(value)) {
    if (value.length === 0) {
      return (
        <span>
          {renderKey()}
          {keyName && <span className="text-neutral-500">: </span>}
          <span className="text-neutral-400">[]</span>
        </span>
      );
    }
    
    return (
      <div>
        <span 
          className="cursor-pointer inline-flex items-center gap-1"
          onClick={() => setIsExpanded(!isExpanded)}
        >
          {isExpanded ? <ChevronDown size={12} className="text-neutral-500" /> : <ChevronRight size={12} className="text-neutral-500" />}
          {renderKey()}
          {keyName && <span className="text-neutral-500">: </span>}
          <span className="text-neutral-400">[</span>
          {!isExpanded && <span className="text-neutral-500">{value.length} items</span>}
          {!isExpanded && <span className="text-neutral-400">]</span>}
        </span>
        {isExpanded && (
          <div className="ml-4 border-l border-neutral-800 pl-3">
            {value.map((item, idx) => (
              <div key={idx}>
                <JsonSyntaxHighlight value={item as JsonValue} />
                {idx < value.length - 1 && <span className="text-neutral-500">,</span>}
              </div>
            ))}
          </div>
        )}
        {isExpanded && <span className="text-neutral-400">]</span>}
      </div>
    );
  }

  if (typeof value === 'object') {
    const entries = Object.entries(value);
    if (entries.length === 0) {
      return (
        <span>
          {renderKey()}
          {keyName && <span className="text-neutral-500">: </span>}
          <span className="text-neutral-400">{'{}'}</span>
        </span>
      );
    }
    
    return (
      <div>
        <span 
          className="cursor-pointer inline-flex items-center gap-1"
          onClick={() => setIsExpanded(!isExpanded)}
        >
          {isExpanded ? <ChevronDown size={12} className="text-neutral-500" /> : <ChevronRight size={12} className="text-neutral-500" />}
          {renderKey()}
          {keyName && <span className="text-neutral-500">: </span>}
          <span className="text-neutral-400">{'{'}</span>
          {!isExpanded && <span className="text-neutral-500">{entries.length} keys</span>}
          {!isExpanded && <span className="text-neutral-400">{'}'}</span>}
        </span>
        {isExpanded && (
          <div className="ml-4 border-l border-neutral-800 pl-3">
            {entries.map(([k, v], idx) => (
              <div key={k}>
                <JsonSyntaxHighlight value={v as JsonValue} keyName={k} />
                {idx < entries.length - 1 && <span className="text-neutral-500">,</span>}
              </div>
            ))}
          </div>
        )}
        {isExpanded && <span className="text-neutral-400">{'}'}</span>}
      </div>
    );
  }

  return null;
}

function JsonViewer({ data }: { data: unknown }) {
  const [copied, setCopied] = useState(false);
  
  const jsonString = useMemo(() => {
    try {
      return JSON.stringify(data, null, 2);
    } catch {
      return String(data);
    }
  }, [data]);

  const handleCopy = () => {
    navigator.clipboard.writeText(jsonString);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (data === undefined || data === null) {
    return (
      <div className="p-4 rounded bg-[#141414] border border-neutral-800/50 text-neutral-500 italic text-sm">
        No data
      </div>
    );
  }

  return (
    <div className="relative group rounded bg-[#141414] border border-neutral-800/50 overflow-hidden">
      <button
        onClick={handleCopy}
        className="absolute right-2 top-2 p-1.5 rounded bg-neutral-800/80 hover:bg-neutral-700 text-neutral-400 hover:text-white transition-all duration-200 opacity-0 group-hover:opacity-100 z-10"
        title="Copy JSON"
      >
        {copied ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
      </button>
      <div className="p-4 overflow-x-auto text-xs font-mono leading-relaxed max-h-[500px] overflow-y-auto">
        <JsonSyntaxHighlight value={data as JsonValue} />
      </div>
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[10px] font-semibold tracking-wider text-neutral-500 uppercase mb-2">
      {children}
    </div>
  );
}

function CollapsibleSection({ 
  label, 
  children, 
  defaultExpanded = false 
}: { 
  label: string; 
  children: React.ReactNode; 
  defaultExpanded?: boolean;
}) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  
  return (
    <div className="border-t border-neutral-800/50">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center gap-2 py-3 text-left hover:bg-neutral-800/30 transition-colors"
      >
        {isExpanded ? (
          <ChevronDown size={14} className="text-neutral-500" />
        ) : (
          <ChevronRight size={14} className="text-neutral-500" />
        )}
        <span className="text-[10px] font-semibold tracking-wider text-neutral-500 uppercase">
          {label}
        </span>
      </button>
      {isExpanded && (
        <div className="pb-4">
          {children}
        </div>
      )}
    </div>
  );
}

function TextContent({ content }: { content: string }) {
  return (
    <div className="p-4 rounded bg-[#141414] border border-neutral-800/50 text-sm text-neutral-300 whitespace-pre-wrap leading-relaxed">
      {content}
    </div>
  );
}

function ExpandableBase64Image({ src, alt }: { src: string; alt?: string }) {
  const [isExpanded, setIsExpanded] = useState(false);
  
  return (
    <>
      <div 
        className="relative group cursor-pointer rounded border border-neutral-800/50 overflow-hidden bg-[#141414] hover:border-neutral-700 transition-colors"
        onClick={() => setIsExpanded(true)}
      >
        <img 
          src={src} 
          alt={alt || "Image content"} 
          className="max-w-full max-h-[300px] object-contain"
        />
        <div className="absolute top-2 right-2 p-1.5 rounded bg-black/50 text-neutral-400 opacity-0 group-hover:opacity-100 transition-opacity">
          <Maximize2 size={14} />
        </div>
      </div>
      
      {isExpanded && (
        <div 
          className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-8"
          onClick={() => setIsExpanded(false)}
        >
          <div className="relative max-w-5xl max-h-full">
            <button
              onClick={() => setIsExpanded(false)}
              className="absolute -top-10 right-0 p-2 text-neutral-400 hover:text-white transition-colors"
            >
              <X size={24} />
            </button>
            <img
              src={src}
              alt={alt || "Image content"}
              className="max-w-full max-h-[85vh] rounded border border-neutral-800"
              onClick={(e) => e.stopPropagation()}
            />
          </div>
        </div>
      )}
    </>
  );
}

function ArtifactImage({ artifact }: { artifact: WorkflowArtifact }) {
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const imageUrl = `/api/workflow/artifacts/${artifact.artifact_id}`;

  return (
    <>
      <div 
        className="relative group cursor-pointer rounded border border-neutral-800/50 overflow-hidden bg-[#141414] hover:border-neutral-700 transition-colors"
        onClick={() => setIsExpanded(true)}
      >
        {error ? (
          <div className="p-4 text-red-400/80 text-sm text-center">Failed to load image</div>
        ) : (
          <div className="relative">
            <img
              src={imageUrl}
              alt={`${artifact.symbol} ${artifact.interval}`}
              className={`max-w-full max-h-[300px] object-contain transition-opacity ${loaded ? 'opacity-100' : 'opacity-0'}`}
              onLoad={() => setLoaded(true)}
              onError={() => setError(true)}
            />
            {!loaded && !error && (
              <div className="absolute inset-0 flex items-center justify-center h-32">
                <div className="w-5 h-5 border-2 border-neutral-700 border-t-neutral-500 rounded-full animate-spin" />
              </div>
            )}
            <div className="absolute top-2 right-2 p-1.5 rounded bg-black/50 text-neutral-400 opacity-0 group-hover:opacity-100 transition-opacity">
              <Maximize2 size={14} />
            </div>
          </div>
        )}
      </div>
      {isExpanded && (
        <div className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-8" onClick={() => setIsExpanded(false)}>
          <div className="relative max-w-5xl max-h-full">
            <button onClick={() => setIsExpanded(false)} className="absolute -top-10 right-0 p-2 text-neutral-400 hover:text-white transition-colors">
              <X size={24} />
            </button>
            <img src={imageUrl} alt={`${artifact.symbol} ${artifact.interval}`} className="max-w-full max-h-[85vh] rounded border border-neutral-800" onClick={(e) => e.stopPropagation()} />
          </div>
        </div>
      )}
    </>
  );
}

function MessageContent({ content, allArtifacts = [] }: { content: string | unknown[] | undefined; allArtifacts?: WorkflowArtifact[] }) {
  const usedArtifactIds = new Set<string>();
  
  const findMatchingArtifact = (meta: { symbol?: string; interval?: string } | undefined): WorkflowArtifact | undefined => {
    if (!meta?.symbol || !meta?.interval) {
      return allArtifacts.find(a => !usedArtifactIds.has(a.artifact_id));
    }
    
    const match = allArtifacts.find(
      a => a.symbol === meta.symbol && a.interval === meta.interval && !usedArtifactIds.has(a.artifact_id)
    );
    
    if (match) {
      usedArtifactIds.add(match.artifact_id);
      return match;
    }
    
    const fallback = allArtifacts.find(a => !usedArtifactIds.has(a.artifact_id));
    if (fallback) {
      usedArtifactIds.add(fallback.artifact_id);
    }
    return fallback;
  };
  
  if (!content) {
    return <span className="text-neutral-600 italic">(empty)</span>;
  }

  if (typeof content === 'string') {
    if (content.startsWith('data:image')) {
      return <ExpandableBase64Image src={content} />;
    }
    return <TextContent content={content} />;
  }

  if (Array.isArray(content)) {
    return (
      <div className="space-y-3">
        {content.map((item, idx) => {
          if (typeof item !== 'object' || item === null) {
            return <TextContent key={idx} content={String(item)} />;
          }
          
          const itemObj = item as Record<string, unknown>;
          
          if (itemObj.type === 'image_url') {
            const imageUrl = itemObj.image_url as { url?: string; detail?: string } | undefined;
            const url = imageUrl?.url || (itemObj.url as string);
            const artifactMeta = itemObj._artifact_meta as { symbol?: string; interval?: string } | undefined;
            
            if (url === '[IMAGE_ARTIFACT]') {
              const artifact = findMatchingArtifact(artifactMeta);
              if (artifact) {
                return <ArtifactImage key={idx} artifact={artifact} />;
              }
              return (
                <div key={idx} className="p-3 rounded bg-[#141414] border border-neutral-800/50 text-neutral-500 text-xs">
                  <span className="text-neutral-400">[Image]</span> Artifact not found
                  {artifactMeta && <span className="ml-2">({artifactMeta.symbol} {artifactMeta.interval})</span>}
                </div>
              );
            }
            
            if (url) {
              const isBase64 = url.startsWith('data:image');
              if (isBase64) {
                return <ExpandableBase64Image key={idx} src={url} />;
              }
              return (
                <div key={idx} className="p-3 rounded bg-[#141414] border border-neutral-800/50 text-neutral-500 text-xs">
                  <span className="text-neutral-400">[Image]</span> External URL
                </div>
              );
            }
          }
          
          if (itemObj.type === 'text') {
            const text = itemObj.text as string;
            if (text) {
              return <TextContent key={idx} content={text} />;
            }
          }
          
          return (
            <div key={idx} className="p-3 rounded bg-[#141414] border border-neutral-800/50 text-neutral-500 text-xs font-mono">
              {JSON.stringify(item, null, 2)}
            </div>
          );
        })}
      </div>
    );
  }

  if (typeof content === 'object') {
    return (
      <div className="p-3 rounded bg-[#141414] border border-neutral-800/50 text-neutral-400 text-xs font-mono">
        {JSON.stringify(content, null, 2)}
      </div>
    );
  }

  return <span className="text-neutral-600 italic">(unknown format)</span>;
}

function ExpandableImage({ artifact }: { artifact: WorkflowArtifact }) {
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);

  const imageUrl = `/api/workflow/artifacts/${artifact.artifact_id}`;

  return (
    <>
      <div 
        className="relative group cursor-pointer rounded border border-neutral-800/50 overflow-hidden bg-[#141414] hover:border-neutral-700 transition-colors"
        onClick={() => setIsExpanded(true)}
      >
        {error ? (
          <div className="p-4 text-red-400/80 text-sm text-center">
            Failed to load image
          </div>
        ) : (
          <div className="relative">
            <img
              src={imageUrl}
              alt={`${artifact.symbol} ${artifact.interval}`}
              className={`w-full transition-opacity ${loaded ? 'opacity-100' : 'opacity-0'}`}
              onLoad={() => setLoaded(true)}
              onError={() => setError(true)}
            />
            {!loaded && !error && (
              <div className="absolute inset-0 flex items-center justify-center h-32">
                <div className="w-5 h-5 border-2 border-neutral-700 border-t-neutral-500 rounded-full animate-spin" />
              </div>
            )}
            <div className="absolute top-2 right-2 p-1.5 rounded bg-black/50 text-neutral-400 opacity-0 group-hover:opacity-100 transition-opacity">
              <Maximize2 size={14} />
            </div>
          </div>
        )}
      </div>

      {isExpanded && (
        <div 
          className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-8"
          onClick={() => setIsExpanded(false)}
        >
          <div className="relative max-w-5xl max-h-full">
            <button
              onClick={() => setIsExpanded(false)}
              className="absolute -top-10 right-0 p-2 text-neutral-400 hover:text-white transition-colors"
            >
              <X size={24} />
            </button>
            <img
              src={imageUrl}
              alt={`${artifact.symbol} ${artifact.interval}`}
              className="max-w-full max-h-[85vh] rounded border border-neutral-800"
              onClick={(e) => e.stopPropagation()}
            />
          </div>
        </div>
      )}
    </>
  );
}

function MetadataRow({ label, value }: { label: string; value: string | undefined }) {
  const [copied, setCopied] = useState(false);
  
  if (!value) return null;
  
  const handleCopy = () => {
    navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  
  return (
    <div className="flex items-center justify-between py-1.5 group">
      <span className="text-xs text-neutral-500">{label}</span>
      <div className="flex items-center gap-2">
        <span className="text-xs font-mono text-neutral-400 truncate max-w-[200px]">{value}</span>
        <button
          onClick={handleCopy}
          className="p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-neutral-800 text-neutral-500 hover:text-neutral-300 transition-all"
        >
          {copied ? <Check size={10} className="text-emerald-400" /> : <Copy size={10} />}
        </button>
      </div>
    </div>
  );
}

export function DetailPanel({ selectedNode, allArtifacts = [] }: DetailPanelProps) {
  if (!selectedNode) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-neutral-500 gap-3 bg-[#1a1a1a]">
        <Workflow size={40} className="opacity-20" />
        <p className="text-sm">Select a node to view details</p>
      </div>
    );
  }

  const renderSpanDetail = (data: WorkflowSpan) => {
    return (
      <div className="space-y-6">
        <SectionLabel>Input</SectionLabel>
        <div className="p-4 rounded bg-[#141414] border border-neutral-800/50 text-neutral-500 text-sm italic">
          Span inputs are inherited from parent context
        </div>

        <SectionLabel>Output</SectionLabel>
        {data.output_summary ? (
          <JsonViewer data={data.output_summary} />
        ) : (
          <div className="p-4 rounded bg-[#141414] border border-neutral-800/50 text-neutral-500 text-sm italic">
            No output data
          </div>
        )}

        {data.error && (
          <>
            <SectionLabel>Error</SectionLabel>
            <div className="p-4 rounded bg-red-950/30 border border-red-900/30 text-red-400 text-sm font-mono">
              {data.error}
            </div>
          </>
        )}

        <CollapsibleSection label="Metadata">
          <div className="px-1">
            <MetadataRow label="Span ID" value={data.span_id} />
            <MetadataRow label="Parent Span ID" value={data.parent_span_id} />
            <MetadataRow label="Start Time" value={data.start_time ? formatTime(data.start_time) : undefined} />
            <MetadataRow label="End Time" value={data.end_time ? formatTime(data.end_time) : undefined} />
            {data.symbol && <MetadataRow label="Symbol" value={data.symbol} />}
          </div>
        </CollapsibleSection>
      </div>
    );
  };

  const renderModelDetail = (before: WorkflowSpanChild, after?: WorkflowSpanChild) => {
    const beforePayload = before.payload as Record<string, unknown> | undefined;
    const afterPayload = after?.payload as Record<string, unknown> | undefined;

    const recentMessages = (beforePayload?.recent_messages || []) as MessageItem[];
    const toolCalls = (afterPayload?.tool_calls || []) as ToolCallItem[];
    const responseContent = afterPayload?.response_content as string | undefined;
    
    const modelSpanId = beforePayload?.model_span_id as string | undefined;
    let durationMs = 0;
    if (before.ts && after?.ts) {
      const start = new Date(before.ts).getTime();
      const end = new Date(after.ts).getTime();
      durationMs = end - start;
    }

    return (
      <div className="space-y-6">
        <SectionLabel>Input</SectionLabel>
        {recentMessages.length > 0 ? (
          <div className="space-y-3">
            {recentMessages.map((msg, idx) => (
              <div key={idx} className="space-y-1">
                <div className="text-[10px] font-medium text-neutral-500 uppercase">
                  {msg.role}
                </div>
                <MessageContent content={msg.content} allArtifacts={allArtifacts} />
                {msg.tool_calls && msg.tool_calls.length > 0 && (
                  <div className="mt-2 p-3 rounded bg-[#141414] border border-neutral-800/50">
                    <div className="text-[10px] text-neutral-500 mb-2">Tool Calls:</div>
                    {msg.tool_calls.map((tc, i) => (
                      <div key={i} className="text-xs font-mono text-neutral-400">
                        {tc.name}({tc.args ? Object.entries(tc.args).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(', ') : tc.args_keys?.join(', ') || ''})
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="p-4 rounded bg-[#141414] border border-neutral-800/50 text-neutral-500 text-sm italic">
            No input messages
          </div>
        )}

        <SectionLabel>Output</SectionLabel>
        {!after ? (
          <div className="p-4 rounded bg-[#141414] border border-neutral-800/50 text-neutral-400 text-sm">
            Waiting for response...
          </div>
        ) : responseContent ? (
          <TextContent content={responseContent} />
        ) : toolCalls.length > 0 ? (
          <div className="space-y-3">
            {toolCalls.map((tc, idx) => (
              <div key={idx} className="rounded bg-[#141414] border border-neutral-800/50 overflow-hidden">
                <div className="px-3 py-2 border-b border-neutral-800/50 flex items-center justify-between">
                  <span className="text-sm font-mono text-neutral-300">{tc.name}</span>
                  {tc.id && <span className="text-xs font-mono text-neutral-600">{tc.id}</span>}
                </div>
                <div className="p-3">
                  <JsonViewer data={tc.args} />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="p-4 rounded bg-[#141414] border border-neutral-800/50 text-neutral-500 text-sm italic">
            No output content
          </div>
        )}

        <CollapsibleSection label="Metadata">
          <div className="px-1">
            <MetadataRow label="Model Span ID" value={modelSpanId} />
            <MetadataRow label="Start Time" value={before.ts ? formatTime(before.ts) : undefined} />
            <MetadataRow label="End Time" value={after?.ts ? formatTime(after.ts) : undefined} />
            <MetadataRow label="Duration" value={durationMs > 0 ? `${durationMs}ms` : undefined} />
            <MetadataRow label="Total Messages" value={String(beforePayload?.total_messages || 0)} />
          </div>
        </CollapsibleSection>
      </div>
    );
  };

  const renderToolDetail = (data: WorkflowSpanChild) => {
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
        <SectionLabel>Input</SectionLabel>
        {input ? (
          <JsonViewer data={input} />
        ) : (
          <div className="p-4 rounded bg-[#141414] border border-neutral-800/50 text-neutral-500 text-sm italic">
            No input arguments
          </div>
        )}

        <SectionLabel>Output</SectionLabel>
        {isKlineImageTool && matchingArtifact ? (
          <div className="space-y-4">
            <ExpandableImage artifact={matchingArtifact} />
            <JsonViewer data={{
              success: output?.success,
              symbol: output?.symbol,
              intervals: output?.intervals,
              kline_count: output?.kline_count,
            }} />
          </div>
        ) : output ? (
          <JsonViewer data={output} />
        ) : (
          <div className="p-4 rounded bg-[#141414] border border-neutral-800/50 text-neutral-500 text-sm italic">
            No output data
          </div>
        )}

        {data.error && (
          <>
            <SectionLabel>Error</SectionLabel>
            <div className="p-4 rounded bg-red-950/30 border border-red-900/30 text-red-400 text-sm font-mono">
              {data.error}
            </div>
          </>
        )}

        <CollapsibleSection label="Metadata">
          <div className="px-1">
            <MetadataRow label="Model Span ID" value={data.model_span_id} />
            <MetadataRow label="Timestamp" value={data.ts ? formatTime(data.ts) : undefined} />
            <MetadataRow label="Duration" value={data.duration_ms ? `${data.duration_ms}ms` : undefined} />
            {data.symbol && <MetadataRow label="Symbol" value={data.symbol} />}
          </div>
        </CollapsibleSection>
      </div>
    );
  };

  const getNodeName = (): string => {
    switch (selectedNode.type) {
      case 'span':
        return selectedNode.data.node;
      case 'model':
        return 'ChatOpenAI';
      case 'tool':
        return selectedNode.data.tool_name || 'Tool';
      default:
        return 'Unknown';
    }
  };

  const getDuration = (): number | undefined => {
    switch (selectedNode.type) {
      case 'span':
        return selectedNode.data.duration_ms;
      case 'model': {
        const { before, after } = selectedNode.data;
        if (before.ts && after?.ts) {
          return new Date(after.ts).getTime() - new Date(before.ts).getTime();
        }
        return undefined;
      }
      case 'tool':
        return selectedNode.data.duration_ms;
      default:
        return undefined;
    }
  };

  const getStatus = (): string | undefined => {
    switch (selectedNode.type) {
      case 'span':
        return selectedNode.data.status;
      case 'model':
        return selectedNode.data.after ? 'success' : 'running';
      case 'tool':
        return selectedNode.data.status;
      default:
        return undefined;
    }
  };

  const nodeName = getNodeName();
  const duration = getDuration();
  const status = getStatus();

  return (
    <div className="h-full flex flex-col bg-[#1a1a1a]">
      <div className="flex items-center justify-between px-5 py-4 border-b border-neutral-800/50">
        <h2 className="text-lg font-semibold text-white">{nodeName}</h2>
        <div className="flex items-center gap-2">
          {status === 'error' && (
            <span className="text-xs text-red-400">error</span>
          )}
          {duration !== undefined && (
            <span className="text-xs text-neutral-500 font-mono">
              {formatDuration(duration)}
            </span>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-5">
        {selectedNode.type === 'span' && renderSpanDetail(selectedNode.data)}
        {selectedNode.type === 'model' && renderModelDetail(selectedNode.data.before, selectedNode.data.after)}
        {selectedNode.type === 'tool' && renderToolDetail(selectedNode.data)}
      </div>
    </div>
  );
}
