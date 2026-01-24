import { TrendingUp, TrendingDown, Clock } from 'lucide-react';
import type { AlertRecord } from '../../../types';

interface AlertsTableProps {
  alerts: AlertRecord[];
  isLoading?: boolean;
}

export function AlertsTable({ alerts, isLoading }: AlertsTableProps) {
  const formatPrice = (price: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 6,
    }).format(price);
  };

  const formatPercent = (value: number) => {
    const sign = value >= 0 ? '+' : '';
    return `${sign}${(value * 100).toFixed(2)}%`;
  };

  const formatTime = (ts: string) => {
    return new Date(ts).toLocaleString();
  };

  if (isLoading) {
    return (
      <div className="overflow-hidden rounded-xl border border-neutral-800 bg-[#1a1a1a]">
        <div className="animate-pulse p-4">
          <div className="space-y-3">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="h-12 rounded bg-neutral-800" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (alerts.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center rounded-xl border border-neutral-800 bg-[#1a1a1a]">
        <p className="text-neutral-500">No alerts found</p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-neutral-800 bg-[#1a1a1a]">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[700px]">
          <thead>
            <tr className="border-b border-neutral-800 bg-[#141414]">
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-neutral-400">
                Time
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-neutral-400">
                Interval
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-neutral-400">
                Symbol
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-neutral-400">
                Price
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-neutral-400">
                Change
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-neutral-400">
                Indicators
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-800">
            {alerts.flatMap((record) =>
              record.entries.map((entry, idx) => (
                <tr
                  key={`${record.ts}-${entry.symbol}-${idx}`}
                  className="transition-all duration-200 hover:bg-neutral-800/50"
                >
                  <td className="whitespace-nowrap px-4 py-3">
                    <div className="flex items-center gap-2 text-sm text-neutral-300">
                      <Clock className="h-4 w-4 text-neutral-500" />
                      {formatTime(entry.timestamp || record.ts)}
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3">
                    <span className="rounded bg-neutral-800 px-2 py-1 text-xs font-medium text-neutral-300">
                      {record.interval}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3">
                    <span className="font-medium text-white">{entry.symbol}</span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right">
                    <span className="text-sm text-white">{formatPrice(entry.price)}</span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right">
                    <span
                      className={`inline-flex items-center gap-1 text-sm font-medium ${
                        entry.price_change_rate >= 0 ? 'text-emerald-500/80' : 'text-rose-500/80'
                      }`}
                    >
                      {entry.price_change_rate >= 0 ? (
                        <TrendingUp className="h-3 w-3" />
                      ) : (
                        <TrendingDown className="h-3 w-3" />
                      )}
                      {formatPercent(entry.price_change_rate)}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {entry.triggered_indicators.map((indicator) => (
                        <span
                          key={indicator}
                          className="rounded-full bg-neutral-700/50 px-2 py-0.5 text-xs font-medium text-neutral-300"
                        >
                          {indicator}
                        </span>
                      ))}
                      {entry.engulfing_type && (
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                            entry.engulfing_type === 'bullish'
                              ? 'bg-emerald-500/20 text-emerald-500/80'
                              : 'bg-rose-500/20 text-rose-500/80'
                          }`}
                        >
                          {entry.engulfing_type}
                        </span>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
