import { ArrowUpRight, ArrowDownRight, Clock, TrendingUp, TrendingDown, ExternalLink } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import type { PositionHistory } from '../../../types';

interface HistoryTableProps {
  positions: PositionHistory[];
  isLoading?: boolean;
}

export function HistoryTable({ positions, isLoading }: HistoryTableProps) {
  const navigate = useNavigate();

  const handleViewTrace = (runId: string) => {
    navigate(`/workflow?run_id=${runId}`);
  };

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
      <div className="overflow-hidden rounded-xl border border-neutral-800 bg-[#1a1a1a]">
        <div className="animate-pulse p-4">
          <div className="space-y-3">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="h-14 rounded bg-neutral-800" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (positions.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center rounded-xl border border-neutral-800 bg-[#1a1a1a]">
        <p className="text-neutral-500">No position history</p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-neutral-800 bg-[#1a1a1a]">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[900px]">
          <thead>
            <tr className="border-b border-neutral-800 bg-[#141414]">
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-neutral-400">
                Closed At
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-neutral-400">
                Symbol
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-neutral-400">
                Side
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-neutral-400">
                Size
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-neutral-400">
                Entry
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-neutral-400">
                Exit
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-neutral-400">
                PnL
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-neutral-400">
                Reason
              </th>
              <th className="px-4 py-3 text-center text-xs font-medium uppercase tracking-wider text-neutral-400">
                Trace
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-800">
            {positions.map((position, idx) => {
              const pnlIsPositive = position.realized_pnl >= 0;
              const isLong = position.side === 'LONG';

              return (
                <tr
                  key={`${position.symbol}-${position.closed_at}-${idx}`}
                  className="transition-all duration-200 hover:bg-neutral-800/50"
                >
                  <td className="whitespace-nowrap px-4 py-3">
                    <div className="flex items-center gap-2 text-sm text-neutral-300">
                      <Clock className="h-4 w-4 text-neutral-500" />
                      {formatTime(position.closed_at)}
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3">
                    <span className="font-medium text-white">{position.symbol}</span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3">
                    <span
                      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${
                        isLong
                          ? 'bg-emerald-500/20 text-emerald-500/80'
                          : 'bg-rose-500/20 text-rose-500/80'
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
                    <span className="text-sm text-white">{formatSize(position.size)}</span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right">
                    <span className="text-sm text-white">
                      {formatPrice(position.entry_price)}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right">
                    <span className="text-sm text-white">
                      {formatPrice(position.exit_price)}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right">
                    <div className="flex flex-col items-end">
                      <span
                        className={`inline-flex items-center gap-1 text-sm font-medium ${
                          pnlIsPositive ? 'text-emerald-500/80' : 'text-rose-500/80'
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
                          pnlIsPositive ? 'text-emerald-500/60' : 'text-rose-500/60'
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
                            ? 'bg-emerald-500/20 text-emerald-500/80'
                            : position.close_reason === 'stop_loss'
                            ? 'bg-rose-500/20 text-rose-500/80'
                            : 'bg-neutral-700 text-neutral-300'
                        }`}
                      >
                        {position.close_reason.replace(/_/g, ' ')}
                      </span>
                    ) : (
                      <span className="text-neutral-500">-</span>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-center">
                    <div className="flex items-center justify-center gap-1">
                      {position.open_run_id && (
                        <button
                          onClick={() => handleViewTrace(position.open_run_id!)}
                          className="inline-flex items-center gap-1 rounded-md bg-blue-500/10 px-2 py-1 text-xs font-medium text-blue-400 transition-colors hover:bg-blue-500/20"
                          title="View opening workflow trace"
                        >
                          <ExternalLink className="h-3 w-3" />
                          Open
                        </button>
                      )}
                      {position.close_run_id && (
                        <button
                          onClick={() => handleViewTrace(position.close_run_id!)}
                          className="inline-flex items-center gap-1 rounded-md bg-purple-500/10 px-2 py-1 text-xs font-medium text-purple-400 transition-colors hover:bg-purple-500/20"
                          title="View closing workflow trace"
                        >
                          <ExternalLink className="h-3 w-3" />
                          Close
                        </button>
                      )}
                      {!position.open_run_id && !position.close_run_id && (
                        <span className="text-neutral-500">-</span>
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
