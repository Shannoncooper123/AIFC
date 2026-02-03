import { History, TrendingUp, TrendingDown, Target, Shield, Clock, Zap } from 'lucide-react';
import type { ReverseHistoryEntry } from '../../../types/reverse';
import { formatPrice, formatNumber, formatTime } from '../../../utils';

interface ReverseHistoryTableProps {
  history: ReverseHistoryEntry[];
  loading?: boolean;
}

function CloseReasonBadge({ reason }: { reason: string }) {
  const reasonLower = reason.toLowerCase();
  
  if (reasonLower.includes('tp') || reasonLower.includes('止盈') || reasonLower.includes('take_profit')) {
    return (
      <span className="inline-flex items-center gap-1 rounded bg-emerald-500/20 px-2 py-0.5 text-xs font-medium text-emerald-400">
        <Target className="h-3 w-3" />
        Take Profit
      </span>
    );
  } else if (reasonLower.includes('sl') || reasonLower.includes('止损') || reasonLower.includes('stop_loss')) {
    return (
      <span className="inline-flex items-center gap-1 rounded bg-rose-500/20 px-2 py-0.5 text-xs font-medium text-rose-400">
        <Shield className="h-3 w-3" />
        Stop Loss
      </span>
    );
  } else if (reasonLower.includes('manual') || reasonLower.includes('手动')) {
    return (
      <span className="inline-flex items-center gap-1 rounded bg-blue-500/20 px-2 py-0.5 text-xs font-medium text-blue-400">
        Manual Close
      </span>
    );
  } else if (reasonLower.includes('liquidat') || reasonLower.includes('强平')) {
    return (
      <span className="inline-flex items-center gap-1 rounded bg-orange-500/20 px-2 py-0.5 text-xs font-medium text-orange-400">
        Liquidated
      </span>
    );
  } else if (reasonLower.includes('external') || reasonLower.includes('外部')) {
    return (
      <span className="inline-flex items-center gap-1 rounded bg-purple-500/20 px-2 py-0.5 text-xs font-medium text-purple-400">
        External Close
      </span>
    );
  }
  
  return (
    <span className="inline-flex items-center rounded bg-neutral-500/20 px-2 py-0.5 text-xs font-medium text-neutral-400">
      {reason}
    </span>
  );
}

function formatDuration(openTime: string, closeTime: string): string {
  const open = new Date(openTime).getTime();
  const close = new Date(closeTime).getTime();
  const diff = close - open;
  
  if (diff < 0) return '—';
  
  const minutes = Math.floor(diff / (1000 * 60));
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);
  
  if (days > 0) {
    return `${days}d ${hours % 24}h`;
  } else if (hours > 0) {
    return `${hours}h ${minutes % 60}m`;
  } else {
    return `${minutes}m`;
  }
}

export function ReverseHistoryTable({ history, loading }: ReverseHistoryTableProps) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-neutral-600 border-t-blue-500" />
      </div>
    );
  }

  if (history.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-neutral-400">
        <History className="mb-3 h-12 w-12 opacity-30" />
        <p>No reverse trading history</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {history.map((entry, idx) => {
        const isLong = entry.side.toUpperCase() === 'LONG' || entry.side.toUpperCase() === 'BUY';
        const isProfitable = entry.realized_pnl >= 0;
        const priceChange = ((entry.exit_price - entry.entry_price) / entry.entry_price) * 100;

        return (
          <div
            key={`${entry.id}-${idx}`}
            className={`rounded-lg border p-4 transition-colors ${
              isProfitable 
                ? 'border-emerald-900/50 bg-emerald-950/20' 
                : 'border-rose-900/50 bg-rose-950/20'
            }`}
          >
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-3">
                <div className="flex flex-col">
                  <div className="flex items-center gap-2">
                    <span className="text-lg font-semibold text-white">{entry.symbol}</span>
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
                      {entry.leverage}x
                    </span>
                    <CloseReasonBadge reason={entry.close_reason} />
                  </div>
                  <div className="flex items-center gap-2 mt-1 text-xs text-neutral-500">
                    <span>Qty: {formatNumber(entry.qty, 4)}</span>
                    <span>•</span>
                    <span>Margin: {formatPrice(entry.margin_usdt)}</span>
                    <span>•</span>
                    <span className="flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {formatDuration(entry.open_time, entry.close_time)}
                    </span>
                  </div>
                </div>
              </div>
              
              <div className={`text-right ${isProfitable ? 'text-emerald-400' : 'text-rose-400'}`}>
                <div className="text-xl font-bold">
                  {isProfitable ? '+' : ''}{formatPrice(entry.realized_pnl)}
                </div>
                <div className="text-sm">
                  ROE: {isProfitable ? '+' : ''}{entry.pnl_percent.toFixed(2)}%
                </div>
                {(entry.total_commission ?? 0) > 0 && (
                  <div className="text-xs text-neutral-500 mt-1">
                    Fee: ${entry.total_commission?.toFixed(4)}
                  </div>
                )}
              </div>
            </div>
            
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="rounded-lg bg-black/20 p-3">
                <div className="text-xs text-neutral-500 mb-1">Entry Price</div>
                <div className="text-sm font-medium text-white">{formatPrice(entry.entry_price)}</div>
              </div>
              
              <div className="rounded-lg bg-black/20 p-3">
                <div className="text-xs text-neutral-500 mb-1">Exit Price</div>
                <div className="text-sm font-medium text-white">{formatPrice(entry.exit_price)}</div>
                <div className={`text-xs ${priceChange >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {priceChange >= 0 ? '+' : ''}{priceChange.toFixed(2)}%
                </div>
              </div>
              
              <div className="rounded-lg bg-black/20 p-3">
                <div className="text-xs text-neutral-500 mb-1">Opened</div>
                <div className="text-sm font-medium text-white">{formatTime(entry.open_time)}</div>
              </div>
              
              <div className="rounded-lg bg-black/20 p-3">
                <div className="text-xs text-neutral-500 mb-1">Closed</div>
                <div className="text-sm font-medium text-white">{formatTime(entry.close_time)}</div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
