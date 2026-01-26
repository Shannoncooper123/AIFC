import type { WorkflowTimeline } from '../../../types';
import { formatTime, formatDuration } from '../../../utils';
import { getStatusColor, getStatusBgColor } from '../utils/workflowHelpers';

interface RunOverviewProps {
  runId: string;
  timeline: WorkflowTimeline;
  artifactsCount: number;
  uniqueSymbols: string[];
  selectedSymbol: string | null;
  onSymbolSelect: (symbol: string | null) => void;
}

export function RunOverview({
  runId,
  timeline,
  artifactsCount,
  uniqueSymbols,
  selectedSymbol,
  onSymbolSelect,
}: RunOverviewProps) {
  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="text-white font-semibold">运行概览</div>
          <div className="text-xs text-neutral-500 mt-1 font-mono">{runId}</div>
        </div>
        <div
          className={`px-3 py-1 rounded text-sm ${getStatusBgColor(timeline.status || 'unknown')}`}
        >
          <span className={getStatusColor(timeline.status || 'unknown')}>
            {timeline.status || 'unknown'}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
        <div>
          <div className="text-neutral-400">开始时间</div>
          <div className="text-white mt-1">{formatTime(timeline.start_time)}</div>
        </div>
        <div>
          <div className="text-neutral-400">总耗时</div>
          <div className="text-white mt-1">
            {formatDuration(timeline.duration_ms)}
          </div>
        </div>
        <div>
          <div className="text-neutral-400">节点数</div>
          <div className="text-white mt-1">{timeline.traces.length}</div>
        </div>
        <div>
          <div className="text-neutral-400">图像数</div>
          <div className="text-white mt-1">{artifactsCount}</div>
        </div>
      </div>

      {uniqueSymbols.length > 0 && (
        <div className="mt-4">
          <div className="text-neutral-400 text-sm mb-2">币种筛选</div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => onSymbolSelect(null)}
              className={`px-2 py-1 text-xs rounded border transition-all duration-200 ${
                selectedSymbol === null
                  ? 'bg-neutral-700/50 border-neutral-500 text-white'
                  : 'border-neutral-700 text-neutral-400 hover:border-neutral-600'
              }`}
            >
              全部
            </button>
            {uniqueSymbols.map((symbol) => (
              <button
                key={symbol}
                onClick={() => onSymbolSelect(symbol)}
                className={`px-2 py-1 text-xs rounded border transition-all duration-200 ${
                  selectedSymbol === symbol
                    ? 'bg-neutral-700/50 border-neutral-500 text-white'
                    : 'border-neutral-700 text-neutral-400 hover:border-neutral-600'
                }`}
              >
                {symbol}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
