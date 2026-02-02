import { TrendingUp, TrendingDown, BarChart3, Target, Percent } from 'lucide-react';
import type { ReverseStatistics } from '../../../types/reverse';
import { formatCurrency } from '../../../utils';

interface ReverseStatisticsPanelProps {
  statistics: ReverseStatistics;
  loading?: boolean;
}

export function ReverseStatisticsPanel({ statistics, loading }: ReverseStatisticsPanelProps) {
  if (loading) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="rounded-xl border border-neutral-800 bg-[#1a1a1a] p-4 animate-pulse">
            <div className="h-4 w-20 bg-neutral-700 rounded mb-2" />
            <div className="h-6 w-16 bg-neutral-700 rounded" />
          </div>
        ))}
      </div>
    );
  }

  const isProfitable = statistics.total_pnl >= 0;

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      <div className="rounded-xl border border-neutral-800 bg-[#1a1a1a] p-4">
        <div className="flex items-center gap-2 text-neutral-400 text-sm mb-1">
          <BarChart3 className="h-4 w-4" />
          Total Trades
        </div>
        <div className="text-2xl font-bold text-white">
          {statistics.total_trades}
        </div>
        <div className="text-xs text-neutral-500 mt-1">
          W: {statistics.winning_trades} / L: {statistics.losing_trades}
        </div>
      </div>

      <div className="rounded-xl border border-neutral-800 bg-[#1a1a1a] p-4">
        <div className="flex items-center gap-2 text-neutral-400 text-sm mb-1">
          <Target className="h-4 w-4" />
          Win Rate
        </div>
        <div className={`text-2xl font-bold ${statistics.win_rate >= 50 ? 'text-emerald-400' : 'text-rose-400'}`}>
          {statistics.win_rate.toFixed(1)}%
        </div>
        <div className="text-xs text-neutral-500 mt-1">
          {statistics.winning_trades} wins
        </div>
      </div>

      <div className="rounded-xl border border-neutral-800 bg-[#1a1a1a] p-4">
        <div className="flex items-center gap-2 text-neutral-400 text-sm mb-1">
          {isProfitable ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
          Total PnL
        </div>
        <div className={`text-2xl font-bold ${isProfitable ? 'text-emerald-400' : 'text-rose-400'}`}>
          {isProfitable ? '+' : ''}{formatCurrency(statistics.total_pnl)}
        </div>
        <div className="text-xs text-neutral-500 mt-1">
          Avg: {formatCurrency(statistics.avg_pnl)}
        </div>
      </div>

      <div className="rounded-xl border border-neutral-800 bg-[#1a1a1a] p-4">
        <div className="flex items-center gap-2 text-neutral-400 text-sm mb-1">
          <Percent className="h-4 w-4" />
          Best / Worst
        </div>
        <div className="flex items-baseline gap-2">
          <span className="text-lg font-bold text-emerald-400">
            +{formatCurrency(statistics.max_profit)}
          </span>
          <span className="text-neutral-500">/</span>
          <span className="text-lg font-bold text-rose-400">
            {formatCurrency(statistics.max_loss)}
          </span>
        </div>
      </div>
    </div>
  );
}
