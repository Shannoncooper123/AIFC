import { useState, useEffect } from 'react';
import { Loader2, Cpu, ChevronUp, ChevronDown, Activity } from 'lucide-react';
import { Card, Button } from '../../../components/ui';
import { useBacktestConcurrency } from '../hooks/useBacktest';

interface ConcurrencyControlProps {
  backtestId: string | null;
  isRunning: boolean;
}

export function ConcurrencyControl({ backtestId, isRunning }: ConcurrencyControlProps) {
  const {
    currentRunning,
    maxConcurrency,
    available,
    isUpdating,
    updateConcurrency,
  } = useBacktestConcurrency(backtestId, isRunning);

  const [inputValue, setInputValue] = useState<number>(maxConcurrency);
  const [showInput, setShowInput] = useState(false);

  useEffect(() => {
    if (maxConcurrency > 0 && !showInput) {
      setInputValue(maxConcurrency);
    }
  }, [maxConcurrency, showInput]);

  if (!isRunning || !backtestId) {
    return null;
  }

  const handleQuickAdjust = async (delta: number) => {
    const newValue = Math.max(1, Math.min(500, maxConcurrency + delta));
    if (newValue !== maxConcurrency) {
      await updateConcurrency(newValue);
    }
  };

  const handleSubmit = async () => {
    const newValue = Math.max(1, Math.min(500, inputValue));
    if (newValue !== maxConcurrency) {
      await updateConcurrency(newValue);
    }
    setShowInput(false);
  };

  const usagePercent = maxConcurrency > 0 ? (currentRunning / maxConcurrency) * 100 : 0;

  return (
    <Card className="bg-neutral-900/50 border-neutral-800">
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Cpu className="h-4 w-4 text-blue-400" />
            <span className="text-sm font-medium text-neutral-200">Concurrency Control</span>
          </div>
          {isUpdating && <Loader2 className="h-4 w-4 text-blue-400 animate-spin" />}
        </div>

        <div className="flex items-center gap-4">
          <div className="flex-1">
            <div className="flex items-baseline gap-2 mb-1">
              <span className="text-2xl font-bold text-white">{currentRunning}</span>
              <span className="text-neutral-500">/</span>
              <span className="text-lg text-neutral-400">{maxConcurrency}</span>
            </div>
            <div className="h-2 bg-neutral-800 rounded-full overflow-hidden">
              <div
                className={`h-full transition-all duration-300 ${
                  usagePercent > 90 ? 'bg-emerald-500' : usagePercent > 50 ? 'bg-blue-500' : 'bg-neutral-600'
                }`}
                style={{ width: `${Math.min(100, usagePercent)}%` }}
              />
            </div>
            <div className="flex justify-between text-xs text-neutral-500 mt-1">
              <span>Running</span>
              <span>{available} available</span>
            </div>
          </div>

          <div className="flex flex-col gap-1">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => handleQuickAdjust(10)}
              disabled={isUpdating || maxConcurrency >= 500}
              className="px-2 py-1"
            >
              <ChevronUp className="h-4 w-4" />
              <span className="text-xs">+10</span>
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => handleQuickAdjust(-10)}
              disabled={isUpdating || maxConcurrency <= 1}
              className="px-2 py-1"
            >
              <ChevronDown className="h-4 w-4" />
              <span className="text-xs">-10</span>
            </Button>
          </div>
        </div>

        {showInput ? (
          <div className="flex items-center gap-2 pt-2 border-t border-neutral-800">
            <input
              type="number"
              min={1}
              max={500}
              value={inputValue}
              onChange={(e) => setInputValue(Math.max(1, parseInt(e.target.value) || 1))}
              className="flex-1 px-3 py-1.5 bg-neutral-800 border border-neutral-700 rounded text-white text-sm focus:outline-none focus:border-blue-500"
              placeholder="Enter max concurrency"
            />
            <Button
              variant="primary"
              size="sm"
              onClick={handleSubmit}
              disabled={isUpdating}
            >
              Apply
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                setShowInput(false);
                setInputValue(maxConcurrency);
              }}
            >
              Cancel
            </Button>
          </div>
        ) : (
          <button
            onClick={() => setShowInput(true)}
            className="w-full text-xs text-neutral-500 hover:text-neutral-300 transition-colors pt-2 border-t border-neutral-800"
          >
            Click to set custom value
          </button>
        )}

        <div className="flex items-center gap-1 text-xs text-neutral-500">
          <Activity className="h-3 w-3" />
          <span>Adjust concurrency to control TPM usage</span>
        </div>
      </div>
    </Card>
  );
}
