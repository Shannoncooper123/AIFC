import { Loader2, Square, CheckCircle, XCircle, Clock, TrendingUp, TrendingDown, Target, BarChart3, Activity, Zap, AlertTriangle, ArrowUpCircle, ArrowDownCircle } from 'lucide-react';
import { Card, Button } from '../../../components/ui';

interface RuntimeStats {
  completed_steps: number;
  total_steps: number;
  elapsed_seconds: number;
  avg_step_duration: number;
  recent_avg_duration: number;
  recent_min_duration: number;
  recent_max_duration: number;
  throughput_per_min: number;
  timeout_count: number;
  error_count: number;
}

interface SideStats {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  total_pnl: number;
  win_rate: number;
  avg_win: number;
  avg_loss: number;
}

interface BacktestProgressProps {
  backtestId: string;
  status: string;
  progress?: {
    current_time?: string;
    total_steps: number;
    completed_steps: number;
    progress_percent: number;
    current_step_info?: string;
    completed_batches?: number;
    total_batches?: number;
    total_trades?: number;
    winning_trades?: number;
    losing_trades?: number;
    total_pnl?: number;
    win_rate?: number;
    runtime_stats?: RuntimeStats;
    long_stats?: SideStats;
    short_stats?: SideStats;
  };
  onStop?: () => void;
}

export function BacktestProgress({ backtestId, status, progress, onStop }: BacktestProgressProps) {
  const isRunning = status === 'running';
  const isCompleted = status === 'completed';
  const isFailed = status === 'failed';
  const isCancelled = status === 'cancelled';

  const getStatusIcon = () => {
    if (isRunning) return <Loader2 className="h-5 w-5 text-blue-400 animate-spin" />;
    if (isCompleted) return <CheckCircle className="h-5 w-5 text-emerald-400" />;
    if (isFailed) return <XCircle className="h-5 w-5 text-rose-400" />;
    if (isCancelled) return <Square className="h-5 w-5 text-yellow-400" />;
    return <Clock className="h-5 w-5 text-neutral-400" />;
  };

  const getStatusText = () => {
    if (isRunning) return 'Running...';
    if (isCompleted) return 'Completed';
    if (isFailed) return 'Failed';
    if (isCancelled) return 'Cancelled';
    return 'Pending';
  };

  const getStatusColor = () => {
    if (isRunning) return 'text-blue-400';
    if (isCompleted) return 'text-emerald-400';
    if (isFailed) return 'text-rose-400';
    if (isCancelled) return 'text-yellow-400';
    return 'text-neutral-400';
  };

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
  };

  const formatPercent = (value: number) => {
    return `${(value * 100).toFixed(1)}%`;
  };

  const totalPnl = progress?.total_pnl ?? 0;
  const isProfitable = totalPnl >= 0;

  return (
    <Card>
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {getStatusIcon()}
            <div>
              <div className={`font-medium ${getStatusColor()}`}>{getStatusText()}</div>
              <div className="text-xs text-neutral-500">ID: {backtestId}</div>
            </div>
          </div>
          {isRunning && onStop && (
            <Button variant="secondary" size="sm" onClick={onStop}>
              <Square className="h-4 w-4 mr-1" />
              Stop
            </Button>
          )}
        </div>

        {progress && (
          <>
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-neutral-400">Progress</span>
                <span className="text-white">
                  {progress.completed_batches ?? 0} / {progress.total_batches ?? 0} steps
                </span>
              </div>
              <div className="h-2 bg-neutral-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-blue-500 transition-all duration-300"
                  style={{ width: `${progress.progress_percent}%` }}
                />
              </div>
              <div className="text-xs text-neutral-500 text-right">
                {progress.progress_percent.toFixed(1)}%
              </div>
            </div>

            {isRunning && (progress.total_trades ?? 0) > 0 && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 pt-2 border-t border-neutral-800">
                <div className="p-2 rounded-lg bg-neutral-800/50">
                  <div className="flex items-center gap-1 text-neutral-400 text-xs mb-1">
                    <BarChart3 className="h-3 w-3" />
                    Trades
                  </div>
                  <div className="text-lg font-semibold text-white">
                    {progress.total_trades ?? 0}
                  </div>
                </div>

                <div className="p-2 rounded-lg bg-neutral-800/50">
                  <div className="flex items-center gap-1 text-neutral-400 text-xs mb-1">
                    <Target className="h-3 w-3" />
                    Win Rate
                  </div>
                  <div className="text-lg font-semibold text-white">
                    {formatPercent(progress.win_rate ?? 0)}
                  </div>
                </div>

                <div className="p-2 rounded-lg bg-neutral-800/50">
                  <div className="flex items-center gap-1 text-xs mb-1">
                    <TrendingUp className="h-3 w-3 text-emerald-400" />
                    <span className="text-emerald-400">Wins</span>
                  </div>
                  <div className="text-lg font-semibold text-emerald-400">
                    {progress.winning_trades ?? 0}
                  </div>
                </div>

                <div className="p-2 rounded-lg bg-neutral-800/50">
                  <div className="flex items-center gap-1 text-xs mb-1">
                    <TrendingDown className="h-3 w-3 text-rose-400" />
                    <span className="text-rose-400">Losses</span>
                  </div>
                  <div className="text-lg font-semibold text-rose-400">
                    {progress.losing_trades ?? 0}
                  </div>
                </div>
              </div>
            )}

            {isRunning && (progress.total_trades ?? 0) > 0 && (
              <div className="p-3 rounded-lg bg-neutral-800/50 border border-neutral-700/50">
                <div className="flex items-center justify-between">
                  <div className="text-sm text-neutral-400">Cumulative P&L</div>
                  <div className={`text-xl font-bold ${isProfitable ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {isProfitable ? '+' : ''}{formatCurrency(totalPnl)}
                  </div>
                </div>
              </div>
            )}

            {isRunning && (progress.long_stats || progress.short_stats) && (
              <div className="grid grid-cols-2 gap-3 pt-2">
                <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
                  <div className="flex items-center gap-2 mb-2">
                    <ArrowUpCircle className="h-4 w-4 text-emerald-400" />
                    <span className="text-emerald-400 text-sm font-medium">Long</span>
                    <span className="text-neutral-500 text-xs">({progress.long_stats?.total_trades ?? 0})</span>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <div className="text-neutral-500">P&L</div>
                      <div className={`font-semibold ${(progress.long_stats?.total_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {formatCurrency(progress.long_stats?.total_pnl ?? 0)}
                      </div>
                    </div>
                    <div>
                      <div className="text-neutral-500">Win Rate</div>
                      <div className="font-semibold text-white">
                        {formatPercent(progress.long_stats?.win_rate ?? 0)}
                      </div>
                    </div>
                    <div>
                      <div className="text-neutral-500">W/L</div>
                      <div className="font-semibold">
                        <span className="text-emerald-400">{progress.long_stats?.winning_trades ?? 0}</span>
                        <span className="text-neutral-500">/</span>
                        <span className="text-rose-400">{progress.long_stats?.losing_trades ?? 0}</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20">
                  <div className="flex items-center gap-2 mb-2">
                    <ArrowDownCircle className="h-4 w-4 text-rose-400" />
                    <span className="text-rose-400 text-sm font-medium">Short</span>
                    <span className="text-neutral-500 text-xs">({progress.short_stats?.total_trades ?? 0})</span>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <div className="text-neutral-500">P&L</div>
                      <div className={`font-semibold ${(progress.short_stats?.total_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {formatCurrency(progress.short_stats?.total_pnl ?? 0)}
                      </div>
                    </div>
                    <div>
                      <div className="text-neutral-500">Win Rate</div>
                      <div className="font-semibold text-white">
                        {formatPercent(progress.short_stats?.win_rate ?? 0)}
                      </div>
                    </div>
                    <div>
                      <div className="text-neutral-500">W/L</div>
                      <div className="font-semibold">
                        <span className="text-emerald-400">{progress.short_stats?.winning_trades ?? 0}</span>
                        <span className="text-neutral-500">/</span>
                        <span className="text-rose-400">{progress.short_stats?.losing_trades ?? 0}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {progress.current_time && (
              <div className="text-sm">
                <span className="text-neutral-400">Current Time: </span>
                <span className="text-white">
                  {new Date(progress.current_time).toLocaleString()}
                </span>
              </div>
            )}

            {progress.current_step_info && (
              <div className="text-sm text-neutral-400">{progress.current_step_info}</div>
            )}

            {isRunning && progress.runtime_stats && (
              <div className="pt-3 border-t border-neutral-800">
                <div className="text-xs text-neutral-500 mb-2 flex items-center gap-1">
                  <Activity className="h-3 w-3" />
                  Runtime Diagnostics
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                  <div className="p-2 rounded bg-neutral-800/50">
                    <div className="text-neutral-500">Throughput</div>
                    <div className="text-white font-medium flex items-center gap-1">
                      <Zap className="h-3 w-3 text-yellow-400" />
                      {progress.runtime_stats.throughput_per_min.toFixed(1)}/min
                    </div>
                  </div>
                  <div className="p-2 rounded bg-neutral-800/50">
                    <div className="text-neutral-500">Avg Duration</div>
                    <div className="text-white font-medium">
                      {progress.runtime_stats.avg_step_duration.toFixed(1)}s
                    </div>
                  </div>
                  <div className="p-2 rounded bg-neutral-800/50">
                    <div className="text-neutral-500">Recent Avg</div>
                    <div className="text-white font-medium">
                      {progress.runtime_stats.recent_avg_duration.toFixed(1)}s
                    </div>
                  </div>
                  <div className="p-2 rounded bg-neutral-800/50">
                    <div className="text-neutral-500">Recent Range</div>
                    <div className="text-white font-medium">
                      {progress.runtime_stats.recent_min_duration.toFixed(0)}-{progress.runtime_stats.recent_max_duration.toFixed(0)}s
                    </div>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-2 mt-2 text-xs">
                  <div className="p-2 rounded bg-neutral-800/50">
                    <div className="text-neutral-500">Elapsed</div>
                    <div className="text-white font-medium">
                      {Math.floor(progress.runtime_stats.elapsed_seconds / 60)}m {Math.floor(progress.runtime_stats.elapsed_seconds % 60)}s
                    </div>
                  </div>
                  <div className="p-2 rounded bg-neutral-800/50">
                    <div className="text-neutral-500 flex items-center gap-1">
                      <AlertTriangle className="h-3 w-3 text-yellow-500" />
                      Timeouts
                    </div>
                    <div className={`font-medium ${progress.runtime_stats.timeout_count > 0 ? 'text-yellow-400' : 'text-white'}`}>
                      {progress.runtime_stats.timeout_count}
                    </div>
                  </div>
                  <div className="p-2 rounded bg-neutral-800/50">
                    <div className="text-neutral-500 flex items-center gap-1">
                      <XCircle className="h-3 w-3 text-rose-500" />
                      Errors
                    </div>
                    <div className={`font-medium ${progress.runtime_stats.error_count > 0 ? 'text-rose-400' : 'text-white'}`}>
                      {progress.runtime_stats.error_count}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </>
        )}

        {!progress && isRunning && (
          <div className="text-sm text-neutral-400 animate-pulse">
            Initializing backtest...
          </div>
        )}
      </div>
    </Card>
  );
}
