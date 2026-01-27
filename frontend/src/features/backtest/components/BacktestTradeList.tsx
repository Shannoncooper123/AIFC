import { useState } from 'react';
import { List, TrendingUp, TrendingDown, Clock, ChevronDown, ChevronUp } from 'lucide-react';
import { Card } from '../../../components/ui';

interface BacktestTrade {
  trade_id: string;
  kline_time: string;
  symbol: string;
  side: string;
  entry_price: number;
  exit_price: number;
  tp_price: number;
  sl_price: number;
  size: number;
  exit_time: string;
  exit_type: string;
  realized_pnl: number;
  pnl_percent: number;
  holding_bars: number;
  workflow_run_id: string;
}

interface BacktestTradeListProps {
  trades: BacktestTrade[];
  isLoading?: boolean;
}

export function BacktestTradeList({ trades, isLoading }: BacktestTradeListProps) {
  const [expanded, setExpanded] = useState(true);
  const [sortBy, setSortBy] = useState<'time' | 'pnl'>('time');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
  };

  const formatPrice = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 6,
    }).format(value);
  };

  const formatTime = (isoString: string) => {
    const date = new Date(isoString);
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const sortedTrades = [...trades].sort((a, b) => {
    if (sortBy === 'time') {
      const timeA = new Date(a.kline_time).getTime();
      const timeB = new Date(b.kline_time).getTime();
      return sortOrder === 'asc' ? timeA - timeB : timeB - timeA;
    } else {
      return sortOrder === 'asc' ? a.realized_pnl - b.realized_pnl : b.realized_pnl - a.realized_pnl;
    }
  });

  const handleSort = (field: 'time' | 'pnl') => {
    if (sortBy === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(field);
      setSortOrder('desc');
    }
  };

  const getExitTypeLabel = (exitType: string) => {
    switch (exitType) {
      case 'tp':
        return { label: 'Take Profit', color: 'text-emerald-400 bg-emerald-400/10' };
      case 'sl':
        return { label: 'Stop Loss', color: 'text-rose-400 bg-rose-400/10' };
      case 'timeout':
        return { label: 'Timeout', color: 'text-amber-400 bg-amber-400/10' };
      default:
        return { label: exitType, color: 'text-neutral-400 bg-neutral-400/10' };
    }
  };

  if (isLoading) {
    return (
      <Card>
        <div className="flex items-center justify-center py-8">
          <span className="animate-spin h-6 w-6 border-2 border-blue-400 border-t-transparent rounded-full" />
        </div>
      </Card>
    );
  }

  return (
    <Card>
      <div className="space-y-4">
        <div
          className="flex items-center justify-between cursor-pointer"
          onClick={() => setExpanded(!expanded)}
        >
          <div className="flex items-center gap-2 text-white font-medium">
            <List className="h-5 w-5 text-blue-400" />
            Trade History ({trades.length})
          </div>
          {expanded ? (
            <ChevronUp className="h-5 w-5 text-neutral-400" />
          ) : (
            <ChevronDown className="h-5 w-5 text-neutral-400" />
          )}
        </div>

        {expanded && (
          <>
            <div className="flex gap-2">
              <button
                onClick={() => handleSort('time')}
                className={`px-3 py-1 rounded text-sm ${
                  sortBy === 'time'
                    ? 'bg-blue-500/20 text-blue-400'
                    : 'bg-neutral-800 text-neutral-400 hover:text-white'
                }`}
              >
                Time {sortBy === 'time' && (sortOrder === 'asc' ? '↑' : '↓')}
              </button>
              <button
                onClick={() => handleSort('pnl')}
                className={`px-3 py-1 rounded text-sm ${
                  sortBy === 'pnl'
                    ? 'bg-blue-500/20 text-blue-400'
                    : 'bg-neutral-800 text-neutral-400 hover:text-white'
                }`}
              >
                P&L {sortBy === 'pnl' && (sortOrder === 'asc' ? '↑' : '↓')}
              </button>
            </div>

            {trades.length === 0 ? (
              <div className="text-center py-8 text-neutral-500">No trades recorded</div>
            ) : (
              <div className="space-y-2 max-h-[500px] overflow-y-auto">
                {sortedTrades.map((trade) => {
                  const exitTypeInfo = getExitTypeLabel(trade.exit_type);
                  const isProfitable = trade.realized_pnl >= 0;

                  return (
                    <div
                      key={trade.trade_id}
                      className="p-3 rounded-lg bg-neutral-800/50 border border-neutral-700/50 hover:border-neutral-600/50 transition-colors"
                    >
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-3">
                          <span className="font-medium text-white">{trade.symbol}</span>
                          <span
                            className={`px-2 py-0.5 rounded text-xs font-medium ${
                              trade.side === 'long'
                                ? 'bg-emerald-400/10 text-emerald-400'
                                : 'bg-rose-400/10 text-rose-400'
                            }`}
                          >
                            {trade.side.toUpperCase()}
                          </span>
                          <span className={`px-2 py-0.5 rounded text-xs font-medium ${exitTypeInfo.color}`}>
                            {exitTypeInfo.label}
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          {isProfitable ? (
                            <TrendingUp className="h-4 w-4 text-emerald-400" />
                          ) : (
                            <TrendingDown className="h-4 w-4 text-rose-400" />
                          )}
                          <span
                            className={`font-semibold ${
                              isProfitable ? 'text-emerald-400' : 'text-rose-400'
                            }`}
                          >
                            {formatCurrency(trade.realized_pnl)}
                          </span>
                          <span
                            className={`text-sm ${
                              isProfitable ? 'text-emerald-400/70' : 'text-rose-400/70'
                            }`}
                          >
                            ({trade.pnl_percent >= 0 ? '+' : ''}{trade.pnl_percent.toFixed(2)}%)
                          </span>
                        </div>
                      </div>

                      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm">
                        <div>
                          <span className="text-neutral-500">Entry:</span>{' '}
                          <span className="text-neutral-300">{formatPrice(trade.entry_price)}</span>
                        </div>
                        <div>
                          <span className="text-neutral-500">Exit:</span>{' '}
                          <span className="text-neutral-300">{formatPrice(trade.exit_price)}</span>
                        </div>
                        <div>
                          <span className="text-neutral-500">TP:</span>{' '}
                          <span className="text-emerald-400/70">{formatPrice(trade.tp_price)}</span>
                        </div>
                        <div>
                          <span className="text-neutral-500">SL:</span>{' '}
                          <span className="text-rose-400/70">{formatPrice(trade.sl_price)}</span>
                        </div>
                      </div>

                      <div className="flex items-center gap-4 mt-2 text-xs text-neutral-500">
                        <div className="flex items-center gap-1">
                          <Clock className="h-3 w-3" />
                          {formatTime(trade.kline_time)}
                        </div>
                        <div>→ {formatTime(trade.exit_time)}</div>
                        <div>{trade.holding_bars} bars</div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}
      </div>
    </Card>
  );
}
