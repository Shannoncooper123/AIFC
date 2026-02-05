import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Briefcase, Clock, History } from 'lucide-react';
import {
  ReverseConfigPanel,
  ReversePositionsTable,
  ReversePendingOrdersTable,
  ReverseHistoryTable,
  ReverseStatisticsPanel,
  ReverseWorkflowPanel,
} from './components';
import {
  getReversePositions,
  getReversePendingOrders,
  getReverseHistory,
  getReverseStatistics,
  closeReversePosition,
} from '../../services/api/reverse';
import type {
  ReversePosition,
  ReversePendingOrder,
  ReverseHistoryEntry,
  ReverseStatistics,
} from '../../types/reverse';

type TabType = 'positions' | 'orders' | 'history';

export function ReverseTradingPage() {
  const [activeTab, setActiveTab] = useState<TabType>('positions');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const [positions, setPositions] = useState<ReversePosition[]>([]);
  const [pendingOrders, setPendingOrders] = useState<ReversePendingOrder[]>([]);
  const [history, setHistory] = useState<ReverseHistoryEntry[]>([]);
  const [historyLimit, setHistoryLimit] = useState(50);
  const [statistics, setStatistics] = useState<ReverseStatistics>({
    total_trades: 0,
    winning_trades: 0,
    losing_trades: 0,
    win_rate: 0,
    total_pnl: 0,
    avg_pnl: 0,
    max_profit: 0,
    max_loss: 0,
  });

  const fetchData = useCallback(async () => {
    try {
      const [posRes, ordersRes, histRes, statsRes] = await Promise.all([
        getReversePositions(),
        getReversePendingOrders(),
        getReverseHistory(historyLimit),
        getReverseStatistics(),
      ]);

      setPositions(posRes.positions);
      setPendingOrders(ordersRes.orders);
      setHistory(histRes.history);
      setStatistics(statsRes);
    } catch (err) {
      console.error('Failed to fetch reverse trading data:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [historyLimit]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchData();
  };

  const handleClosePosition = async (recordId: string) => {
    if (!confirm('Are you sure you want to close this position? This will cancel the associated TP/SL orders.')) {
      return;
    }
    
    try {
      const result = await closeReversePosition(recordId);
      if (result.success) {
        fetchData();
      } else {
        alert(`Failed to close position: ${result.message}`);
      }
    } catch (err) {
      console.error('Failed to close position:', err);
      alert('Failed to close position');
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Reverse Trading</h1>
          <p className="text-sm text-neutral-400 mt-1">
            Automatically create opposite trades when Agent places limit orders
          </p>
        </div>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="flex items-center gap-2 rounded-lg border border-neutral-700 bg-neutral-800 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      <ReverseConfigPanel onConfigChange={fetchData} />

      <ReverseWorkflowPanel onWorkflowChange={fetchData} />

      <ReverseStatisticsPanel statistics={statistics} loading={loading} />

      <div className="rounded-xl border border-neutral-800 bg-[#1a1a1a] p-6">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
          <div className="flex rounded-lg border border-neutral-800 bg-[#141414] p-1 w-fit">
            <button
              onClick={() => setActiveTab('positions')}
              className={`flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 ${
                activeTab === 'positions'
                  ? 'bg-neutral-800 text-white'
                  : 'text-neutral-400 hover:text-white'
              }`}
            >
              <Briefcase className="h-4 w-4" />
              Positions
              <span className="rounded-full bg-neutral-700 px-2 py-0.5 text-xs">
                {positions.length}
              </span>
            </button>
            <button
              onClick={() => setActiveTab('orders')}
              className={`flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 ${
                activeTab === 'orders'
                  ? 'bg-neutral-800 text-white'
                  : 'text-neutral-400 hover:text-white'
              }`}
            >
              <Clock className="h-4 w-4" />
              Pending Orders
              <span className="rounded-full bg-neutral-700 px-2 py-0.5 text-xs">
                {pendingOrders.length}
              </span>
            </button>
            <button
              onClick={() => setActiveTab('history')}
              className={`flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 ${
                activeTab === 'history'
                  ? 'bg-neutral-800 text-white'
                  : 'text-neutral-400 hover:text-white'
              }`}
            >
              <History className="h-4 w-4" />
              History
              <span className="rounded-full bg-neutral-700 px-2 py-0.5 text-xs">
                {history.length}
              </span>
            </button>
          </div>

          {activeTab === 'history' && (
            <div className="flex items-center gap-2">
              <span className="text-sm text-neutral-400">Show:</span>
              <select
                value={historyLimit}
                onChange={(e) => setHistoryLimit(Number(e.target.value))}
                className="rounded-lg border border-neutral-700 bg-neutral-800 px-3 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none"
              >
                <option value={50}>50 rows</option>
                <option value={100}>100 rows</option>
                <option value={200}>200 rows</option>
                <option value={500}>500 rows</option>
                <option value={1000}>1000 rows</option>
              </select>
            </div>
          )}
        </div>

        {activeTab === 'positions' && (
          <ReversePositionsTable 
            positions={positions} 
            loading={loading} 
            onClosePosition={handleClosePosition}
          />
        )}
        {activeTab === 'orders' && (
          <ReversePendingOrdersTable
            orders={pendingOrders}
            loading={loading}
            onOrderCancelled={fetchData}
          />
        )}
        {activeTab === 'history' && (
          <ReverseHistoryTable history={history} loading={loading} />
        )}
      </div>
    </div>
  );
}
