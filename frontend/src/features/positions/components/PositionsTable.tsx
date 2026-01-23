import { ArrowUpRight, ArrowDownRight, Target, ShieldAlert } from 'lucide-react';
import type { Position } from '../../../types';

interface PositionsTableProps {
  positions: Position[];
  isLoading?: boolean;
}

export function PositionsTable({ positions, isLoading }: PositionsTableProps) {
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

  const formatSize = (size: number) => {
    return new Intl.NumberFormat('en-US', {
      minimumFractionDigits: 4,
      maximumFractionDigits: 8,
    }).format(size);
  };

  if (isLoading) {
    return (
      <div className="overflow-hidden rounded-xl border border-gray-700 bg-gray-800/50">
        <div className="animate-pulse p-4">
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-16 rounded bg-gray-700" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (positions.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center rounded-xl border border-gray-700 bg-gray-800/50">
        <p className="text-gray-500">No open positions</p>
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
                Symbol
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-400">
                Side
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-400">
                Size
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-400">
                Entry Price
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-400">
                Mark Price
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-400">
                Unrealized PnL
              </th>
              <th className="px-4 py-3 text-center text-xs font-medium uppercase tracking-wider text-gray-400">
                Leverage
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-400">
                TP / SL
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-700">
            {positions.map((position) => {
              const pnlIsPositive = (position.unrealized_pnl ?? 0) >= 0;
              const isLong = position.side === 'LONG';

              return (
                <tr
                  key={`${position.symbol}-${position.side}`}
                  className="transition-colors hover:bg-gray-700/50"
                >
                  <td className="whitespace-nowrap px-4 py-4">
                    <span className="font-medium text-gray-100">{position.symbol}</span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-4">
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
                  <td className="whitespace-nowrap px-4 py-4 text-right">
                    <span className="text-sm text-gray-100">{formatSize(position.size)}</span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-4 text-right">
                    <span className="text-sm text-gray-100">
                      {formatPrice(position.entry_price)}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-4 text-right">
                    <span className="text-sm text-gray-100">
                      {position.mark_price ? formatPrice(position.mark_price) : '-'}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-4 text-right">
                    <span
                      className={`text-sm font-medium ${
                        pnlIsPositive ? 'text-green-400' : 'text-red-400'
                      }`}
                    >
                      {pnlIsPositive ? '+' : ''}
                      {position.unrealized_pnl !== undefined
                        ? formatCurrency(position.unrealized_pnl)
                        : '-'}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-4 text-center">
                    <span className="rounded bg-gray-700 px-2 py-1 text-xs font-medium text-gray-300">
                      {position.leverage}x
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-4 text-right">
                    <div className="flex items-center justify-end gap-2 text-xs">
                      {position.take_profit && (
                        <span className="flex items-center gap-1 text-green-400">
                          <Target className="h-3 w-3" />
                          {formatPrice(position.take_profit)}
                        </span>
                      )}
                      {position.stop_loss && (
                        <span className="flex items-center gap-1 text-red-400">
                          <ShieldAlert className="h-3 w-3" />
                          {formatPrice(position.stop_loss)}
                        </span>
                      )}
                      {!position.take_profit && !position.stop_loss && (
                        <span className="text-gray-500">-</span>
                      )}
                    </div>
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
