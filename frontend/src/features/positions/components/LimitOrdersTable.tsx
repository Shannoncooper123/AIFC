import { ArrowUpRight, ArrowDownRight, Target, ShieldAlert, Clock, ExternalLink } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import type { LimitOrder } from '../../../types';

interface LimitOrdersTableProps {
  orders: LimitOrder[];
  isLoading?: boolean;
}

export function LimitOrdersTable({ orders, isLoading }: LimitOrdersTableProps) {
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

  if (orders.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center rounded-xl border border-neutral-800 bg-[#1a1a1a]">
        <p className="text-neutral-500">No pending orders</p>
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
                Created At
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-neutral-400">
                Symbol
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-neutral-400">
                Side
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-neutral-400">
                Limit Price
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-neutral-400">
                Margin
              </th>
              <th className="px-4 py-3 text-center text-xs font-medium uppercase tracking-wider text-neutral-400">
                Leverage
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-neutral-400">
                TP / SL
              </th>
              <th className="px-4 py-3 text-center text-xs font-medium uppercase tracking-wider text-neutral-400">
                Status
              </th>
              <th className="px-4 py-3 text-center text-xs font-medium uppercase tracking-wider text-neutral-400">
                Trace
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-800">
            {orders.map((order) => {
              const isLong = order.side.toLowerCase() === 'long';

              return (
                <tr
                  key={order.id}
                  className="transition-all duration-200 hover:bg-neutral-800/50"
                >
                  <td className="whitespace-nowrap px-4 py-4">
                    <div className="flex items-center gap-2 text-sm text-neutral-300">
                      <Clock className="h-4 w-4 text-emerald-500/60" />
                      {formatTime(order.create_time)}
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-4 py-4">
                    <span className="font-medium text-white">{order.symbol}</span>
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
                      {order.side.toUpperCase()}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-4 text-right">
                    <span className="text-sm text-white">
                      {formatPrice(order.limit_price)}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-4 text-right">
                    <span className="text-sm text-white">
                      {formatCurrency(order.margin_usdt)}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-4 text-center">
                    <span className="rounded bg-neutral-800 px-2 py-1 text-xs font-medium text-neutral-300">
                      {order.leverage}x
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-4 text-right">
                    <div className="flex items-center justify-end gap-2 text-xs">
                      {order.tp_price && (
                        <span className="flex items-center gap-1 text-emerald-500/80">
                          <Target className="h-3 w-3" />
                          {formatPrice(order.tp_price)}
                        </span>
                      )}
                      {order.sl_price && (
                        <span className="flex items-center gap-1 text-rose-500/80">
                          <ShieldAlert className="h-3 w-3" />
                          {formatPrice(order.sl_price)}
                        </span>
                      )}
                      {!order.tp_price && !order.sl_price && (
                        <span className="text-neutral-500">-</span>
                      )}
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-4 py-4 text-center">
                    <span className="rounded bg-yellow-500/10 px-2 py-1 text-xs font-medium text-yellow-500">
                      {order.status.toUpperCase()}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-4 text-center">
                    {order.create_run_id ? (
                      <button
                        onClick={() => handleViewTrace(order.create_run_id!)}
                        className="inline-flex items-center gap-1 rounded-md bg-blue-500/10 px-2 py-1 text-xs font-medium text-blue-400 transition-colors hover:bg-blue-500/20"
                        title="View creation workflow trace"
                      >
                        <ExternalLink className="h-3 w-3" />
                        Created
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
