import { useState } from 'react';
import { Briefcase, RefreshCw } from 'lucide-react';
import { PageHeader } from '../components/layout';
import {
  PositionsTable,
  HistoryTable,
  PositionsTabs,
  usePositionsQuery,
  usePositionHistoryQuery,
  type PositionsTab,
} from '../features/positions';

export function PositionsPage() {
  const [activeTab, setActiveTab] = useState<PositionsTab>('open');
  const [historyLimit, setHistoryLimit] = useState(50);

  const {
    data: positionsData,
    isLoading: isLoadingPositions,
    refetch: refetchPositions,
    isFetching: isFetchingPositions,
  } = usePositionsQuery();

  const {
    data: historyData,
    isLoading: isLoadingHistory,
    refetch: refetchHistory,
    isFetching: isFetchingHistory,
  } = usePositionHistoryQuery(historyLimit);

  const isFetching = isFetchingPositions || isFetchingHistory;

  const handleRefresh = () => {
    if (activeTab === 'open') {
      refetchPositions();
    } else {
      refetchHistory();
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 p-6">
      <div className="mx-auto max-w-7xl space-y-6">
        <PageHeader
          title="Positions"
          icon={<Briefcase className="h-6 w-6 text-blue-400" />}
          action={
            <button
              onClick={handleRefresh}
              disabled={isFetching}
              className="flex items-center gap-2 rounded-lg bg-gray-800 px-4 py-2 text-sm text-gray-300 transition-colors hover:bg-gray-700 disabled:opacity-50"
            >
              <RefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          }
        />

        <PositionsTabs
          activeTab={activeTab}
          onTabChange={setActiveTab}
          openPositionsCount={positionsData?.total}
          historyCount={historyData?.total}
          totalPnl={historyData?.total_pnl ?? 0}
          historyLimit={historyLimit}
          onHistoryLimitChange={setHistoryLimit}
        />

        {activeTab === 'open' ? (
          <PositionsTable
            positions={positionsData?.positions ?? []}
            isLoading={isLoadingPositions}
          />
        ) : (
          <HistoryTable
            positions={historyData?.positions ?? []}
            isLoading={isLoadingHistory}
          />
        )}
      </div>
    </div>
  );
}
