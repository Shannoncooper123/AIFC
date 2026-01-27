import { TrendingUp, TrendingDown, Target, BarChart3, DollarSign, Percent, Activity, Scale } from 'lucide-react';
import { Card } from '../../../components/ui';

interface BacktestResultsProps {
  result: {
    total_trades: number;
    winning_trades: number;
    losing_trades: number;
    total_pnl: number;
    win_rate: number;
    return_rate: number;
    final_balance: number;
    avg_win?: number;
    avg_loss?: number;
    profit_factor?: number;
    max_drawdown?: number;
    total_klines_analyzed?: number;
    completed_batches?: number;
    total_batches?: number;
    config: {
      initial_balance: number;
      concurrency?: number;
    };
  };
}

export function BacktestResults({ result }: BacktestResultsProps) {
  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
  };

  const formatPercent = (value: number) => {
    return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
  };

  const isProfitable = result.total_pnl >= 0;
  const profitFactor = result.profit_factor ?? 0;

  return (
    <Card>
      <div className="space-y-6">
        <div className="flex items-center gap-2 text-white font-medium">
          <BarChart3 className="h-5 w-5 text-blue-400" />
          Backtest Results
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="p-4 rounded-lg bg-neutral-800/50">
            <div className="flex items-center gap-2 text-neutral-400 text-sm mb-1">
              <DollarSign className="h-4 w-4" />
              Total P&L
            </div>
            <div
              className={`text-xl font-semibold ${
                isProfitable ? 'text-emerald-400' : 'text-rose-400'
              }`}
            >
              {formatCurrency(result.total_pnl)}
            </div>
          </div>

          <div className="p-4 rounded-lg bg-neutral-800/50">
            <div className="flex items-center gap-2 text-neutral-400 text-sm mb-1">
              <Percent className="h-4 w-4" />
              Return Rate
            </div>
            <div
              className={`text-xl font-semibold ${
                result.return_rate >= 0 ? 'text-emerald-400' : 'text-rose-400'
              }`}
            >
              {formatPercent(result.return_rate)}
            </div>
          </div>

          <div className="p-4 rounded-lg bg-neutral-800/50">
            <div className="flex items-center gap-2 text-neutral-400 text-sm mb-1">
              <Target className="h-4 w-4" />
              Win Rate
            </div>
            <div className="text-xl font-semibold text-white">
              {(result.win_rate * 100).toFixed(1)}%
            </div>
          </div>

          <div className="p-4 rounded-lg bg-neutral-800/50">
            <div className="flex items-center gap-2 text-neutral-400 text-sm mb-1">
              <Scale className="h-4 w-4" />
              Profit Factor
            </div>
            <div className={`text-xl font-semibold ${profitFactor >= 1 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {profitFactor.toFixed(2)}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="p-4 rounded-lg bg-neutral-800/50">
            <div className="flex items-center gap-2 text-neutral-400 text-sm mb-1">
              <BarChart3 className="h-4 w-4" />
              Total Trades
            </div>
            <div className="text-xl font-semibold text-white">{result.total_trades}</div>
          </div>

          <div className="p-4 rounded-lg bg-neutral-800/50">
            <div className="text-neutral-400 text-sm mb-1">Winning Trades</div>
            <div className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-emerald-400" />
              <span className="text-lg font-medium text-emerald-400">{result.winning_trades}</span>
            </div>
          </div>

          <div className="p-4 rounded-lg bg-neutral-800/50">
            <div className="text-neutral-400 text-sm mb-1">Losing Trades</div>
            <div className="flex items-center gap-2">
              <TrendingDown className="h-4 w-4 text-rose-400" />
              <span className="text-lg font-medium text-rose-400">{result.losing_trades}</span>
            </div>
          </div>

          <div className="p-4 rounded-lg bg-neutral-800/50">
            <div className="text-neutral-400 text-sm mb-1">K-lines Analyzed</div>
            <div className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-blue-400" />
              <span className="text-lg font-medium text-white">{result.total_klines_analyzed ?? 0}</span>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="p-4 rounded-lg bg-neutral-800/50">
            <div className="text-neutral-400 text-sm mb-1">Avg Win</div>
            <div className="text-lg font-medium text-emerald-400">
              {formatCurrency(result.avg_win ?? 0)}
            </div>
          </div>

          <div className="p-4 rounded-lg bg-neutral-800/50">
            <div className="text-neutral-400 text-sm mb-1">Avg Loss</div>
            <div className="text-lg font-medium text-rose-400">
              {formatCurrency(result.avg_loss ?? 0)}
            </div>
          </div>

          <div className="p-4 rounded-lg bg-neutral-800/50">
            <div className="text-neutral-400 text-sm mb-1">Max Drawdown</div>
            <div className="text-lg font-medium text-rose-400">
              {formatCurrency(result.max_drawdown ?? 0)}
            </div>
          </div>

          <div className="p-4 rounded-lg bg-neutral-800/50">
            <div className="text-neutral-400 text-sm mb-1">Final Balance</div>
            <div className="text-lg font-medium text-white">{formatCurrency(result.final_balance)}</div>
            <div className="text-xs text-neutral-500">
              Started: {formatCurrency(result.config.initial_balance)}
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
}
