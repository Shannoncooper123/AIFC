import { Activity, Trophy, Target, TrendingUp, TrendingDown } from 'lucide-react';
import type { PositionsSummary } from '../../../types';
import { Card } from '../../../components/ui';

interface SummaryCardProps {
  summary: PositionsSummary;
}

export function SummaryCard({ summary }: SummaryCardProps) {
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

  const totalPnl = summary.total_unrealized_pnl + summary.total_realized_pnl;
  const pnlIsPositive = totalPnl >= 0;

  return (
    <Card title="Trading Summary">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-sm text-neutral-400">
            <Activity className="h-4 w-4" />
            <span>Open Positions</span>
          </div>
          <p className="text-2xl font-bold text-white">
            {summary.open_positions}
          </p>
        </div>

        <div className="space-y-1">
          <div className="flex items-center gap-2 text-sm text-neutral-400">
            <Target className="h-4 w-4" />
            <span>Total Trades</span>
          </div>
          <p className="text-2xl font-bold text-white">
            {summary.total_trades}
          </p>
        </div>

        <div className="space-y-1">
          <div className="flex items-center gap-2 text-sm text-neutral-400">
            <Trophy className="h-4 w-4 text-yellow-400" />
            <span>Win Rate</span>
          </div>
          <p className="text-2xl font-bold text-yellow-400">
            {formatPercent(summary.win_rate)}
          </p>
          <p className="text-xs text-neutral-500">
            {summary.win_count}W / {summary.loss_count}L
          </p>
        </div>

        <div className="space-y-1">
          <div className="flex items-center gap-2 text-sm text-neutral-400">
            <TrendingUp className="h-4 w-4 text-emerald-500/80" />
            <span>Unrealized PnL</span>
          </div>
          <p
            className={`text-xl font-semibold ${
              summary.total_unrealized_pnl >= 0 ? 'text-emerald-500/80' : 'text-rose-500/80'
            }`}
          >
            {summary.total_unrealized_pnl >= 0 ? '+' : ''}
            {formatCurrency(summary.total_unrealized_pnl)}
          </p>
        </div>

        <div className="space-y-1">
          <div className="flex items-center gap-2 text-sm text-neutral-400">
            <TrendingDown className="h-4 w-4 text-neutral-400" />
            <span>Realized PnL</span>
          </div>
          <p
            className={`text-xl font-semibold ${
              summary.total_realized_pnl >= 0 ? 'text-emerald-500/80' : 'text-rose-500/80'
            }`}
          >
            {summary.total_realized_pnl >= 0 ? '+' : ''}
            {formatCurrency(summary.total_realized_pnl)}
          </p>
        </div>

        <div className="space-y-1">
          <div className="flex items-center gap-2 text-sm text-neutral-400">
            {pnlIsPositive ? (
              <TrendingUp className="h-4 w-4" />
            ) : (
              <TrendingDown className="h-4 w-4" />
            )}
            <span>Total PnL</span>
          </div>
          <p
            className={`text-xl font-semibold ${
              pnlIsPositive ? 'text-emerald-500/80' : 'text-rose-500/80'
            }`}
          >
            {pnlIsPositive ? '+' : ''}
            {formatCurrency(totalPnl)}
          </p>
        </div>
      </div>
    </Card>
  );
}
