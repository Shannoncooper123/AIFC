import { Loader2, Square, CheckCircle, XCircle, Clock, TrendingUp, TrendingDown, Target, BarChart3 } from 'lucide-react';
import { Card, Button } from '../../../components/ui';

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
                  {progress.completed_batches ?? 0} / {progress.total_batches ?? 0} batches
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
