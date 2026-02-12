import { useMemo } from 'react';
import { TrendingUp, TrendingDown, Target, BarChart3, DollarSign, Percent, Activity, Scale, Zap, Clock, ArrowUpCircle, ArrowDownCircle, Brain, Sparkles, RefreshCcw } from 'lucide-react';
import { Card } from '../../../components/ui';
import type { ReinforcementStats } from '../../../services/api/backtest';

interface Trade {
  trade_id: string;
  order_type?: string;
  side?: string;
  realized_pnl: number;
  exit_type: string;
}

interface SideStats {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  total_pnl: number;
  win_rate: number;
  avg_win: number;
  avg_loss: number;
}

interface BacktestResultsProps {
  result: {
    total_trades: number;
    winning_trades: number;
    losing_trades: number;
    total_pnl: number;
    win_rate: number;
    return_rate: number;
    final_balance: number;
    avg_win?: number;
    avg_loss?: number;
    profit_factor?: number;
    max_drawdown?: number;
    total_klines_analyzed?: number;
    completed_batches?: number;
    total_batches?: number;
    long_stats?: SideStats;
    short_stats?: SideStats;
    reinforcement_stats?: ReinforcementStats;
    config: {
      initial_balance: number;
      concurrency?: number;
      enable_reinforcement?: boolean;
    };
  };
  trades?: Trade[];
}

interface OrderTypeStats {
  total: number;
  wins: number;
  losses: number;
  totalPnl: number;
  winRate: number;
  avgWin: number;
  avgLoss: number;
}

export function BacktestResults({ result, trades = [] }: BacktestResultsProps) {
  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
  };

  const formatPercent = (value: number) => {
    return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
  };

  const isProfitable = result.total_pnl >= 0;
  const profitFactor = result.profit_factor ?? 0;

  const { marketStats, limitStats, longStats, shortStats } = useMemo(() => {
    const calculateStats = (filteredTrades: Trade[]): OrderTypeStats => {
      const wins = filteredTrades.filter(t => t.realized_pnl > 0);
      const losses = filteredTrades.filter(t => t.realized_pnl <= 0);
      const totalPnl = filteredTrades.reduce((sum, t) => sum + t.realized_pnl, 0);
      const totalWinPnl = wins.reduce((sum, t) => sum + t.realized_pnl, 0);
      const totalLossPnl = losses.reduce((sum, t) => sum + t.realized_pnl, 0);
      
      return {
        total: filteredTrades.length,
        wins: wins.length,
        losses: losses.length,
        totalPnl,
        winRate: filteredTrades.length > 0 ? wins.length / filteredTrades.length : 0,
        avgWin: wins.length > 0 ? totalWinPnl / wins.length : 0,
        avgLoss: losses.length > 0 ? totalLossPnl / losses.length : 0,
      };
    };

    const marketTrades = trades.filter(t => t.order_type === 'market' || !t.order_type);
    const limitTrades = trades.filter(t => t.order_type === 'limit');
    const longTrades = trades.filter(t => t.side?.toLowerCase() === 'long');
    const shortTrades = trades.filter(t => t.side?.toLowerCase() === 'short');

    return {
      marketStats: calculateStats(marketTrades),
      limitStats: calculateStats(limitTrades),
      longStats: calculateStats(longTrades),
      shortStats: calculateStats(shortTrades),
    };
  }, [trades]);

  const displayLongStats = result.long_stats || {
    total_trades: longStats.total,
    winning_trades: longStats.wins,
    losing_trades: longStats.losses,
    total_pnl: longStats.totalPnl,
    win_rate: longStats.winRate,
    avg_win: longStats.avgWin,
    avg_loss: longStats.avgLoss,
  };

  const displayShortStats = result.short_stats || {
    total_trades: shortStats.total,
    winning_trades: shortStats.wins,
    losing_trades: shortStats.losses,
    total_pnl: shortStats.totalPnl,
    win_rate: shortStats.winRate,
    avg_win: shortStats.avgWin,
    avg_loss: shortStats.avgLoss,
  };

  return (
    <Card>
      <div className="space-y-6">
        <div className="flex items-center gap-2 text-white font-medium">
          <BarChart3 className="h-5 w-5 text-blue-400" />
          Backtest Results
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="p-4 rounded-lg bg-neutral-800/50">
            <div className="flex items-center gap-2 text-neutral-400 text-sm mb-1">
              <DollarSign className="h-4 w-4" />
              Total P&L
            </div>
            <div
              className={`text-xl font-semibold ${
                isProfitable ? 'text-emerald-400' : 'text-rose-400'
              }`}
            >
              {formatCurrency(result.total_pnl)}
            </div>
          </div>

          <div className="p-4 rounded-lg bg-neutral-800/50">
            <div className="flex items-center gap-2 text-neutral-400 text-sm mb-1">
              <Percent className="h-4 w-4" />
              Return Rate
            </div>
            <div
              className={`text-xl font-semibold ${
                result.return_rate >= 0 ? 'text-emerald-400' : 'text-rose-400'
              }`}
            >
              {formatPercent(result.return_rate)}
            </div>
          </div>

          <div className="p-4 rounded-lg bg-neutral-800/50">
            <div className="flex items-center gap-2 text-neutral-400 text-sm mb-1">
              <Target className="h-4 w-4" />
              Win Rate
            </div>
            <div className="text-xl font-semibold text-white">
              {(result.win_rate * 100).toFixed(1)}%
            </div>
          </div>

          <div className="p-4 rounded-lg bg-neutral-800/50">
            <div className="flex items-center gap-2 text-neutral-400 text-sm mb-1">
              <Scale className="h-4 w-4" />
              Profit Factor
            </div>
            <div className={`text-xl font-semibold ${profitFactor >= 1 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {profitFactor.toFixed(2)}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="p-4 rounded-lg bg-neutral-800/50">
            <div className="flex items-center gap-2 text-neutral-400 text-sm mb-1">
              <BarChart3 className="h-4 w-4" />
              Total Trades
            </div>
            <div className="text-xl font-semibold text-white">{result.total_trades}</div>
          </div>

          <div className="p-4 rounded-lg bg-neutral-800/50">
            <div className="text-neutral-400 text-sm mb-1">Winning Trades</div>
            <div className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-emerald-400" />
              <span className="text-lg font-medium text-emerald-400">{result.winning_trades}</span>
            </div>
          </div>

          <div className="p-4 rounded-lg bg-neutral-800/50">
            <div className="text-neutral-400 text-sm mb-1">Losing Trades</div>
            <div className="flex items-center gap-2">
              <TrendingDown className="h-4 w-4 text-rose-400" />
              <span className="text-lg font-medium text-rose-400">{result.losing_trades}</span>
            </div>
          </div>

          <div className="p-4 rounded-lg bg-neutral-800/50">
            <div className="text-neutral-400 text-sm mb-1">K-lines Analyzed</div>
            <div className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-blue-400" />
              <span className="text-lg font-medium text-white">{result.total_klines_analyzed ?? 0}</span>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="p-4 rounded-lg bg-neutral-800/50">
            <div className="text-neutral-400 text-sm mb-1">Avg Win</div>
            <div className="text-lg font-medium text-emerald-400">
              {formatCurrency(result.avg_win ?? 0)}
            </div>
          </div>

          <div className="p-4 rounded-lg bg-neutral-800/50">
            <div className="text-neutral-400 text-sm mb-1">Avg Loss</div>
            <div className="text-lg font-medium text-rose-400">
              {formatCurrency(result.avg_loss ?? 0)}
            </div>
          </div>

          <div className="p-4 rounded-lg bg-neutral-800/50">
            <div className="text-neutral-400 text-sm mb-1">Max Drawdown</div>
            <div className="text-lg font-medium text-rose-400">
              {formatCurrency(result.max_drawdown ?? 0)}
            </div>
          </div>

          <div className="p-4 rounded-lg bg-neutral-800/50">
            <div className="text-neutral-400 text-sm mb-1">Final Balance</div>
            <div className="text-lg font-medium text-white">{formatCurrency(result.final_balance)}</div>
            <div className="text-xs text-neutral-500">
              Started: {formatCurrency(result.config.initial_balance)}
            </div>
          </div>
        </div>

        {(displayLongStats.total_trades > 0 || displayShortStats.total_trades > 0) && (
          <div className="border-t border-neutral-700/50 pt-6">
            <div className="text-white font-medium mb-4">Performance by Position Side</div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="p-4 rounded-lg bg-gradient-to-br from-emerald-500/10 to-emerald-600/5 border border-emerald-500/20">
                <div className="flex items-center gap-2 mb-3">
                  <ArrowUpCircle className="h-5 w-5 text-emerald-400" />
                  <span className="text-emerald-400 font-medium">Long Positions</span>
                  <span className="text-neutral-500 text-sm">({displayLongStats.total_trades} trades)</span>
                </div>
                
                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <div className="text-neutral-500 text-xs mb-1">P&L</div>
                    <div className={`text-lg font-semibold ${displayLongStats.total_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {formatCurrency(displayLongStats.total_pnl)}
                    </div>
                  </div>
                  <div>
                    <div className="text-neutral-500 text-xs mb-1">Win Rate</div>
                    <div className="text-lg font-semibold text-white">
                      {(displayLongStats.win_rate * 100).toFixed(1)}%
                    </div>
                  </div>
                  <div>
                    <div className="text-neutral-500 text-xs mb-1">W/L</div>
                    <div className="text-lg font-semibold">
                      <span className="text-emerald-400">{displayLongStats.winning_trades}</span>
                      <span className="text-neutral-500">/</span>
                      <span className="text-rose-400">{displayLongStats.losing_trades}</span>
                    </div>
                  </div>
                </div>
                
                <div className="grid grid-cols-2 gap-3 mt-3 pt-3 border-t border-emerald-500/20">
                  <div>
                    <div className="text-neutral-500 text-xs mb-1">Avg Win</div>
                    <div className="text-sm font-medium text-emerald-400">
                      {formatCurrency(displayLongStats.avg_win)}
                    </div>
                  </div>
                  <div>
                    <div className="text-neutral-500 text-xs mb-1">Avg Loss</div>
                    <div className="text-sm font-medium text-rose-400">
                      {formatCurrency(displayLongStats.avg_loss)}
                    </div>
                  </div>
                </div>
              </div>

              <div className="p-4 rounded-lg bg-gradient-to-br from-rose-500/10 to-rose-600/5 border border-rose-500/20">
                <div className="flex items-center gap-2 mb-3">
                  <ArrowDownCircle className="h-5 w-5 text-rose-400" />
                  <span className="text-rose-400 font-medium">Short Positions</span>
                  <span className="text-neutral-500 text-sm">({displayShortStats.total_trades} trades)</span>
                </div>
                
                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <div className="text-neutral-500 text-xs mb-1">P&L</div>
                    <div className={`text-lg font-semibold ${displayShortStats.total_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {formatCurrency(displayShortStats.total_pnl)}
                    </div>
                  </div>
                  <div>
                    <div className="text-neutral-500 text-xs mb-1">Win Rate</div>
                    <div className="text-lg font-semibold text-white">
                      {(displayShortStats.win_rate * 100).toFixed(1)}%
                    </div>
                  </div>
                  <div>
                    <div className="text-neutral-500 text-xs mb-1">W/L</div>
                    <div className="text-lg font-semibold">
                      <span className="text-emerald-400">{displayShortStats.winning_trades}</span>
                      <span className="text-neutral-500">/</span>
                      <span className="text-rose-400">{displayShortStats.losing_trades}</span>
                    </div>
                  </div>
                </div>
                
                <div className="grid grid-cols-2 gap-3 mt-3 pt-3 border-t border-rose-500/20">
                  <div>
                    <div className="text-neutral-500 text-xs mb-1">Avg Win</div>
                    <div className="text-sm font-medium text-emerald-400">
                      {formatCurrency(displayShortStats.avg_win)}
                    </div>
                  </div>
                  <div>
                    <div className="text-neutral-500 text-xs mb-1">Avg Loss</div>
                    <div className="text-sm font-medium text-rose-400">
                      {formatCurrency(displayShortStats.avg_loss)}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 强化学习统计 */}
        {result.reinforcement_stats && result.config.enable_reinforcement && (
          <div className="border-t border-neutral-700/50 pt-6">
            <div className="flex items-center gap-2 text-white font-medium mb-4">
              <Brain className="h-5 w-5 text-purple-400" />
              Reinforcement Learning Results
            </div>
            
            <div className="p-4 rounded-lg bg-gradient-to-br from-purple-500/10 to-blue-500/10 border border-purple-500/20">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <div className="flex items-center gap-1 text-neutral-400 text-xs mb-1">
                    <RefreshCcw className="h-3 w-3" />
                    Sessions
                  </div>
                  <div className="text-xl font-semibold text-white">
                    {result.reinforcement_stats.total_sessions}
                  </div>
                  <div className="text-xs text-neutral-500">Losing trades analyzed</div>
                </div>
                
                <div>
                  <div className="flex items-center gap-1 text-neutral-400 text-xs mb-1">
                    <Sparkles className="h-3 w-3" />
                    Improved
                  </div>
                  <div className="text-xl font-semibold text-emerald-400">
                    {result.reinforcement_stats.improved_count}
                  </div>
                  <div className="text-xs text-neutral-500">
                    {(result.reinforcement_stats.improvement_rate * 100).toFixed(1)}% success rate
                  </div>
                </div>
                
                <div>
                  <div className="flex items-center gap-1 text-neutral-400 text-xs mb-1">
                    <Activity className="h-3 w-3" />
                    Avg Rounds
                  </div>
                  <div className="text-xl font-semibold text-white">
                    {result.reinforcement_stats.avg_rounds}
                  </div>
                  <div className="text-xs text-neutral-500">per session</div>
                </div>
                
                <div>
                  <div className="flex items-center gap-1 text-neutral-400 text-xs mb-1">
                    <Target className="h-3 w-3" />
                    Outcome Distribution
                  </div>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {Object.entries(result.reinforcement_stats.outcome_distribution).map(([outcome, count]) => (
                      <span
                        key={outcome}
                        className={`px-2 py-0.5 rounded text-xs font-medium ${
                          outcome === 'profit' ? 'bg-emerald-500/20 text-emerald-400' :
                          outcome === 'loss' ? 'bg-rose-500/20 text-rose-400' :
                          outcome === 'no_trade' ? 'bg-blue-500/20 text-blue-400' :
                          'bg-neutral-500/20 text-neutral-400'
                        }`}
                      >
                        {outcome}: {count}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
              
              {result.reinforcement_stats.improved_count > 0 && (
                <div className="mt-4 pt-4 border-t border-purple-500/20">
                  <div className="flex items-center gap-2 text-sm text-purple-300">
                    <Sparkles className="h-4 w-4" />
                    <span>
                      Successfully converted {result.reinforcement_stats.improved_count} losing trade(s) 
                      to profitable/neutral outcomes through iterative feedback
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {trades.length > 0 && (
          <>
            <div className="border-t border-neutral-700/50 pt-6">
              <div className="text-white font-medium mb-4">Performance by Order Type</div>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-4 rounded-lg bg-gradient-to-br from-amber-500/10 to-amber-600/5 border border-amber-500/20">
                  <div className="flex items-center gap-2 mb-3">
                    <Zap className="h-5 w-5 text-amber-400" />
                    <span className="text-amber-400 font-medium">Market Orders</span>
                    <span className="text-neutral-500 text-sm">({marketStats.total} trades)</span>
                  </div>
                  
                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <div className="text-neutral-500 text-xs mb-1">P&L</div>
                      <div className={`text-lg font-semibold ${marketStats.totalPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {formatCurrency(marketStats.totalPnl)}
                      </div>
                    </div>
                    <div>
                      <div className="text-neutral-500 text-xs mb-1">Win Rate</div>
                      <div className="text-lg font-semibold text-white">
                        {(marketStats.winRate * 100).toFixed(1)}%
                      </div>
                    </div>
                    <div>
                      <div className="text-neutral-500 text-xs mb-1">W/L</div>
                      <div className="text-lg font-semibold">
                        <span className="text-emerald-400">{marketStats.wins}</span>
                        <span className="text-neutral-500">/</span>
                        <span className="text-rose-400">{marketStats.losses}</span>
                      </div>
                    </div>
                  </div>
                  
                  <div className="grid grid-cols-2 gap-3 mt-3 pt-3 border-t border-amber-500/20">
                    <div>
                      <div className="text-neutral-500 text-xs mb-1">Avg Win</div>
                      <div className="text-sm font-medium text-emerald-400">
                        {formatCurrency(marketStats.avgWin)}
                      </div>
                    </div>
                    <div>
                      <div className="text-neutral-500 text-xs mb-1">Avg Loss</div>
                      <div className="text-sm font-medium text-rose-400">
                        {formatCurrency(marketStats.avgLoss)}
                      </div>
                    </div>
                  </div>
                </div>

                <div className="p-4 rounded-lg bg-gradient-to-br from-purple-500/10 to-purple-600/5 border border-purple-500/20">
                  <div className="flex items-center gap-2 mb-3">
                    <Clock className="h-5 w-5 text-purple-400" />
                    <span className="text-purple-400 font-medium">Limit Orders</span>
                    <span className="text-neutral-500 text-sm">({limitStats.total} trades)</span>
                  </div>
                  
                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <div className="text-neutral-500 text-xs mb-1">P&L</div>
                      <div className={`text-lg font-semibold ${limitStats.totalPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {formatCurrency(limitStats.totalPnl)}
                      </div>
                    </div>
                    <div>
                      <div className="text-neutral-500 text-xs mb-1">Win Rate</div>
                      <div className="text-lg font-semibold text-white">
                        {(limitStats.winRate * 100).toFixed(1)}%
                      </div>
                    </div>
                    <div>
                      <div className="text-neutral-500 text-xs mb-1">W/L</div>
                      <div className="text-lg font-semibold">
                        <span className="text-emerald-400">{limitStats.wins}</span>
                        <span className="text-neutral-500">/</span>
                        <span className="text-rose-400">{limitStats.losses}</span>
                      </div>
                    </div>
                  </div>
                  
                  <div className="grid grid-cols-2 gap-3 mt-3 pt-3 border-t border-purple-500/20">
                    <div>
                      <div className="text-neutral-500 text-xs mb-1">Avg Win</div>
                      <div className="text-sm font-medium text-emerald-400">
                        {formatCurrency(limitStats.avgWin)}
                      </div>
                    </div>
                    <div>
                      <div className="text-neutral-500 text-xs mb-1">Avg Loss</div>
                      <div className="text-sm font-medium text-rose-400">
                        {formatCurrency(limitStats.avgLoss)}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </Card>
  );
}
