import type { WorkflowRunSummary } from '../../../types';
import { formatTime, formatDuration } from '../../../utils';

interface RunsListProps {
  runs: WorkflowRunSummary[];
  selectedRunId: string | null;
  onSelectRun: (runId: string) => void;
}

export function RunsList({ runs, selectedRunId, onSelectRun }: RunsListProps) {
  return (
    <div className="space-y-2 max-h-[calc(100vh-200px)] overflow-y-auto">
      {runs.map((run) => (
        <button
          key={run.run_id}
          onClick={() => onSelectRun(run.run_id)}
          className={`w-full text-left p-3 rounded-lg border transition-all duration-200 ${
            selectedRunId === run.run_id
              ? 'border-neutral-500 bg-[#1a1a1a]'
              : 'border-neutral-800 hover:border-neutral-600'
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-white font-mono text-xs truncate max-w-[120px]">
              {run.run_id.replace('run_', '')}
            </span>
            <span
              className={`text-xs ${
                run.status === 'success' ? 'text-emerald-500/80' : 'text-rose-500/80'
              }`}
            >
              {run.status || '—'}
            </span>
          </div>
          <div className="text-xs text-neutral-400 mt-1">
            {formatTime(run.start_time)}
          </div>
          <div className="flex flex-wrap gap-1 mt-2">
            {run.symbols.slice(0, 3).map((s) => (
              <span
                key={s}
                className="text-xs px-1.5 py-0.5 rounded bg-neutral-700/50 text-neutral-300"
              >
                {s.replace('USDT', '')}
              </span>
            ))}
            {run.symbols.length > 3 && (
              <span className="text-xs text-neutral-500">
                +{run.symbols.length - 3}
              </span>
            )}
          </div>
          <div className="flex items-center gap-3 mt-2 text-xs text-neutral-500">
            <span>⏱️ {formatDuration(run.duration_ms)}</span>
            <span>🔧 {run.tool_calls_count}</span>
            <span>🤖 {run.model_calls_count}</span>
          </div>
        </button>
      ))}
    </div>
  );
}
