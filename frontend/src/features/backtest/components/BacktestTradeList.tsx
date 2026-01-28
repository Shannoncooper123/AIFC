import { useState } from 'react';
import { Link } from 'react-router-dom';
import { List, TrendingUp, TrendingDown, Clock, ChevronDown, ChevronUp, Info, DollarSign, Percent, Target, ExternalLink } from 'lucide-react';
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
  order_type?: string;
  margin_usdt?: number;
  leverage?: number;
  notional_usdt?: number;
  original_tp_price?: number | null;
  original_sl_price?: number | null;
  limit_price?: number | null;
  fees_total?: number;
  r_multiple?: number | null;
  tp_distance_percent?: number;
  sl_distance_percent?: number;
  close_reason?: string;
  order_created_time?: string | null;
}

interface BacktestTradeListProps {
  trades: BacktestTrade[];
  isLoading?: boolean;
}

export function BacktestTradeList({ trades, isLoading }: BacktestTradeListProps) {
  const [expanded, setExpanded] = useState(true);
  const [sortBy, setSortBy] = useState<'time' | 'pnl'>('time');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [expandedTradeId, setExpandedTradeId] = useState<string | null>(null);

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
    const year = date.getUTCFullYear();
    const month = String(date.getUTCMonth() + 1).padStart(2, '0');
    const day = String(date.getUTCDate()).padStart(2, '0');
    const hours = String(date.getUTCHours()).padStart(2, '0');
    const minutes = String(date.getUTCMinutes()).padStart(2, '0');
    return `${year}-${month}-${day} ${hours}:${minutes}`;
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
              <div className="space-y-2 max-h-[600px] overflow-y-auto">
                {sortedTrades.map((trade) => {
                  const exitTypeInfo = getExitTypeLabel(trade.exit_type);
                  const isProfitable = trade.realized_pnl >= 0;
                  const isExpanded = expandedTradeId === trade.trade_id;
                  const orderTypeLabel = trade.order_type === 'limit' ? 'Limit' : 'Market';

                  return (
                    <div
                      key={trade.trade_id}
                      className="rounded-lg bg-neutral-800/50 border border-neutral-700/50 hover:border-neutral-600/50 transition-colors"
                    >
                      <div 
                        className="p-3 cursor-pointer"
                        onClick={() => setExpandedTradeId(isExpanded ? null : trade.trade_id)}
                      >
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
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
                            <span className="px-2 py-0.5 rounded text-xs font-medium bg-blue-400/10 text-blue-400">
                              {orderTypeLabel}
                            </span>
                            {trade.r_multiple !== null && trade.r_multiple !== undefined && (
                              <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                                trade.r_multiple >= 0 ? 'bg-emerald-400/10 text-emerald-400' : 'bg-rose-400/10 text-rose-400'
                              }`}>
                                {trade.r_multiple >= 0 ? '+' : ''}{trade.r_multiple.toFixed(1)}R
                              </span>
                            )}
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
                            {isExpanded ? (
                              <ChevronUp className="h-4 w-4 text-neutral-400" />
                            ) : (
                              <ChevronDown className="h-4 w-4 text-neutral-400" />
                            )}
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
                            {trade.order_created_time ? (
                              <span title="Order Created → Filled">
                                <span className="text-purple-400">{formatTime(trade.order_created_time)}</span>
                                <span className="mx-1">→</span>
                                <span>{formatTime(trade.kline_time)}</span>
                              </span>
                            ) : (
                              formatTime(trade.kline_time)
                            )}
                          </div>
                          <div>→ {formatTime(trade.exit_time)}</div>
                          <div>{trade.holding_bars} bars</div>
                          {trade.leverage && trade.leverage > 1 && (
                            <div className="text-blue-400">{trade.leverage}x</div>
                          )}
                        </div>
                      </div>

                      {isExpanded && (
                        <div className="px-3 pb-3 border-t border-neutral-700/50 mt-2 pt-3">
                          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 text-sm">
                            <div className="p-2 rounded bg-neutral-900/50">
                              <div className="flex items-center gap-1 text-neutral-500 text-xs mb-1">
                                <DollarSign className="h-3 w-3" />
                                Margin
                              </div>
                              <div className="text-white font-medium">
                                {trade.margin_usdt ? formatCurrency(trade.margin_usdt) : 'N/A'}
                              </div>
                            </div>
                            
                            <div className="p-2 rounded bg-neutral-900/50">
                              <div className="flex items-center gap-1 text-neutral-500 text-xs mb-1">
                                <DollarSign className="h-3 w-3" />
                                Notional
                              </div>
                              <div className="text-white font-medium">
                                {trade.notional_usdt ? formatCurrency(trade.notional_usdt) : 'N/A'}
                              </div>
                            </div>
                            
                            <div className="p-2 rounded bg-neutral-900/50">
                              <div className="flex items-center gap-1 text-neutral-500 text-xs mb-1">
                                <Percent className="h-3 w-3" />
                                Leverage
                              </div>
                              <div className="text-blue-400 font-medium">
                                {trade.leverage ? `${trade.leverage}x` : 'N/A'}
                              </div>
                            </div>
                            
                            <div className="p-2 rounded bg-neutral-900/50">
                              <div className="flex items-center gap-1 text-neutral-500 text-xs mb-1">
                                <Target className="h-3 w-3" />
                                R Multiple
                              </div>
                              <div className={`font-medium ${
                                trade.r_multiple && trade.r_multiple >= 0 ? 'text-emerald-400' : 'text-rose-400'
                              }`}>
                                {trade.r_multiple !== null && trade.r_multiple !== undefined 
                                  ? `${trade.r_multiple >= 0 ? '+' : ''}${trade.r_multiple.toFixed(2)}R` 
                                  : 'N/A'}
                              </div>
                            </div>
                            
                            {trade.order_type === 'limit' && trade.limit_price && (
                              <div className="p-2 rounded bg-neutral-900/50">
                                <div className="text-neutral-500 text-xs mb-1">Limit Price</div>
                                <div className="text-blue-400 font-medium">
                                  {formatPrice(trade.limit_price)}
                                </div>
                              </div>
                            )}
                            
                            <div className="p-2 rounded bg-neutral-900/50">
                              <div className="text-neutral-500 text-xs mb-1">Original TP</div>
                              <div className="text-emerald-400/70 font-medium">
                                {trade.original_tp_price ? formatPrice(trade.original_tp_price) : 'N/A'}
                                {trade.tp_distance_percent ? (
                                  <span className="text-xs ml-1">({trade.tp_distance_percent.toFixed(1)}%)</span>
                                ) : null}
                              </div>
                            </div>
                            
                            <div className="p-2 rounded bg-neutral-900/50">
                              <div className="text-neutral-500 text-xs mb-1">Original SL</div>
                              <div className="text-rose-400/70 font-medium">
                                {trade.original_sl_price ? formatPrice(trade.original_sl_price) : 'N/A'}
                                {trade.sl_distance_percent ? (
                                  <span className="text-xs ml-1">({trade.sl_distance_percent.toFixed(1)}%)</span>
                                ) : null}
                              </div>
                            </div>
                            
                            <div className="p-2 rounded bg-neutral-900/50">
                              <div className="text-neutral-500 text-xs mb-1">Fees</div>
                              <div className="text-amber-400 font-medium">
                                {trade.fees_total ? formatCurrency(trade.fees_total) : '$0.00'}
                              </div>
                            </div>
                          </div>
                          
                          {trade.close_reason && (
                            <div className="mt-3 p-2 rounded bg-neutral-900/50">
                              <div className="flex items-center gap-1 text-neutral-500 text-xs mb-1">
                                <Info className="h-3 w-3" />
                                Close Reason
                              </div>
                              <div className="text-neutral-300 text-sm">{trade.close_reason}</div>
                            </div>
                          )}
                          
                          <div className="mt-3 flex items-center justify-between">
                            <div className="text-xs text-neutral-500">
                              <span>Workflow: </span>
                              <span className="font-mono text-neutral-400">{trade.workflow_run_id}</span>
                            </div>
                            <Link
                              to={`/workflow?run_id=${trade.workflow_run_id}`}
                              className="flex items-center gap-1 px-2 py-1 rounded text-xs font-medium bg-purple-400/10 text-purple-400 hover:bg-purple-400/20 transition-colors"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <ExternalLink className="h-3 w-3" />
                              View Trace
                            </Link>
                          </div>
                        </div>
                      )}
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
