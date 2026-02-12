import { CheckCircle, XCircle, Clock, Loader2, Trash2, Eye, RefreshCw, Brain } from 'lucide-react';
import { Card } from '../../../components/ui';

interface BacktestListItem {
  backtest_id: string;
  status: string;
  config: {
    symbols: string[];
    start_time: string;
    end_time: string;
    interval: string;
    initial_balance: number;
    reverse_mode?: boolean;
    enable_reinforcement?: boolean;
  };
  start_timestamp: string;
  end_timestamp?: string;
  total_trades: number;
  total_pnl: number;
  win_rate: number;
}

interface BacktestListProps {
  backtests: BacktestListItem[];
  onSelect: (backtestId: string) => void;
  onDelete: (backtestId: string) => void;
  selectedId?: string;
}

export function BacktestList({ backtests, onSelect, onDelete, selectedId }: BacktestListProps) {
  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'running':
        return <Loader2 className="h-4 w-4 text-blue-400 animate-spin" />;
      case 'completed':
        return <CheckCircle className="h-4 w-4 text-emerald-400" />;
      case 'failed':
        return <XCircle className="h-4 w-4 text-rose-400" />;
      default:
        return <Clock className="h-4 w-4 text-neutral-400" />;
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    const year = date.getUTCFullYear();
    const month = String(date.getUTCMonth() + 1).padStart(2, '0');
    const day = String(date.getUTCDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  };

  const formatCurrency = (value: number) => {
    const formatted = new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(Math.abs(value));
    return value >= 0 ? `+${formatted}` : `-${formatted}`;
  };

  if (backtests.length === 0) {
    return (
      <Card>
        <div className="text-center py-8 text-neutral-500">
          <Clock className="h-12 w-12 mx-auto mb-4 opacity-20" />
          <div>No backtests yet</div>
          <div className="text-sm mt-1">Start a new backtest to see results here</div>
        </div>
      </Card>
    );
  }

  return (
    <Card>
      <div className="text-white font-medium mb-4">Recent Backtests</div>
      <div className="space-y-2">
        {backtests.map((bt) => (
          <div
            key={bt.backtest_id}
            className={`p-3 rounded-lg border transition-colors cursor-pointer ${
              selectedId === bt.backtest_id
                ? 'border-blue-500 bg-blue-500/10'
                : 'border-neutral-800 bg-neutral-800/50 hover:border-neutral-700'
            }`}
            onClick={() => onSelect(bt.backtest_id)}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                {getStatusIcon(bt.status)}
                <div>
                  <div className="text-sm text-white flex items-center gap-2">
                    {bt.config.symbols.join(', ')}
                    {bt.config.enable_reinforcement && (
                      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs bg-purple-500/20 text-purple-400 border border-purple-500/30">
                        <Brain className="h-3 w-3" />
                        RL
                      </span>
                    )}
                    {bt.config.reverse_mode && (
                      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs bg-orange-500/20 text-orange-400 border border-orange-500/30">
                        <RefreshCw className="h-3 w-3" />
                        Rev
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-neutral-500">
                    {formatDate(bt.config.start_time)} - {formatDate(bt.config.end_time)}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-4">
                {bt.status === 'completed' && (
                  <div className="text-right">
                    <div
                      className={`text-sm font-medium ${
                        bt.total_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'
                      }`}
                    >
                      {formatCurrency(bt.total_pnl)}
                    </div>
                    <div className="text-xs text-neutral-500">
                      {bt.total_trades} trades | {(bt.win_rate * 100).toFixed(0)}% win
                    </div>
                  </div>
                )}
                <div className="flex items-center gap-1">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelect(bt.backtest_id);
                    }}
                    className="p-1.5 rounded hover:bg-neutral-700 text-neutral-400 hover:text-white transition-colors"
                    title="View details"
                  >
                    <Eye className="h-4 w-4" />
                  </button>
                  {bt.status !== 'running' && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onDelete(bt.backtest_id);
                      }}
                      className="p-1.5 rounded hover:bg-rose-500/20 text-neutral-400 hover:text-rose-400 transition-colors"
                      title="Delete"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
