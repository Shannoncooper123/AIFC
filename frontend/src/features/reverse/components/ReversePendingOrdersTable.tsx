import { useState } from 'react';
import { Clock, X, TrendingUp, TrendingDown, RefreshCw } from 'lucide-react';
import type { ReversePendingOrder } from '../../../types/reverse';
import { formatCurrency, formatNumber, formatTime } from '../../../utils';
import { cancelReversePendingOrder } from '../../../services/api/reverse';

interface ReversePendingOrdersTableProps {
  orders: ReversePendingOrder[];
  loading?: boolean;
  onOrderCancelled?: () => void;
}

export function ReversePendingOrdersTable({ orders, loading, onOrderCancelled }: ReversePendingOrdersTableProps) {
  const [cancellingId, setCancellingId] = useState<string | null>(null);

  const handleCancel = async (algoId: string) => {
    try {
      setCancellingId(algoId);
      await cancelReversePendingOrder(algoId);
      onOrderCancelled?.();
    } catch (err) {
      console.error('Failed to cancel order:', err);
    } finally {
      setCancellingId(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-neutral-600 border-t-blue-500" />
      </div>
    );
  }

  if (orders.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-neutral-400">
        <Clock className="mb-3 h-12 w-12 opacity-30" />
        <p>No pending conditional orders</p>
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
            <th className="pb-3 font-medium text-right">Trigger</th>
            <th className="pb-3 font-medium text-right">Qty</th>
            <th className="pb-3 font-medium text-right">TP</th>
            <th className="pb-3 font-medium text-right">SL</th>
            <th className="pb-3 font-medium text-right">Margin</th>
            <th className="pb-3 font-medium">Status</th>
            <th className="pb-3 font-medium">Created</th>
            <th className="pb-3 font-medium">Expires</th>
            <th className="pb-3 font-medium text-right">Action</th>
          </tr>
        </thead>
        <tbody>
          {orders.map((order) => {
            const isLong = order.side.toUpperCase() === 'BUY';

            return (
              <tr
                key={order.algo_id}
                className="border-b border-neutral-800/50 hover:bg-neutral-800/30 transition-colors"
              >
                <td className="py-4">
                  <span className="font-medium text-white">{order.symbol}</span>
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
                    {isLong ? 'LONG' : 'SHORT'}
                  </span>
                </td>
                <td className="py-4 text-right text-neutral-300">
                  {formatCurrency(order.trigger_price)}
                </td>
                <td className="py-4 text-right text-neutral-300">
                  {formatNumber(order.quantity, 4)}
                </td>
                <td className="py-4 text-right text-emerald-400">
                  {order.tp_price ? formatCurrency(order.tp_price) : '-'}
                </td>
                <td className="py-4 text-right text-rose-400">
                  {order.sl_price ? formatCurrency(order.sl_price) : '-'}
                </td>
                <td className="py-4 text-right text-neutral-300">
                  {formatCurrency(order.margin_usdt)}
                </td>
                <td className="py-4">
                  <span className="inline-flex items-center gap-1 rounded bg-amber-500/20 px-2 py-0.5 text-xs font-medium text-amber-400">
                    <Clock className="h-3 w-3" />
                    {order.status}
                  </span>
                </td>
                <td className="py-4 text-sm text-neutral-400">
                  {formatTime(order.created_at)}
                </td>
                <td className="py-4 text-sm text-neutral-400">
                  {order.expires_at ? formatTime(order.expires_at) : '-'}
                </td>
                <td className="py-4 text-right">
                  <button
                    onClick={() => handleCancel(order.algo_id)}
                    disabled={cancellingId === order.algo_id}
                    className="inline-flex items-center gap-1 rounded bg-rose-500/20 px-2 py-1 text-xs font-medium text-rose-400 hover:bg-rose-500/30 transition-colors disabled:opacity-50"
                  >
                    {cancellingId === order.algo_id ? (
                      <RefreshCw className="h-3 w-3 animate-spin" />
                    ) : (
                      <X className="h-3 w-3" />
                    )}
                    Cancel
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
