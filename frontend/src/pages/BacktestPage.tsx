import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { FlaskConical } from 'lucide-react';
import { Card } from '../components/ui';
import {
  BacktestConfig,
  BacktestProgress,
  BacktestResults,
  BacktestList,
  BacktestTradeList,
  ConcurrencyControl,
  useBacktestList,
  useBacktestStatus,
  useBacktestTrades,
  useStartBacktest,
  useStopBacktest,
  useDeleteBacktest,
} from '../features/backtest';
import type { BacktestConfigData } from '../features/backtest/components/BacktestConfig';

export function BacktestPage() {
  const navigate = useNavigate();
  const [selectedBacktestId, setSelectedBacktestId] = useState<string | null>(null);

  const { data: listData } = useBacktestList(20);
  const { data: statusData } = useBacktestStatus(selectedBacktestId);
  const isBacktestRunning = statusData?.status === 'running';
  const { data: tradesData, isLoading: tradesLoading } = useBacktestTrades(selectedBacktestId, 100, isBacktestRunning);

  const startMutation = useStartBacktest();
  const stopMutation = useStopBacktest();
  const deleteMutation = useDeleteBacktest();

  const handleStart = useCallback(
    async (config: BacktestConfigData) => {
      try {
        const result = await startMutation.mutateAsync({
          symbols: config.symbols,
          start_time: config.startTime + ':00Z',
          end_time: config.endTime + ':00Z',
          interval: config.interval,
          initial_balance: config.initialBalance,
          concurrency: config.concurrency,
          fixed_margin_usdt: config.fixedMarginUsdt,
          fixed_leverage: config.fixedLeverage,
        });
        setSelectedBacktestId(result.backtest_id);
      } catch (error) {
        console.error('Failed to start backtest:', error);
      }
    },
    [startMutation]
  );

  const handleStop = useCallback(() => {
    if (selectedBacktestId) {
      stopMutation.mutate(selectedBacktestId);
    }
  }, [selectedBacktestId, stopMutation]);

  const handleDelete = useCallback(
    async (backtestId: string) => {
      try {
        await deleteMutation.mutateAsync(backtestId);
        if (selectedBacktestId === backtestId) {
          setSelectedBacktestId(null);
        }
      } catch (error) {
        console.error('Failed to delete backtest:', error);
      }
    },
    [deleteMutation, selectedBacktestId]
  );

  const handleViewWorkflow = useCallback(
    (runId: string) => {
      navigate(`/workflow?run_id=${runId}`);
    },
    [navigate]
  );

  const isRunning = isBacktestRunning;
  const isCompleted = statusData?.status === 'completed';
  const result = statusData?.result;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <FlaskConical className="h-6 w-6 text-blue-400" />
        <h1 className="text-xl font-semibold tracking-tight text-white">Backtest</h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 space-y-6">
          <BacktestConfig
            onStart={handleStart}
            isLoading={startMutation.isPending}
            disabled={isRunning}
          />

          <BacktestList
            backtests={listData?.backtests ?? []}
            onSelect={setSelectedBacktestId}
            onDelete={handleDelete}
            selectedId={selectedBacktestId ?? undefined}
          />
        </div>

        <div className="lg:col-span-2 space-y-6">
          {selectedBacktestId && statusData && (
            <BacktestProgress
              backtestId={selectedBacktestId}
              status={statusData.status}
              progress={statusData.progress}
              onStop={isRunning ? handleStop : undefined}
            />
          )}

          {selectedBacktestId && isRunning && (
            <ConcurrencyControl
              backtestId={selectedBacktestId}
              isRunning={isRunning}
            />
          )}

          {isCompleted && result && <BacktestResults result={result} trades={tradesData?.trades ?? []} />}

          {/* 显示交易列表：运行中或已完成时都显示 */}
          {selectedBacktestId && (isRunning || isCompleted) && (
            <BacktestTradeList 
              trades={tradesData?.trades ?? []} 
              cancelledOrders={tradesData?.cancelledOrders ?? []}
              isLoading={tradesLoading} 
            />
          )}

          {selectedBacktestId && result?.workflow_runs && result.workflow_runs.length > 0 && (
            <Card>
              <div className="text-white font-medium mb-4">Workflow Runs</div>
              <div className="text-sm text-neutral-400 mb-2">
                {result.workflow_runs.length} workflow executions
              </div>
              <div className="flex flex-wrap gap-2">
                {result.workflow_runs.slice(0, 10).map((runId) => (
                  <button
                    key={runId}
                    onClick={() => handleViewWorkflow(runId)}
                    className="px-3 py-1.5 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-xs text-neutral-300 hover:text-white transition-colors"
                  >
                    {runId.slice(0, 12)}...
                  </button>
                ))}
                {result.workflow_runs.length > 10 && (
                  <span className="px-3 py-1.5 text-xs text-neutral-500">
                    +{result.workflow_runs.length - 10} more
                  </span>
                )}
              </div>
            </Card>
          )}

          {!selectedBacktestId && (
            <Card>
              <div className="text-center py-12 text-neutral-500">
                <FlaskConical className="h-12 w-12 mx-auto mb-4 opacity-20" />
                <div>Configure and start a backtest</div>
                <div className="text-sm mt-1">
                  Or select a previous backtest from the list
                </div>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
