import { useState } from 'react';
import { Card } from '../components/ui';
import {
  RunsList,
  RunOverview,
  TimelineView,
  useWorkflowRuns,
  useWorkflowTimeline,
  useWorkflowArtifacts,
  useUniqueSymbols,
} from '../features/workflow';

export function WorkflowPage() {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);

  const runsQuery = useWorkflowRuns(50);
  const timelineQuery = useWorkflowTimeline(selectedRunId);
  const artifactsQuery = useWorkflowArtifacts(selectedRunId);

  const timeline = timelineQuery.data?.timeline;
  const uniqueSymbols = useUniqueSymbols(timeline);

  const handleSelectRun = (runId: string) => {
    setSelectedRunId(runId);
    setSelectedSymbol(null);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Workflow Trace</h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        <Card className="lg:col-span-1">
          <div className="text-sm text-slate-400 mb-4">最近运行</div>
          <RunsList
            runs={runsQuery.data?.runs ?? []}
            selectedRunId={selectedRunId}
            onSelectRun={handleSelectRun}
          />
        </Card>

        <div className="lg:col-span-3 space-y-4">
          {!selectedRunId && (
            <Card>
              <div className="text-slate-400 text-center py-12">
                <div className="text-4xl mb-4">📊</div>
                <div>选择一条运行记录查看详细追踪</div>
              </div>
            </Card>
          )}

          {selectedRunId && timeline && (
            <>
              <Card>
                <RunOverview
                  runId={selectedRunId}
                  timeline={timeline}
                  artifactsCount={artifactsQuery.data?.length || 0}
                  uniqueSymbols={uniqueSymbols}
                  selectedSymbol={selectedSymbol}
                  onSymbolSelect={setSelectedSymbol}
                />
              </Card>

              <Card>
                <div className="text-white font-semibold mb-4">执行时间线</div>
                <TimelineView timeline={timeline} selectedSymbol={selectedSymbol} />
              </Card>
            </>
          )}

          {selectedRunId && timelineQuery.isLoading && (
            <Card>
              <div className="text-slate-400 text-center py-8">
                <div className="animate-spin text-2xl mb-2">⏳</div>
                <div>加载中...</div>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
