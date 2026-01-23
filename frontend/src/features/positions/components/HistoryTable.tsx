import { ArrowUpRight, ArrowDownRight, Clock, TrendingUp, TrendingDown } from 'lucide-react';
import type { PositionHistory } from '../../../types';

interface HistoryTableProps {
  positions: PositionHistory[];
  isLoading?: boolean;
}

export function HistoryTable({ positions, isLoading }: HistoryTableProps) {
  const formatPrice = (price: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 6,
    }).format(price);
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
    const sign = value >= 0 ? '+' : '';
    return `${sign}${(value * 100).toFixed(2)}%`;
  };

  const formatSize = (size: number) => {
    return new Intl.NumberFormat('en-US', {
      minimumFractionDigits: 4,
      maximumFractionDigits: 8,
    }).format(size);
  };

  const formatTime = (ts: string) => {
    return new Date(ts).toLocaleString();
  };

  if (isLoading) {
    return (
      <div className="overflow-hidden rounded-xl border border-gray-700 bg-gray-800/50">
        <div className="animate-pulse p-4">
          <div className="space-y-3">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="h-14 rounded bg-gray-700" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (positions.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center rounded-xl border border-gray-700 bg-gray-800/50">
        <p className="text-gray-500">No position history</p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-gray-700 bg-gray-800/50">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-700 bg-gray-800">
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-400">
                Closed At
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-400">
                Symbol
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-400">
                Side
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-400">
                Size
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-400">
                Entry
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-400">
                Exit
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-400">
                PnL
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-400">
                Reason
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-700">
            {positions.map((position, idx) => {
              const pnlIsPositive = position.realized_pnl >= 0;
              const isLong = position.side === 'LONG';

              return (
                <tr
                  key={`${position.symbol}-${position.closed_at}-${idx}`}
                  className="transition-colors hover:bg-gray-700/50"
                >
                  <td className="whitespace-nowrap px-4 py-3">
                    <div className="flex items-center gap-2 text-sm text-gray-300">
                      <Clock className="h-4 w-4 text-gray-500" />
                      {formatTime(position.closed_at)}
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3">
                    <span className="font-medium text-gray-100">{position.symbol}</span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3">
                    <span
                      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${
                        isLong
                          ? 'bg-green-500/20 text-green-400'
                          : 'bg-red-500/20 text-red-400'
                      }`}
                    >
                      {isLong ? (
                        <ArrowUpRight className="h-3 w-3" />
                      ) : (
                        <ArrowDownRight className="h-3 w-3" />
                      )}
                      {position.side}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right">
                    <span className="text-sm text-gray-100">{formatSize(position.size)}</span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right">
                    <span className="text-sm text-gray-100">
                      {formatPrice(position.entry_price)}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right">
                    <span className="text-sm text-gray-100">
                      {formatPrice(position.exit_price)}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right">
                    <div className="flex flex-col items-end">
                      <span
                        className={`inline-flex items-center gap-1 text-sm font-medium ${
                          pnlIsPositive ? 'text-green-400' : 'text-red-400'
                        }`}
                      >
                        {pnlIsPositive ? (
                          <TrendingUp className="h-3 w-3" />
                        ) : (
                          <TrendingDown className="h-3 w-3" />
                        )}
                        {pnlIsPositive ? '+' : ''}
                        {formatCurrency(position.realized_pnl)}
                      </span>
                      <span
                        className={`text-xs ${
                          pnlIsPositive ? 'text-green-400/70' : 'text-red-400/70'
                        }`}
                      >
                        {formatPercent(position.pnl_percent)}
                      </span>
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3">
                    {position.close_reason ? (
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                          position.close_reason === 'take_profit'
                            ? 'bg-green-500/20 text-green-400'
                            : position.close_reason === 'stop_loss'
                            ? 'bg-red-500/20 text-red-400'
                            : 'bg-gray-600 text-gray-300'
                        }`}
                      >
                        {position.close_reason.replace(/_/g, ' ')}
                      </span>
                    ) : (
                      <span className="text-gray-500">-</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
