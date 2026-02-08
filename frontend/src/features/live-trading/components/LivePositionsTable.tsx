import { useState, useEffect, useMemo, useCallback } from 'react';
import { TrendingUp, TrendingDown, CheckCircle, XCircle, AlertCircle, Target, Shield, Zap } from 'lucide-react';
import type { LivePosition } from '../../../types/live';
import { formatPrice, formatPriceChange, calcPriceDistance, formatNumber } from '../../../utils';
import { useWebSocket } from '../../../hooks/useWebSocket';

interface LivePositionsTableProps {
  positions: LivePosition[];
  loading?: boolean;
  onClosePosition?: (recordId: string) => void;
}

function useRealtimePrices(positions: LivePosition[]) {
  const [prices, setPrices] = useState<Record<string, number>>({});
  
  const handleMessage = useCallback((event: { type: string; data: Record<string, unknown> }) => {
    if (event.type === 'mark_price_update') {
      const newPrices = event.data.prices as Record<string, number>;
      if (newPrices) {
        setPrices(prev => ({ ...prev, ...newPrices }));
      }
    }
  }, []);
  
  useWebSocket('/ws/events', {
    onMessage: handleMessage,
  });
  
  useEffect(() => {
    const initialPrices: Record<string, number> = {};
    positions.forEach(pos => {
      if (pos.mark_price) {
        initialPrices[pos.symbol] = pos.mark_price;
      }
    });
    setPrices(prev => ({ ...initialPrices, ...prev }));
  }, [positions]);
  
  const positionsWithRealtimePrices = useMemo(() => {
    return positions.map(pos => {
      const realtimePrice = prices[pos.symbol];
      if (realtimePrice && realtimePrice !== pos.mark_price) {
        const newMarkPrice = realtimePrice;
        const isLong = pos.side === 'LONG' || pos.side.toUpperCase() === 'BUY';
        
        let unrealizedPnl: number;
        if (isLong) {
          unrealizedPnl = (newMarkPrice - pos.entry_price) * pos.size;
        } else {
          unrealizedPnl = (pos.entry_price - newMarkPrice) * pos.size;
        }
        
        const roe = pos.margin > 0 ? (unrealizedPnl / pos.margin) * 100 : 0;
        
        return {
          ...pos,
          mark_price: newMarkPrice,
          unrealized_pnl: unrealizedPnl,
          roe: roe,
        };
      }
      return pos;
    });
  }, [positions, prices]);
  
  return positionsWithRealtimePrices;
}

function TPSLStatus({ tpOrderId, tpAlgoId, slAlgoId }: { tpOrderId?: number; tpAlgoId?: string; slAlgoId?: string }) {
  const hasTP = !!(tpOrderId || tpAlgoId);
  const hasSL = !!slAlgoId;
  
  if (hasTP && hasSL) {
    return (
      <div className="flex items-center gap-1.5 text-emerald-400">
        <CheckCircle className="h-4 w-4" />
        <span className="text-xs font-medium">Protected</span>
      </div>
    );
  } else if (hasTP || hasSL) {
    return (
      <div className="flex items-center gap-1.5 text-amber-400">
        <AlertCircle className="h-4 w-4" />
        <span className="text-xs font-medium">{hasTP ? 'TP Only' : 'SL Only'}</span>
      </div>
    );
  } else {
    return (
      <div className="flex items-center gap-1.5 text-rose-400">
        <XCircle className="h-4 w-4" />
        <span className="text-xs font-medium">Unprotected</span>
      </div>
    );
  }
}

function PriceDistanceBar({ 
  entryPrice, 
  currentPrice, 
  tpPrice, 
  slPrice,
  isLong 
}: { 
  entryPrice: number;
  currentPrice: number;
  tpPrice?: number;
  slPrice?: number;
  isLong: boolean;
}) {
  if (!tpPrice || !slPrice || !currentPrice) return null;
  
  const totalRange = Math.abs(tpPrice - slPrice);
  const currentFromEntry = currentPrice - entryPrice;
  const progressPercent = isLong 
    ? ((currentPrice - slPrice) / totalRange) * 100
    : ((tpPrice - currentPrice) / totalRange) * 100;
  
  const clampedProgress = Math.max(0, Math.min(100, progressPercent));
  
  return (
    <div className="mt-2">
      <div className="flex justify-between text-[10px] text-neutral-500 mb-1">
        <span>SL</span>
        <span>Entry</span>
        <span>TP</span>
      </div>
      <div className="relative h-1.5 bg-neutral-700 rounded-full overflow-hidden">
        <div 
          className={`absolute h-full rounded-full transition-all duration-300 ${
            currentFromEntry >= 0 ? 'bg-emerald-500' : 'bg-rose-500'
          }`}
          style={{ width: `${clampedProgress}%` }}
        />
        <div 
          className="absolute h-full w-0.5 bg-neutral-400"
          style={{ left: `${isLong ? ((entryPrice - slPrice) / totalRange) * 100 : ((tpPrice - entryPrice) / totalRange) * 100}%` }}
        />
      </div>
    </div>
  );
}

export function LivePositionsTable({ positions, loading, onClosePosition }: LivePositionsTableProps) {
  const realtimePositions = useRealtimePrices(positions);
  
  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-neutral-600 border-t-blue-500" />
      </div>
    );
  }

  if (positions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-neutral-400">
        <TrendingUp className="mb-3 h-12 w-12 opacity-30" />
        <p>No live positions</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {realtimePositions.map((pos) => {
        const isLong = pos.side === 'LONG' || pos.side.toUpperCase() === 'BUY';
        const pnl = pos.unrealized_pnl ?? 0;
        const roe = pos.roe ?? 0;
        const isProfitable = pnl >= 0;
        
        const tpDistance = pos.take_profit && pos.mark_price 
          ? calcPriceDistance(pos.mark_price, pos.take_profit) 
          : null;
        const slDistance = pos.stop_loss && pos.mark_price 
          ? calcPriceDistance(pos.mark_price, pos.stop_loss) 
          : null;

        return (
          <div
            key={pos.id}
            className="rounded-lg border border-neutral-800 bg-neutral-900/50 p-4 hover:border-neutral-700 transition-colors"
          >
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="flex flex-col">
                  <div className="flex items-center gap-2">
                    <span className="text-lg font-semibold text-white">{pos.symbol}</span>
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
                      {pos.leverage}x
                    </span>
                  </div>
                  <div className="flex items-center gap-2 mt-1 text-xs text-neutral-500">
                    <span>Size: {formatNumber(pos.size, 4)}</span>
                    <span>•</span>
                    <span>Margin: {formatPrice(pos.margin)}</span>
                  </div>
                </div>
              </div>
              
              <div className="flex items-center gap-3">
                <div className={`text-right ${isProfitable ? 'text-emerald-400' : 'text-rose-400'}`}>
                  <div className="text-lg font-semibold">
                    {isProfitable ? '+' : ''}{formatPrice(pnl)}
                  </div>
                  <div className="text-xs">
                    ROE: {isProfitable ? '+' : ''}{roe.toFixed(2)}%
                  </div>
                </div>
                {onClosePosition && (
                  <button
                    onClick={() => onClosePosition(pos.id)}
                    className="rounded-lg bg-rose-500/20 px-4 py-2 text-sm font-medium text-rose-400 hover:bg-rose-500/30 transition-colors"
                  >
                    Close
                  </button>
                )}
              </div>
            </div>
            
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
              <div className="rounded-lg bg-neutral-800/50 p-3">
                <div className="text-xs text-neutral-500 mb-1">Entry Price</div>
                <div className="text-sm font-medium text-white">{formatPrice(pos.entry_price)}</div>
              </div>
              
              <div className="rounded-lg bg-neutral-800/50 p-3">
                <div className="text-xs text-neutral-500 mb-1">Mark Price</div>
                <div className="text-sm font-medium text-white">
                  {pos.mark_price ? formatPrice(pos.mark_price) : '—'}
                </div>
                {pos.mark_price && pos.entry_price && (
                  <div className={`text-xs ${pos.mark_price >= pos.entry_price ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {formatPriceChange(pos.entry_price, pos.mark_price)}
                  </div>
                )}
              </div>
              
              <div className="rounded-lg bg-neutral-800/50 p-3">
                <div className="flex items-center gap-1 text-xs text-emerald-500 mb-1">
                  <Target className="h-3 w-3" />
                  Take Profit
                </div>
                <div className="text-sm font-medium text-emerald-400">
                  {pos.take_profit ? formatPrice(pos.take_profit) : '—'}
                </div>
                {tpDistance !== null && (
                  <div className="text-xs text-neutral-500">
                    {tpDistance >= 0 ? '+' : ''}{tpDistance.toFixed(2)}% away
                  </div>
                )}
                {(pos.tp_order_id || pos.tp_algo_id) && (
                  <div className="text-[10px] text-neutral-600 font-mono mt-1">
                    #{pos.tp_order_id ? String(pos.tp_order_id).slice(-8) : (pos.tp_algo_id || '').slice(-8)}
                  </div>
                )}
              </div>
              
              <div className="rounded-lg bg-neutral-800/50 p-3">
                <div className="flex items-center gap-1 text-xs text-rose-500 mb-1">
                  <Shield className="h-3 w-3" />
                  Stop Loss
                </div>
                <div className="text-sm font-medium text-rose-400">
                  {pos.stop_loss ? formatPrice(pos.stop_loss) : '—'}
                </div>
                {slDistance !== null && (
                  <div className="text-xs text-neutral-500">
                    {slDistance >= 0 ? '+' : ''}{slDistance.toFixed(2)}% away
                  </div>
                )}
                {pos.sl_algo_id && (
                  <div className="text-[10px] text-neutral-600 font-mono mt-1">
                    #{(pos.sl_algo_id || '').slice(-8)}
                  </div>
                )}
              </div>
            </div>
            
            <div className="flex items-center justify-between pt-3 border-t border-neutral-800">
              <TPSLStatus tpOrderId={pos.tp_order_id} tpAlgoId={pos.tp_algo_id} slAlgoId={pos.sl_algo_id} />
              
              <PriceDistanceBar
                entryPrice={pos.entry_price}
                currentPrice={pos.mark_price ?? pos.entry_price}
                tpPrice={pos.take_profit}
                slPrice={pos.stop_loss}
                isLong={isLong}
              />
            </div>
          </div>
        );
      })}
      
      <div className="flex items-center gap-6 text-xs text-neutral-500 pt-2">
        <div className="flex items-center gap-1.5">
          <CheckCircle className="h-4 w-4 text-emerald-400" />
          <span>TP/SL orders active on Binance</span>
        </div>
        <div className="flex items-center gap-1.5">
          <AlertCircle className="h-4 w-4 text-amber-400" />
          <span>Partial TP/SL</span>
        </div>
        <div className="flex items-center gap-1.5">
          <XCircle className="h-4 w-4 text-rose-400" />
          <span>No TP/SL orders</span>
        </div>
      </div>
    </div>
  );
}
