import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Activity, RefreshCw } from 'lucide-react';
import { Card, Loading } from '../components/ui';
import {
  RunsList,
  TimelineView,
  useWorkflowRuns,
  useWorkflowTimeline,
  useUniqueSymbols,
} from '../features/workflow';

export function WorkflowPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialRunId = searchParams.get('run_id');
  
  const [selectedRunId, setSelectedRunId] = useState<string | null>(initialRunId);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);

  useEffect(() => {
    const runIdFromUrl = searchParams.get('run_id');
    if (runIdFromUrl && runIdFromUrl !== selectedRunId) {
      setSelectedRunId(runIdFromUrl);
      setSelectedSymbol(null);
    }
  }, [searchParams]);

  const { data: runsData, refetch: refetchRuns } = useWorkflowRuns(50);
  const timelineQuery = useWorkflowTimeline(selectedRunId);

  const timeline = timelineQuery.data?.timeline;
  const uniqueSymbols = useUniqueSymbols(timeline);

  const handleSelectRun = (runId: string) => {
    setSelectedRunId(runId);
    setSelectedSymbol(null);
    setSearchParams({ run_id: runId });
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold tracking-tight text-white">Workflow Trace</h1>
        <button
          onClick={() => refetchRuns()}
          className="p-2 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-neutral-400 hover:text-white transition-colors"
          title="Refresh runs"
        >
          <RefreshCw className="h-4 w-4" />
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 lg:gap-6">
        <Card className="lg:col-span-1 hidden lg:block">
          <div className="text-sm text-neutral-400 mb-4">Recent Runs</div>
          <RunsList
            runs={runsData?.runs ?? []}
            selectedRunId={selectedRunId}
            onSelectRun={handleSelectRun}
          />
        </Card>

        <details className="lg:hidden border border-neutral-800 rounded-lg bg-[#1a1a1a] p-4">
          <summary className="text-sm text-neutral-400 cursor-pointer">Recent Runs</summary>
          <div className="mt-4">
            <RunsList
              runs={runsData?.runs ?? []}
              selectedRunId={selectedRunId}
              onSelectRun={handleSelectRun}
            />
          </div>
        </details>

        <div className="lg:col-span-3 space-y-4 overflow-x-auto">
          {!selectedRunId && (
            <Card>
              <div className="text-neutral-500 text-center py-12">
                <Activity className="h-12 w-12 mx-auto mb-4 opacity-20" />
                <div>Select a run to view detailed trace</div>
              </div>
            </Card>
          )}

          {selectedRunId && timeline && (
            <Card>
              <div className="text-white font-medium mb-4">Execution Timeline</div>
              <TimelineView 
                timeline={timeline} 
                selectedSymbol={selectedSymbol}
                uniqueSymbols={uniqueSymbols}
                onSymbolSelect={setSelectedSymbol}
              />
            </Card>
          )}

          {selectedRunId && timelineQuery.isLoading && (
            <Card>
              <Loading text="Loading..." />
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
