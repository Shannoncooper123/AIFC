import { TrendingUp, TrendingDown, CheckCircle, XCircle, AlertCircle } from 'lucide-react';
import type { ReversePosition } from '../../../types/reverse';
import { formatCurrency, formatNumber } from '../../../utils';

interface ReversePositionsTableProps {
  positions: ReversePosition[];
  loading?: boolean;
  onClosePosition?: (recordId: string) => void;
}

function TPSLStatus({ tpAlgoId, slAlgoId }: { tpAlgoId?: string; slAlgoId?: string }) {
  const hasTP = !!tpAlgoId;
  const hasSL = !!slAlgoId;
  
  if (hasTP && hasSL) {
    return (
      <div className="flex items-center gap-1 text-emerald-400">
        <CheckCircle className="h-3.5 w-3.5" />
        <span className="text-xs">Active</span>
      </div>
    );
  } else if (hasTP || hasSL) {
    return (
      <div className="flex items-center gap-1 text-amber-400">
        <AlertCircle className="h-3.5 w-3.5" />
        <span className="text-xs">{hasTP ? 'TP Only' : 'SL Only'}</span>
      </div>
    );
  } else {
    return (
      <div className="flex items-center gap-1 text-rose-400">
        <XCircle className="h-3.5 w-3.5" />
        <span className="text-xs">None</span>
      </div>
    );
  }
}

export function ReversePositionsTable({ positions, loading, onClosePosition }: ReversePositionsTableProps) {
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
        <p>No reverse positions</p>
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
            <th className="pb-3 font-medium text-right">Mark</th>
            <th className="pb-3 font-medium text-right">TP</th>
            <th className="pb-3 font-medium text-right">SL</th>
            <th className="pb-3 font-medium text-center">TP/SL Orders</th>
            <th className="pb-3 font-medium text-right">PnL</th>
            <th className="pb-3 font-medium text-right">ROE</th>
            <th className="pb-3 font-medium text-right">Margin</th>
            {onClosePosition && <th className="pb-3 font-medium text-center">Action</th>}
          </tr>
        </thead>
        <tbody>
          {positions.map((pos) => {
            const isLong = pos.side === 'LONG';
            const pnl = pos.unrealized_pnl ?? 0;
            const roe = pos.roe ?? 0;
            const isProfitable = pnl >= 0;

            return (
              <tr
                key={pos.id}
                className="border-b border-neutral-800/50 hover:bg-neutral-800/30 transition-colors"
              >
                <td className="py-4">
                  <span className="font-medium text-white">{pos.symbol}</span>
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
                    {pos.side}
                  </span>
                </td>
                <td className="py-4 text-right text-neutral-300">
                  {formatNumber(pos.size, 4)}
                </td>
                <td className="py-4 text-right text-neutral-300">
                  {formatCurrency(pos.entry_price)}
                </td>
                <td className="py-4 text-right text-neutral-300">
                  {pos.mark_price ? formatCurrency(pos.mark_price) : '-'}
                </td>
                <td className="py-4 text-right">
                  <div className="flex flex-col items-end">
                    <span className="text-emerald-400">
                      {pos.take_profit ? formatCurrency(pos.take_profit) : '-'}
                    </span>
                    {pos.tp_algo_id && (
                      <span className="text-xs text-neutral-500 font-mono">
                        #{pos.tp_algo_id.slice(-6)}
                      </span>
                    )}
                  </div>
                </td>
                <td className="py-4 text-right">
                  <div className="flex flex-col items-end">
                    <span className="text-rose-400">
                      {pos.stop_loss ? formatCurrency(pos.stop_loss) : '-'}
                    </span>
                    {pos.sl_algo_id && (
                      <span className="text-xs text-neutral-500 font-mono">
                        #{pos.sl_algo_id.slice(-6)}
                      </span>
                    )}
                  </div>
                </td>
                <td className="py-4 text-center">
                  <TPSLStatus tpAlgoId={pos.tp_algo_id} slAlgoId={pos.sl_algo_id} />
                </td>
                <td className={`py-4 text-right font-medium ${isProfitable ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {isProfitable ? '+' : ''}{formatCurrency(pnl)}
                </td>
                <td className={`py-4 text-right font-medium ${isProfitable ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {isProfitable ? '+' : ''}{roe.toFixed(2)}%
                </td>
                <td className="py-4 text-right text-neutral-300">
                  {formatCurrency(pos.margin)}
                </td>
                {onClosePosition && (
                  <td className="py-4 text-center">
                    <button
                      onClick={() => onClosePosition(pos.id)}
                      className="rounded bg-rose-500/20 px-3 py-1 text-xs font-medium text-rose-400 hover:bg-rose-500/30 transition-colors"
                    >
                      Close
                    </button>
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
      
      <div className="mt-4 flex items-center gap-4 text-xs text-neutral-500">
        <div className="flex items-center gap-1">
          <CheckCircle className="h-3.5 w-3.5 text-emerald-400" />
          <span>TP/SL orders active on Binance</span>
        </div>
        <div className="flex items-center gap-1">
          <AlertCircle className="h-3.5 w-3.5 text-amber-400" />
          <span>Partial TP/SL</span>
        </div>
        <div className="flex items-center gap-1">
          <XCircle className="h-3.5 w-3.5 text-rose-400" />
          <span>No TP/SL orders</span>
        </div>
      </div>
    </div>
  );
}
