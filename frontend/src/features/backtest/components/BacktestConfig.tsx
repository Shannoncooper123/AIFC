import { useState } from 'react';
import { Play, Calendar, DollarSign, Clock, Cpu } from 'lucide-react';
import { Button, Card } from '../../../components/ui';

interface BacktestConfigProps {
  onStart: (config: BacktestConfigData) => void;
  isLoading?: boolean;
  disabled?: boolean;
}

export interface BacktestConfigData {
  symbols: string[];
  startTime: string;
  endTime: string;
  interval: string;
  initialBalance: number;
  concurrency: number;
}

export function BacktestConfig({ onStart, isLoading, disabled }: BacktestConfigProps) {
  const [config, setConfig] = useState<BacktestConfigData>({
    symbols: ['BTCUSDT', 'ETHUSDT'],
    startTime: getDefaultStartTime(),
    endTime: getDefaultEndTime(),
    interval: '15m',
    initialBalance: 10000,
    concurrency: 5,
  });

  function getDefaultStartTime(): string {
    const date = new Date();
    date.setDate(date.getDate() - 7);
    return date.toISOString().slice(0, 16);
  }

  function getDefaultEndTime(): string {
    const date = new Date();
    date.setDate(date.getDate() - 1);
    return date.toISOString().slice(0, 16);
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onStart(config);
  };

  const handleSymbolToggle = (symbol: string) => {
    setConfig((prev) => ({
      ...prev,
      symbols: prev.symbols.includes(symbol)
        ? prev.symbols.filter((s) => s !== symbol)
        : [...prev.symbols, symbol],
    }));
  };

  return (
    <Card>
      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="flex items-center gap-2 text-white font-medium">
          <Clock className="h-5 w-5 text-blue-400" />
          Backtest Configuration
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-neutral-400 mb-2">Symbols</label>
            <div className="flex gap-2">
              {['BTCUSDT', 'ETHUSDT'].map((symbol) => (
                <button
                  key={symbol}
                  type="button"
                  onClick={() => handleSymbolToggle(symbol)}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    config.symbols.includes(symbol)
                      ? 'bg-blue-500/20 text-blue-400 border border-blue-500/50'
                      : 'bg-neutral-800 text-neutral-400 border border-neutral-700 hover:border-neutral-600'
                  }`}
                >
                  {symbol.replace('USDT', '')}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-sm text-neutral-400 mb-2">Interval</label>
            <select
              value={config.interval}
              onChange={(e) => setConfig((prev) => ({ ...prev, interval: e.target.value }))}
              className="w-full px-4 py-2 rounded-lg bg-neutral-800 border border-neutral-700 text-white focus:border-blue-500 focus:outline-none"
            >
              <option value="15m">15 minutes</option>
              <option value="1h">1 hour</option>
              <option value="4h">4 hours</option>
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-neutral-400 mb-2">
              <Calendar className="inline h-4 w-4 mr-1" />
              Start Time
            </label>
            <input
              type="datetime-local"
              value={config.startTime}
              onChange={(e) => setConfig((prev) => ({ ...prev, startTime: e.target.value }))}
              className="w-full px-4 py-2 rounded-lg bg-neutral-800 border border-neutral-700 text-white focus:border-blue-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-sm text-neutral-400 mb-2">
              <Calendar className="inline h-4 w-4 mr-1" />
              End Time
            </label>
            <input
              type="datetime-local"
              value={config.endTime}
              onChange={(e) => setConfig((prev) => ({ ...prev, endTime: e.target.value }))}
              className="w-full px-4 py-2 rounded-lg bg-neutral-800 border border-neutral-700 text-white focus:border-blue-500 focus:outline-none"
            />
          </div>
        </div>

        <div>
          <label className="block text-sm text-neutral-400 mb-2">
            <DollarSign className="inline h-4 w-4 mr-1" />
            Initial Balance (USDT)
          </label>
          <input
            type="number"
            value={config.initialBalance}
            onChange={(e) =>
              setConfig((prev) => ({ ...prev, initialBalance: parseFloat(e.target.value) || 10000 }))
            }
            min={100}
            max={1000000}
            step={100}
            className="w-full px-4 py-2 rounded-lg bg-neutral-800 border border-neutral-700 text-white focus:border-blue-500 focus:outline-none"
          />
        </div>

        <div>
          <label className="block text-sm text-neutral-400 mb-2">
            <Cpu className="inline h-4 w-4 mr-1" />
            Concurrency
          </label>
          <div className="flex items-center gap-4">
            <input
              type="range"
              value={config.concurrency}
              onChange={(e) =>
                setConfig((prev) => ({ ...prev, concurrency: parseInt(e.target.value, 10) }))
              }
              min={1}
              max={50}
              step={1}
              className="flex-1 h-2 rounded-lg appearance-none cursor-pointer bg-neutral-800 border border-neutral-700 accent-blue-500"
            />
            <span className="min-w-[2rem] text-center text-white font-medium bg-neutral-800 border border-neutral-700 px-2 py-1 rounded-lg">
              {config.concurrency}
            </span>
          </div>
        </div>

        <Button
          type="submit"
          disabled={disabled || isLoading || config.symbols.length === 0}
          className="w-full"
        >
          {isLoading ? (
            <span className="flex items-center justify-center gap-2">
              <span className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full" />
              Starting...
            </span>
          ) : (
            <span className="flex items-center justify-center gap-2">
              <Play className="h-4 w-4" />
              Start Backtest
            </span>
          )}
        </Button>
      </form>
    </Card>
  );
}
