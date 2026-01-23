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
          className={`w-full text-left p-3 rounded-lg border transition ${
            selectedRunId === run.run_id
              ? 'border-blue-500 bg-slate-800'
              : 'border-slate-700 hover:border-slate-500'
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-white font-mono text-xs truncate max-w-[120px]">
              {run.run_id.replace('run_', '')}
            </span>
            <span
              className={`text-xs ${
                run.status === 'success' ? 'text-green-400' : 'text-red-400'
              }`}
            >
              {run.status || '—'}
            </span>
          </div>
          <div className="text-xs text-slate-400 mt-1">
            {formatTime(run.start_time)}
          </div>
          <div className="flex flex-wrap gap-1 mt-2">
            {run.symbols.slice(0, 3).map((s) => (
              <span
                key={s}
                className="text-xs px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-300"
              >
                {s.replace('USDT', '')}
              </span>
            ))}
            {run.symbols.length > 3 && (
              <span className="text-xs text-slate-500">
                +{run.symbols.length - 3}
              </span>
            )}
          </div>
          <div className="flex items-center gap-3 mt-2 text-xs text-slate-500">
            <span>⏱️ {formatDuration(run.duration_ms)}</span>
            <span>🔧 {run.tool_calls_count}</span>
            <span>🤖 {run.model_calls_count}</span>
          </div>
        </button>
      ))}
    </div>
  );
}
