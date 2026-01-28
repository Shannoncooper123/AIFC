import { useState } from 'react';
import { ArrowUpRight, ArrowDownRight, Target, ShieldAlert, ExternalLink, Clock, ChevronDown, History } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import type { Position, PositionOperation } from '../../../types';

interface PositionsTableProps {
  positions: Position[];
  isLoading?: boolean;
}

const OPERATION_LABELS: Record<string, string> = {
  open: 'Open',
  add_position: 'Add',
  update_tp_sl: 'TP/SL',
  close: 'Close',
};

function OperationTraceDropdown({
  operations,
  onViewTrace,
}: {
  operations: PositionOperation[];
  onViewTrace: (runId: string) => void;
}) {
  const [isOpen, setIsOpen] = useState(false);

  const operationsWithTrace = operations.filter((op) => op.run_id);

  if (operationsWithTrace.length === 0) {
    return <span className="text-neutral-500">-</span>;
  }

  if (operationsWithTrace.length === 1) {
    const op = operationsWithTrace[0];
    return (
      <button
        onClick={() => onViewTrace(op.run_id!)}
        className="inline-flex items-center gap-1 rounded-md bg-blue-500/10 px-2 py-1 text-xs font-medium text-blue-400 transition-colors hover:bg-blue-500/20"
        title={`View ${OPERATION_LABELS[op.operation] || op.operation} trace`}
      >
        <ExternalLink className="h-3 w-3" />
        {OPERATION_LABELS[op.operation] || op.operation}
      </button>
    );
  }

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="inline-flex items-center gap-1 rounded-md bg-blue-500/10 px-2 py-1 text-xs font-medium text-blue-400 transition-colors hover:bg-blue-500/20"
      >
        <History className="h-3 w-3" />
        {operationsWithTrace.length} Traces
        <ChevronDown className={`h-3 w-3 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>
      {isOpen && (
        <div className="absolute right-0 top-full z-10 mt-1 min-w-[160px] rounded-md border border-neutral-700 bg-neutral-800 py-1 shadow-lg">
          {operationsWithTrace.map((op, idx) => (
            <button
              key={`${op.timestamp}-${idx}`}
              onClick={() => {
                onViewTrace(op.run_id!);
                setIsOpen(false);
              }}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-neutral-300 hover:bg-neutral-700"
            >
              <ExternalLink className="h-3 w-3 text-blue-400" />
              <span className="font-medium">{OPERATION_LABELS[op.operation] || op.operation}</span>
              <span className="ml-auto text-neutral-500">
                {new Date(op.timestamp).toLocaleDateString()}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function PositionsTable({ positions, isLoading }: PositionsTableProps) {
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

  const formatSize = (size: number) => {
    return new Intl.NumberFormat('en-US', {
      minimumFractionDigits: 4,
      maximumFractionDigits: 8,
    }).format(size);
  };

  const formatTime = (ts: string | undefined) => {
    if (!ts) return '-';
    const date = new Date(ts);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    return `${year}-${month}-${day} ${hours}:${minutes}`;
  };

  if (isLoading) {
    return (
      <div className="overflow-hidden rounded-xl border border-neutral-800 bg-[#1a1a1a]">
        <div className="animate-pulse p-4">
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-16 rounded bg-neutral-800" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (positions.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center rounded-xl border border-neutral-800 bg-[#1a1a1a]">
        <p className="text-neutral-500">No open positions</p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-neutral-800 bg-[#1a1a1a]">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[800px]">
          <thead>
            <tr className="border-b border-neutral-800 bg-[#141414]">
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-neutral-400">
                Opened At
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
                Entry Price
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-neutral-400">
                Mark Price
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-neutral-400">
                Unrealized PnL
              </th>
              <th className="px-4 py-3 text-center text-xs font-medium uppercase tracking-wider text-neutral-400">
                Leverage
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-neutral-400">
                TP / SL
              </th>
              <th className="px-4 py-3 text-center text-xs font-medium uppercase tracking-wider text-neutral-400">
                Trace
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-800">
            {positions.map((position) => {
              const pnlIsPositive = (position.unrealized_pnl ?? 0) >= 0;
              const isLong = position.side === 'LONG';

              return (
                <tr
                  key={`${position.symbol}-${position.side}`}
                  className="transition-all duration-200 hover:bg-neutral-800/50"
                >
                  <td className="whitespace-nowrap px-4 py-4">
                    <div className="flex items-center gap-2 text-sm text-neutral-300">
                      <Clock className="h-4 w-4 text-emerald-500/60" />
                      {formatTime(position.opened_at)}
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-4 py-4">
                    <span className="font-medium text-white">{position.symbol}</span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-4">
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
                  <td className="whitespace-nowrap px-4 py-4 text-right">
                    <span className="text-sm text-white">{formatSize(position.size)}</span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-4 text-right">
                    <span className="text-sm text-white">
                      {formatPrice(position.entry_price)}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-4 text-right">
                    <span className="text-sm text-white">
                      {position.mark_price ? formatPrice(position.mark_price) : '-'}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-4 text-right">
                    <span
                      className={`text-sm font-medium ${
                        pnlIsPositive ? 'text-emerald-500/80' : 'text-rose-500/80'
                      }`}
                    >
                      {pnlIsPositive ? '+' : ''}
                      {position.unrealized_pnl !== undefined
                        ? formatCurrency(position.unrealized_pnl)
                        : '-'}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-4 text-center">
                    <span className="rounded bg-neutral-800 px-2 py-1 text-xs font-medium text-neutral-300">
                      {position.leverage}x
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-4 text-right">
                    <div className="flex items-center justify-end gap-2 text-xs">
                      {position.take_profit && (
                        <span className="flex items-center gap-1 text-emerald-500/80">
                          <Target className="h-3 w-3" />
                          {formatPrice(position.take_profit)}
                        </span>
                      )}
                      {position.stop_loss && (
                        <span className="flex items-center gap-1 text-rose-500/80">
                          <ShieldAlert className="h-3 w-3" />
                          {formatPrice(position.stop_loss)}
                        </span>
                      )}
                      {!position.take_profit && !position.stop_loss && (
                        <span className="text-neutral-500">-</span>
                      )}
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-4 py-4 text-center">
                    {position.operation_history && position.operation_history.length > 0 ? (
                      <OperationTraceDropdown
                        operations={position.operation_history}
                        onViewTrace={handleViewTrace}
                      />
                    ) : position.open_run_id ? (
                      <button
                        onClick={() => handleViewTrace(position.open_run_id!)}
                        className="inline-flex items-center gap-1 rounded-md bg-blue-500/10 px-2 py-1 text-xs font-medium text-blue-400 transition-colors hover:bg-blue-500/20"
                        title="View opening workflow trace"
                      >
                        <ExternalLink className="h-3 w-3" />
                        Open
                      </button>
                    ) : (
                      <span className="text-neutral-500">-</span>
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
