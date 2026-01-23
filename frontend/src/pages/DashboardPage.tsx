import { RefreshCw } from 'lucide-react';
import { ErrorAlert } from '../components/ui';
import { PageHeader } from '../components/layout';
import {
  AccountCard,
  ServiceCard,
  SummaryCard,
  useDashboardData,
} from '../features/dashboard';

export function DashboardPage() {
  const {
    systemStatus,
    tradeState,
    summary,
    isLoading,
    hasError,
    refetchSystem,
  } = useDashboardData();

  return (
    <div className="min-h-screen bg-gray-900 p-6">
      <div className="mx-auto max-w-7xl space-y-6">
        <PageHeader
          title="Dashboard"
          action={
            <button
              onClick={() => refetchSystem()}
              disabled={isLoading}
              className="flex items-center gap-2 rounded-lg bg-gray-800 px-4 py-2 text-sm text-gray-300 transition-colors hover:bg-gray-700 disabled:opacity-50"
            >
              <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          }
        />

        {hasError && (
          <ErrorAlert message="Failed to load some data. Please try again." />
        )}

        <div className="grid gap-6 lg:grid-cols-2">
          {tradeState?.account && <AccountCard account={tradeState.account} />}
          {summary && <SummaryCard summary={summary} />}
        </div>

        <div>
          <h2 className="mb-4 text-lg font-semibold text-gray-100">Services</h2>
          {isLoading ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {[1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="h-32 animate-pulse rounded-xl border border-gray-700 bg-gray-800/50"
                />
              ))}
            </div>
          ) : systemStatus?.services ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {Object.values(systemStatus.services).map((service) => (
                <ServiceCard key={service.name} service={service} />
              ))}
            </div>
          ) : (
            <p className="text-gray-500">No services available</p>
          )}
        </div>

        {systemStatus && (
          <div className="text-right text-xs text-gray-500">
            Last updated: {new Date(systemStatus.timestamp).toLocaleString()}
          </div>
        )}
      </div>
    </div>
  );
}
