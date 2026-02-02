import { History, TrendingUp, TrendingDown } from 'lucide-react';
import type { ReverseHistoryEntry } from '../../../types/reverse';
import { formatCurrency, formatNumber, formatTime } from '../../../utils';

interface ReverseHistoryTableProps {
  history: ReverseHistoryEntry[];
  loading?: boolean;
}

export function ReverseHistoryTable({ history, loading }: ReverseHistoryTableProps) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-neutral-600 border-t-blue-500" />
      </div>
    );
  }

  if (history.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-neutral-400">
        <History className="mb-3 h-12 w-12 opacity-30" />
        <p>No reverse trading history</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-neutral-800 text-left text-sm text-neutral-400">
            <th className="pb-3 font-medium">Symbol</th>
            <th className="pb-3 font-medium">Side</th>
            <th className="pb-3 font-medium text-right">Size</th>
            <th className="pb-3 font-medium text-right">Entry</th>
            <th className="pb-3 font-medium text-right">Exit</th>
            <th className="pb-3 font-medium text-right">PnL</th>
            <th className="pb-3 font-medium text-right">ROE</th>
            <th className="pb-3 font-medium">Reason</th>
            <th className="pb-3 font-medium">Opened</th>
            <th className="pb-3 font-medium">Closed</th>
          </tr>
        </thead>
        <tbody>
          {history.map((entry, idx) => {
            const isLong = entry.side.toUpperCase() === 'LONG';
            const isProfitable = entry.realized_pnl >= 0;

            return (
              <tr
                key={`${entry.id}-${idx}`}
                className="border-b border-neutral-800/50 hover:bg-neutral-800/30 transition-colors"
              >
                <td className="py-4">
                  <span className="font-medium text-white">{entry.symbol}</span>
                </td>
                <td className="py-4">
                  <span
                    className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium ${
                      isLong
                        ? 'bg-emerald-500/20 text-emerald-400'
                        : 'bg-rose-500/20 text-rose-400'
                    }`}
                  >
                    {isLong ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                    {entry.side.toUpperCase()}
                  </span>
                </td>
                <td className="py-4 text-right text-neutral-300">
                  {formatNumber(entry.qty, 4)}
                </td>
                <td className="py-4 text-right text-neutral-300">
                  {formatCurrency(entry.entry_price)}
                </td>
                <td className="py-4 text-right text-neutral-300">
                  {formatCurrency(entry.exit_price)}
                </td>
                <td className={`py-4 text-right font-medium ${isProfitable ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {isProfitable ? '+' : ''}{formatCurrency(entry.realized_pnl)}
                </td>
                <td className={`py-4 text-right font-medium ${isProfitable ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {isProfitable ? '+' : ''}{entry.pnl_percent.toFixed(2)}%
                </td>
                <td className="py-4">
                  <span
                    className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${
                      entry.close_reason === '止盈'
                        ? 'bg-emerald-500/20 text-emerald-400'
                        : entry.close_reason === '止损'
                        ? 'bg-rose-500/20 text-rose-400'
                        : 'bg-neutral-500/20 text-neutral-400'
                    }`}
                  >
                    {entry.close_reason}
                  </span>
                </td>
                <td className="py-4 text-sm text-neutral-400">
                  {formatTime(entry.open_time)}
                </td>
                <td className="py-4 text-sm text-neutral-400">
                  {formatTime(entry.close_time)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
