import { Briefcase, History, TrendingUp, TrendingDown } from 'lucide-react';
import { formatCurrency } from '../../../utils';

export type PositionsTab = 'open' | 'history';

interface PositionsTabsProps {
  activeTab: PositionsTab;
  onTabChange: (tab: PositionsTab) => void;
  openPositionsCount?: number;
  historyCount?: number;
  totalPnl?: number;
  historyLimit: number;
  onHistoryLimitChange: (limit: number) => void;
}

export function PositionsTabs({
  activeTab,
  onTabChange,
  openPositionsCount,
  historyCount,
  totalPnl = 0,
  historyLimit,
  onHistoryLimitChange,
}: PositionsTabsProps) {
  const pnlIsPositive = totalPnl >= 0;

  return (
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div className="flex rounded-lg border border-gray-700 bg-gray-800/50 p-1">
        <button
          onClick={() => onTabChange('open')}
          className={`flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors ${
            activeTab === 'open'
              ? 'bg-gray-700 text-gray-100'
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          <Briefcase className="h-4 w-4" />
          Open Positions
          {openPositionsCount !== undefined && (
            <span className="rounded-full bg-gray-600 px-2 py-0.5 text-xs">
              {openPositionsCount}
            </span>
          )}
        </button>
        <button
          onClick={() => onTabChange('history')}
          className={`flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors ${
            activeTab === 'history'
              ? 'bg-gray-700 text-gray-100'
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          <History className="h-4 w-4" />
          History
          {historyCount !== undefined && (
            <span className="rounded-full bg-gray-600 px-2 py-0.5 text-xs">
              {historyCount}
            </span>
          )}
        </button>
      </div>

      {activeTab === 'history' && (
        <div className="flex items-center gap-4">
          <div
            className={`flex items-center gap-2 rounded-lg border px-3 py-2 ${
              pnlIsPositive
                ? 'border-green-500/30 bg-green-500/10'
                : 'border-red-500/30 bg-red-500/10'
            }`}
          >
            {pnlIsPositive ? (
              <TrendingUp className="h-4 w-4 text-green-400" />
            ) : (
              <TrendingDown className="h-4 w-4 text-red-400" />
            )}
            <span className="text-sm text-gray-400">Total PnL:</span>
            <span
              className={`font-semibold ${
                pnlIsPositive ? 'text-green-400' : 'text-red-400'
              }`}
            >
              {pnlIsPositive ? '+' : ''}
              {formatCurrency(totalPnl)}
            </span>
          </div>

          <div className="flex items-center gap-2">
            <label htmlFor="historyLimit" className="text-sm text-gray-400">
              Show:
            </label>
            <select
              id="historyLimit"
              value={historyLimit}
              onChange={(e) => onHistoryLimitChange(Number(e.target.value))}
              className="rounded-lg border border-gray-600 bg-gray-700 px-3 py-1.5 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              <option value={25}>25</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
              <option value={200}>200</option>
            </select>
          </div>
        </div>
      )}
    </div>
  );
}
