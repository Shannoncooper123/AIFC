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
    <div className="min-h-screen p-6">
      <div className="mx-auto max-w-7xl space-y-6">
        <PageHeader
          title="Positions"
          icon={<Briefcase className="h-6 w-6 text-neutral-400" />}
          action={
            <button
              onClick={handleRefresh}
              disabled={isFetching}
              className="flex items-center gap-2 rounded-lg bg-[#1a1a1a] border border-[#2a2a2a] px-4 py-2 text-sm text-neutral-300 transition-all duration-200 hover:bg-[#222222] hover:border-[#3a3a3a] disabled:opacity-50"
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
