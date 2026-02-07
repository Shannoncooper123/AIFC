import { useState, useEffect } from 'react';
import { Clock, X, TrendingUp, TrendingDown, RefreshCw, Target, Shield, Zap, ArrowRight } from 'lucide-react';
import type { ReversePendingOrder } from '../../../types/reverse';
import { formatPrice, formatPriceChange, formatNumber, formatTime } from '../../../utils';
import { cancelReversePendingOrder } from '../../../services/api/reverse';

interface ReversePendingOrdersTableProps {
  orders: ReversePendingOrder[];
  loading?: boolean;
  onOrderCancelled?: () => void;
  currentPrices?: Record<string, number>;
}

function TimeRemaining({ expiresAt }: { expiresAt?: string }) {
  const [remaining, setRemaining] = useState<string>('');
  
  useEffect(() => {
    if (!expiresAt) {
      setRemaining('—');
      return;
    }
    
    const updateRemaining = () => {
      const now = new Date().getTime();
      const expiry = new Date(expiresAt).getTime();
      const diff = expiry - now;
      
      if (diff <= 0) {
        setRemaining('Expired');
        return;
      }
      
      const days = Math.floor(diff / (1000 * 60 * 60 * 24));
      const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
      const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
      
      if (days > 0) {
        setRemaining(`${days}d ${hours}h`);
      } else if (hours > 0) {
        setRemaining(`${hours}h ${minutes}m`);
      } else {
        setRemaining(`${minutes}m`);
      }
    };
    
    updateRemaining();
    const interval = setInterval(updateRemaining, 60000);
    return () => clearInterval(interval);
  }, [expiresAt]);
  
  return <span>{remaining}</span>;
}

export function ReversePendingOrdersTable({ 
  orders, 
  loading, 
  onOrderCancelled,
  currentPrices = {}
}: ReversePendingOrdersTableProps) {
  const [cancellingId, setCancellingId] = useState<string | null>(null);

  const handleCancel = async (orderId: string) => {
    try {
      setCancellingId(orderId);
      await cancelReversePendingOrder(orderId);
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
    <div className="space-y-3">
      {orders.map((order) => {
        const isLong = order.side.toUpperCase() === 'BUY';
        const currentPrice = currentPrices[order.symbol];
        const distancePercent = currentPrice 
          ? ((order.trigger_price - currentPrice) / currentPrice) * 100 
          : null;

        return (
          <div
            key={order.id}
            className="rounded-lg border border-neutral-800 bg-neutral-900/50 p-4 hover:border-neutral-700 transition-colors"
          >
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-3">
                <div className="flex flex-col">
                  <div className="flex items-center gap-2">
                    <span className="text-lg font-semibold text-white">{order.symbol}</span>
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
                    <span className="inline-flex items-center gap-1 rounded bg-blue-500/20 px-2 py-0.5 text-xs font-medium text-blue-400">
                      <Zap className="h-3 w-3" />
                      {order.leverage}x
                    </span>
                    <span className="inline-flex items-center gap-1 rounded bg-amber-500/20 px-2 py-0.5 text-xs font-medium text-amber-400">
                      <Clock className="h-3 w-3" />
                      {order.status}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 mt-1 text-xs text-neutral-500">
                    <span>Qty: {formatNumber(order.quantity, 4)}</span>
                    <span>•</span>
                    <span>Margin: {formatPrice(order.margin_usdt)}</span>
                    <span>•</span>
                    <span>ID: #{(order.algo_id || order.id || '').slice(-8)}</span>
                  </div>
                </div>
              </div>
              
              <button
                onClick={() => handleCancel(order.id)}
                disabled={cancellingId === order.id}
                className="inline-flex items-center gap-1.5 rounded-lg bg-rose-500/20 px-3 py-1.5 text-sm font-medium text-rose-400 hover:bg-rose-500/30 transition-colors disabled:opacity-50"
              >
                {cancellingId === order.id ? (
                  <RefreshCw className="h-4 w-4 animate-spin" />
                ) : (
                  <X className="h-4 w-4" />
                )}
                Cancel
              </button>
            </div>
            
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="rounded-lg bg-neutral-800/50 p-3">
                <div className="flex items-center gap-1 text-xs text-amber-500 mb-1">
                  <ArrowRight className="h-3 w-3" />
                  Trigger Price
                </div>
                <div className="text-sm font-medium text-amber-400">
                  {formatPrice(order.trigger_price)}
                </div>
                {distancePercent !== null && (
                  <div className={`text-xs ${distancePercent >= 0 ? 'text-neutral-500' : 'text-amber-500'}`}>
                    {distancePercent >= 0 ? '+' : ''}{distancePercent.toFixed(2)}% from current
                  </div>
                )}
              </div>
              
              <div className="rounded-lg bg-neutral-800/50 p-3">
                <div className="flex items-center gap-1 text-xs text-emerald-500 mb-1">
                  <Target className="h-3 w-3" />
                  Take Profit
                </div>
                <div className="text-sm font-medium text-emerald-400">
                  {order.tp_price ? formatPrice(order.tp_price) : '—'}
                </div>
                {order.tp_price && (
                  <div className="text-xs text-neutral-500">
                    {formatPriceChange(order.trigger_price, order.tp_price)}
                  </div>
                )}
              </div>
              
              <div className="rounded-lg bg-neutral-800/50 p-3">
                <div className="flex items-center gap-1 text-xs text-rose-500 mb-1">
                  <Shield className="h-3 w-3" />
                  Stop Loss
                </div>
                <div className="text-sm font-medium text-rose-400">
                  {order.sl_price ? formatPrice(order.sl_price) : '—'}
                </div>
                {order.sl_price && (
                  <div className="text-xs text-neutral-500">
                    {formatPriceChange(order.trigger_price, order.sl_price)}
                  </div>
                )}
              </div>
              
              <div className="rounded-lg bg-neutral-800/50 p-3">
                <div className="text-xs text-neutral-500 mb-1">Expires In</div>
                <div className="text-sm font-medium text-white">
                  <TimeRemaining expiresAt={order.expires_at} />
                </div>
                <div className="text-xs text-neutral-600">
                  {order.expires_at ? formatTime(order.expires_at) : '—'}
                </div>
              </div>
            </div>
            
            {order.agent_side && (
              <div className="mt-3 pt-3 border-t border-neutral-800">
                <div className="flex items-center gap-2 text-xs text-neutral-500">
                  <span>Agent Signal:</span>
                  <span className={order.agent_side.toUpperCase() === 'BUY' || order.agent_side.toUpperCase() === 'LONG' ? 'text-emerald-400' : 'text-rose-400'}>
                    {order.agent_side.toUpperCase()}
                  </span>
                  <span>→</span>
                  <span className={isLong ? 'text-emerald-400' : 'text-rose-400'}>
                    Reverse {isLong ? 'LONG' : 'SHORT'}
                  </span>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
