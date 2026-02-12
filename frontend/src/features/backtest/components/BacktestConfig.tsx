import { useState, useCallback } from 'react';
import { Play, Calendar, DollarSign, Clock, Cpu, TrendingUp, RefreshCw, Brain, Settings } from 'lucide-react';
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
  fixedMarginUsdt: number;
  fixedLeverage: number;
  reverseMode: boolean;
  enableReinforcement: boolean;
}

const AVAILABLE_SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'DOGEUSDT', 'LTCUSDT', 'SOLUSDT', 'XRPUSDT', '1000PEPEUSDT'];

export function BacktestConfig({ onStart, isLoading, disabled }: BacktestConfigProps) {
  const [config, setConfig] = useState<BacktestConfigData>({
    symbols: ['BTCUSDT', 'ETHUSDT'],
    startTime: getDefaultStartTime(),
    endTime: getDefaultEndTime(),
    interval: '15m',
    initialBalance: 10000,
    concurrency: 5,
    fixedMarginUsdt: 50,
    fixedLeverage: 10,
    reverseMode: false,
    enableReinforcement: false,
  });

  const [showAdvanced, setShowAdvanced] = useState(false);

  function toUTCDatetimeLocal(date: Date): string {
    const year = date.getUTCFullYear();
    const month = String(date.getUTCMonth() + 1).padStart(2, '0');
    const day = String(date.getUTCDate()).padStart(2, '0');
    const hours = String(date.getUTCHours()).padStart(2, '0');
    const minutes = String(date.getUTCMinutes()).padStart(2, '0');
    return `${year}-${month}-${day}T${hours}:${minutes}`;
  }

  function getDefaultStartTime(): string {
    const date = new Date();
    date.setUTCDate(date.getUTCDate() - 7);
    return toUTCDatetimeLocal(date);
  }

  function getDefaultEndTime(): string {
    const date = new Date();
    date.setUTCDate(date.getUTCDate() - 1);
    return toUTCDatetimeLocal(date);
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

  const handleNumberChange = useCallback((field: keyof BacktestConfigData, value: string, defaultValue: number, min?: number, max?: number) => {
    let numValue = value === '' ? defaultValue : parseFloat(value);
    if (isNaN(numValue)) numValue = defaultValue;
    if (min !== undefined && numValue < min) numValue = min;
    if (max !== undefined && numValue > max) numValue = max;
    setConfig((prev) => ({ ...prev, [field]: numValue }));
  }, []);

  const handleIntegerChange = useCallback((field: keyof BacktestConfigData, value: string, defaultValue: number, min?: number, max?: number) => {
    let numValue = value === '' ? defaultValue : parseInt(value, 10);
    if (isNaN(numValue)) numValue = defaultValue;
    if (min !== undefined && numValue < min) numValue = min;
    if (max !== undefined && numValue > max) numValue = max;
    setConfig((prev) => ({ ...prev, [field]: numValue }));
  }, []);

  return (
    <Card>
      <form onSubmit={handleSubmit} className="space-y-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-white font-medium">
            <Clock className="h-5 w-5 text-blue-400" />
            Backtest Configuration
          </div>
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="flex items-center gap-1.5 text-xs text-neutral-400 hover:text-white transition-colors"
          >
            <Settings className="h-3.5 w-3.5" />
            {showAdvanced ? 'Hide Advanced' : 'Show Advanced'}
          </button>
        </div>

        {/* 币种选择 */}
        <div>
          <label className="block text-sm text-neutral-400 mb-2">Symbols</label>
          <div className="flex flex-wrap gap-2">
            {AVAILABLE_SYMBOLS.map((symbol) => (
              <button
                key={symbol}
                type="button"
                onClick={() => handleSymbolToggle(symbol)}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
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

        {/* 时间范围 */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-sm text-neutral-400 mb-1.5">
              <Calendar className="inline h-3.5 w-3.5 mr-1" />
              Start <span className="text-xs text-blue-400/70">(UTC)</span>
            </label>
            <input
              type="datetime-local"
              value={config.startTime}
              onChange={(e) => setConfig((prev) => ({ ...prev, startTime: e.target.value }))}
              className="w-full px-3 py-2 rounded-lg bg-neutral-800 border border-neutral-700 text-white text-sm focus:border-blue-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-sm text-neutral-400 mb-1.5">
              <Calendar className="inline h-3.5 w-3.5 mr-1" />
              End <span className="text-xs text-blue-400/70">(UTC)</span>
            </label>
            <input
              type="datetime-local"
              value={config.endTime}
              onChange={(e) => setConfig((prev) => ({ ...prev, endTime: e.target.value }))}
              className="w-full px-3 py-2 rounded-lg bg-neutral-800 border border-neutral-700 text-white text-sm focus:border-blue-500 focus:outline-none"
            />
          </div>
        </div>

        {/* 周期和并发 */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-sm text-neutral-400 mb-1.5">Interval</label>
            <select
              value={config.interval}
              onChange={(e) => setConfig((prev) => ({ ...prev, interval: e.target.value }))}
              className="w-full px-3 py-2 rounded-lg bg-neutral-800 border border-neutral-700 text-white text-sm focus:border-blue-500 focus:outline-none"
            >
              <option value="15m">15 minutes</option>
              <option value="1h">1 hour</option>
              <option value="4h">4 hours</option>
            </select>
          </div>
          <div>
            <label className="block text-sm text-neutral-400 mb-1.5">
              <Cpu className="inline h-3.5 w-3.5 mr-1" />
              Concurrency
            </label>
            <div className="flex items-center gap-2">
              <input
                type="range"
                value={config.concurrency}
                onChange={(e) => setConfig((prev) => ({ ...prev, concurrency: parseInt(e.target.value, 10) }))}
                min={1}
                max={50}
                step={1}
                className="flex-1 h-2 rounded-lg appearance-none cursor-pointer bg-neutral-700 accent-blue-500"
              />
              <span className="min-w-[2.5rem] text-center text-white text-sm font-medium bg-neutral-800 border border-neutral-700 px-2 py-1 rounded">
                {config.concurrency}
              </span>
            </div>
          </div>
        </div>

        {/* 资金设置 */}
        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="block text-sm text-neutral-400 mb-1.5">
              <DollarSign className="inline h-3.5 w-3.5 mr-1" />
              Balance
            </label>
            <input
              type="number"
              value={config.initialBalance}
              onChange={(e) => handleNumberChange('initialBalance', e.target.value, 10000, 100, 1000000)}
              onBlur={(e) => handleNumberChange('initialBalance', e.target.value, 10000, 100, 1000000)}
              min={100}
              max={1000000}
              step={100}
              className="w-full px-3 py-2 rounded-lg bg-neutral-800 border border-neutral-700 text-white text-sm focus:border-blue-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-sm text-neutral-400 mb-1.5">
              <DollarSign className="inline h-3.5 w-3.5 mr-1" />
              Margin
            </label>
            <input
              type="number"
              value={config.fixedMarginUsdt}
              onChange={(e) => handleNumberChange('fixedMarginUsdt', e.target.value, 50, 1, 10000)}
              onBlur={(e) => handleNumberChange('fixedMarginUsdt', e.target.value, 50, 1, 10000)}
              min={1}
              max={10000}
              step={1}
              className="w-full px-3 py-2 rounded-lg bg-neutral-800 border border-neutral-700 text-white text-sm focus:border-blue-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-sm text-neutral-400 mb-1.5">
              <TrendingUp className="inline h-3.5 w-3.5 mr-1" />
              Leverage
            </label>
            <input
              type="number"
              value={config.fixedLeverage}
              onChange={(e) => handleIntegerChange('fixedLeverage', e.target.value, 10, 1, 125)}
              onBlur={(e) => handleIntegerChange('fixedLeverage', e.target.value, 10, 1, 125)}
              min={1}
              max={125}
              step={1}
              className="w-full px-3 py-2 rounded-lg bg-neutral-800 border border-neutral-700 text-white text-sm focus:border-blue-500 focus:outline-none"
            />
          </div>
        </div>

        {/* 高级选项 */}
        {showAdvanced && (
          <div className="space-y-3 pt-3 border-t border-neutral-800">
            <div className="text-xs text-neutral-500 uppercase tracking-wider">Advanced Options</div>
            
            {/* 强化学习开关 */}
            <div className="p-3 rounded-lg bg-gradient-to-r from-purple-500/10 to-blue-500/10 border border-purple-500/20">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Brain className="h-4 w-4 text-purple-400" />
                  <div>
                    <div className="text-sm font-medium text-white">Reinforcement Learning</div>
                    <div className="text-xs text-neutral-400">Multi-round optimization for losing trades</div>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setConfig((prev) => ({ ...prev, enableReinforcement: !prev.enableReinforcement }))}
                  className={`relative w-11 h-6 rounded-full transition-colors ${
                    config.enableReinforcement ? 'bg-purple-500' : 'bg-neutral-700'
                  }`}
                >
                  <span
                    className={`absolute top-1 left-1 w-4 h-4 rounded-full bg-white transition-transform ${
                      config.enableReinforcement ? 'translate-x-5' : 'translate-x-0'
                    }`}
                  />
                </button>
              </div>
              {config.enableReinforcement && (
                <div className="mt-2 text-xs text-purple-300/80 pl-6">
                  When a trade results in a loss, the system will analyze the decision process and retry up to 3 times with improved guidance.
                </div>
              )}
            </div>

            {/* 反向模式 */}
            <div className="p-3 rounded-lg bg-neutral-800/50 border border-neutral-700">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <RefreshCw className={`h-4 w-4 ${config.reverseMode ? 'text-orange-400' : 'text-neutral-400'}`} />
                  <div>
                    <div className="text-sm font-medium text-white">Reverse Mode</div>
                    <div className="text-xs text-neutral-400">Invert agent trading signals</div>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setConfig((prev) => ({ ...prev, reverseMode: !prev.reverseMode }))}
                  className={`relative w-11 h-6 rounded-full transition-colors ${
                    config.reverseMode ? 'bg-orange-500' : 'bg-neutral-700'
                  }`}
                >
                  <span
                    className={`absolute top-1 left-1 w-4 h-4 rounded-full bg-white transition-transform ${
                      config.reverseMode ? 'translate-x-5' : 'translate-x-0'
                    }`}
                  />
                </button>
              </div>
              {config.reverseMode && (
                <div className="mt-2 text-xs text-orange-300/80 pl-6">
                  Agent Long → We Short, Agent Short → We Long
                </div>
              )}
            </div>
          </div>
        )}

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
              {config.enableReinforcement && (
                <span className="ml-1 px-1.5 py-0.5 rounded text-xs bg-purple-500/30 text-purple-300">RL</span>
              )}
            </span>
          )}
        </Button>
      </form>
    </Card>
  );
}
