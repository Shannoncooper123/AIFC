import { useState } from 'react';
import { Activity } from 'lucide-react';
import { Card, Loading } from '../components/ui';
import {
  RunsList,
  TimelineView,
  useWorkflowRuns,
  useWorkflowTimeline,
  useUniqueSymbols,
} from '../features/workflow';

export function WorkflowPage() {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);

  const runsQuery = useWorkflowRuns(50);
  const timelineQuery = useWorkflowTimeline(selectedRunId);

  const timeline = timelineQuery.data?.timeline;
  const uniqueSymbols = useUniqueSymbols(timeline);

  const handleSelectRun = (runId: string) => {
    setSelectedRunId(runId);
    setSelectedSymbol(null);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold tracking-tight text-white">Workflow Trace</h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        <Card className="lg:col-span-1">
          <div className="text-sm text-neutral-400 mb-4">Recent Runs</div>
          <RunsList
            runs={runsQuery.data?.runs ?? []}
            selectedRunId={selectedRunId}
            onSelectRun={handleSelectRun}
          />
        </Card>

        <div className="lg:col-span-3 space-y-4">
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
