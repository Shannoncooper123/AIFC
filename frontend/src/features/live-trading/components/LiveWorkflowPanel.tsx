import { useState, useEffect, useCallback } from 'react';
import { Play, Square, RefreshCw, Activity, Clock } from 'lucide-react';
import {
  startSymbolWorkflow,
  stopSymbolWorkflow,
  getRunningWorkflows,
  getWorkflowStatus,
  type WorkflowStatus,
  type AllWorkflowStatus,
} from '../../../services/api/live';
import { formatTime } from '../../../utils';

const INTERVALS = [
  { value: '1m', label: '1 分钟' },
  { value: '5m', label: '5 分钟' },
  { value: '15m', label: '15 分钟' },
  { value: '30m', label: '30 分钟' },
  { value: '1h', label: '1 小时' },
  { value: '4h', label: '4 小时' },
];

interface LiveWorkflowPanelProps {
  onWorkflowChange?: () => void;
}

export function LiveWorkflowPanel({ onWorkflowChange }: LiveWorkflowPanelProps) {
  const [symbol, setSymbol] = useState('BTCUSDT');
  const [selectedInterval, setSelectedInterval] = useState('15m');
  const [loading, setLoading] = useState(false);
  const [starting, setStarting] = useState(false);
  const [runningSymbols, setRunningSymbols] = useState<string[]>([]);
  const [workflowStatuses, setWorkflowStatuses] = useState<Record<string, WorkflowStatus>>({});
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      setLoading(true);
      const [running, status] = await Promise.all([
        getRunningWorkflows(),
        getWorkflowStatus(),
      ]);
      setRunningSymbols(running.symbols);
      if ('symbols' in status) {
        setWorkflowStatuses((status as AllWorkflowStatus).symbols);
      }
      setError(null);
    } catch (err) {
      console.error('Failed to fetch workflow status:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const timer = setInterval(fetchStatus, 5000);
    return () => clearInterval(timer);
  }, [fetchStatus]);

  const handleStart = async () => {
    if (!symbol.trim()) {
      setError('请输入交易对');
      return;
    }

    try {
      setStarting(true);
      setError(null);
      await startSymbolWorkflow(symbol.toUpperCase(), selectedInterval);
      await fetchStatus();
      onWorkflowChange?.();
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : '启动失败';
      setError(errorMessage);
    } finally {
      setStarting(false);
    }
  };

  const handleStop = async (sym: string) => {
    try {
      await stopSymbolWorkflow(sym);
      await fetchStatus();
      onWorkflowChange?.();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : `停止 ${sym} workflow 失败`;
      setError(msg);
      console.error('Failed to stop workflow:', err);
    }
  };

  return (
    <div className="rounded-xl border border-neutral-800 bg-[#1a1a1a] p-6">
      <div className="mb-6 flex items-center gap-3">
        <Activity className="h-5 w-5 text-blue-400" />
        <h3 className="text-lg font-semibold text-white">Workflow 分析</h3>
        <span className="text-sm text-neutral-400">
          针对单个币种，每根K线触发 Agent 分析
        </span>
      </div>

      {error && (
        <div className="mb-4 rounded-lg bg-rose-500/10 border border-rose-500/30 p-3 text-sm text-rose-400">
          {error}
        </div>
      )}

      <div className="flex flex-wrap items-end gap-4 mb-6">
        <div className="flex-1 min-w-[200px]">
          <label className="block text-sm font-medium text-neutral-400 mb-2">
            交易对
          </label>
          <input
            type="text"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            placeholder="如 BTCUSDT"
            className="w-full rounded-lg border border-neutral-700 bg-neutral-800 px-4 py-2.5 text-white placeholder-neutral-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>

        <div className="w-40">
          <label className="block text-sm font-medium text-neutral-400 mb-2">
            K线周期
          </label>
          <select
            value={selectedInterval}
            onChange={(e) => setSelectedInterval(e.target.value)}
            className="w-full rounded-lg border border-neutral-700 bg-neutral-800 px-4 py-2.5 text-white focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            {INTERVALS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        <button
          onClick={handleStart}
          disabled={starting || !symbol.trim()}
          className="flex items-center gap-2 rounded-lg bg-emerald-600 px-6 py-2.5 text-sm font-medium text-white hover:bg-emerald-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {starting ? (
            <RefreshCw className="h-4 w-4 animate-spin" />
          ) : (
            <Play className="h-4 w-4" />
          )}
          启动分析
        </button>
      </div>

      <div>
        <div className="flex items-center justify-between mb-3">
          <h4 className="text-sm font-medium text-neutral-400">
            运行中的 Workflow ({runningSymbols.length})
          </h4>
          <button
            onClick={fetchStatus}
            disabled={loading}
            className="text-neutral-400 hover:text-white transition-colors"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {runningSymbols.length === 0 ? (
          <div className="text-center py-8 text-neutral-500">
            <Activity className="h-8 w-8 mx-auto mb-2 opacity-30" />
            <p>暂无运行中的 Workflow</p>
            <p className="text-xs mt-1">输入交易对并点击"启动分析"开始</p>
          </div>
        ) : (
          <div className="space-y-2">
            {runningSymbols.map((sym) => {
              const status = workflowStatuses[sym];
              return (
                <div
                  key={sym}
                  className="flex items-center justify-between rounded-lg border border-neutral-700 bg-neutral-800/50 px-4 py-3"
                >
                  <div className="flex items-center gap-4">
                    <div className="flex items-center gap-2">
                      <span className="relative flex h-2 w-2">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                      </span>
                      <span className="font-medium text-white">{sym}</span>
                    </div>
                    {status && (
                      <>
                        <span className="text-sm text-neutral-400">
                          @ {status.interval}
                        </span>
                        <span className="flex items-center gap-1 text-sm text-neutral-400">
                          <Clock className="h-3 w-3" />
                          {status.workflow_count} 次分析
                        </span>
                        {status.last_kline_time && (
                          <span className="text-xs text-neutral-500">
                            最后: {formatTime(status.last_kline_time)}
                          </span>
                        )}
                      </>
                    )}
                  </div>
                  <button
                    onClick={() => handleStop(sym)}
                    className="flex items-center gap-1 rounded bg-rose-500/20 px-3 py-1.5 text-xs font-medium text-rose-400 hover:bg-rose-500/30 transition-colors"
                  >
                    <Square className="h-3 w-3" />
                    停止
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
