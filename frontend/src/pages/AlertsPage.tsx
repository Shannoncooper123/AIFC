import { useState } from 'react';
import { Bell, RefreshCw } from 'lucide-react';
import { PageHeader } from '../components/layout';
import {
  AlertsTable,
  AlertsFilter,
  useAlerts,
  useAlertSymbols,
} from '../features/alerts';

export function AlertsPage() {
  const [selectedSymbol, setSelectedSymbol] = useState<string>('');
  const [limit, setLimit] = useState(50);

  const {
    data: alertsData,
    isLoading: isLoadingAlerts,
    refetch,
    isFetching,
  } = useAlerts(limit, selectedSymbol || undefined);

  const { data: symbolsData } = useAlertSymbols();

  const clearFilters = () => {
    setSelectedSymbol('');
    setLimit(50);
  };

  const hasFilters = selectedSymbol !== '' || limit !== 50;

  return (
    <div className="min-h-screen p-6">
      <div className="mx-auto max-w-7xl space-y-6">
        <PageHeader
          title="Alerts"
          icon={<Bell className="h-6 w-6 text-neutral-400" />}
          badge={
            alertsData && (
              <span className="rounded-full bg-[#1a1a1a] border border-[#2a2a2a] px-3 py-1 text-sm text-neutral-300">
                {alertsData.total} total
              </span>
            )
          }
          action={
            <button
              onClick={() => refetch()}
              disabled={isFetching}
              className="flex items-center gap-2 rounded-lg bg-[#1a1a1a] border border-[#2a2a2a] px-4 py-2 text-sm text-neutral-300 transition-all duration-200 hover:bg-[#222222] hover:border-[#3a3a3a] disabled:opacity-50"
            >
              <RefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          }
        />

        <AlertsFilter
          selectedSymbol={selectedSymbol}
          onSymbolChange={setSelectedSymbol}
          limit={limit}
          onLimitChange={setLimit}
          symbols={symbolsData?.symbols ?? []}
          hasFilters={hasFilters}
          onClear={clearFilters}
        />

        <AlertsTable alerts={alertsData?.alerts ?? []} isLoading={isLoadingAlerts} />
      </div>
    </div>
  );
}
