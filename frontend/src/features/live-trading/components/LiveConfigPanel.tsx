import { useState, useEffect } from 'react';
import { Settings, Power, PowerOff, Save, RefreshCw } from 'lucide-react';
import type { LiveTradingConfig } from '../../../types/live';
import { getLiveConfig, updateLiveConfig, startLiveEngine, stopLiveEngine, getLiveSummary } from '../../../services/api/live';

interface LiveConfigPanelProps {
  onConfigChange?: () => void;
}

const parseNumber = (value: string, defaultValue: number): number => {
  const parsed = parseFloat(value);
  return isNaN(parsed) ? defaultValue : parsed;
};

const parseInteger = (value: string, defaultValue: number): number => {
  const parsed = parseInt(value, 10);
  return isNaN(parsed) ? defaultValue : parsed;
};

export function LiveConfigPanel({ onConfigChange }: LiveConfigPanelProps) {
  const [config, setConfig] = useState<LiveTradingConfig | null>(null);
  const [engineRunning, setEngineRunning] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [formData, setFormData] = useState({
    fixed_margin_usdt: '50',
    fixed_leverage: '10',
    expiration_days: '10',
    max_positions: '10',
  });

  const fetchConfig = async () => {
    try {
      setLoading(true);
      const [configData, summaryData] = await Promise.all([
        getLiveConfig(),
        getLiveSummary()
      ]);
      setConfig(configData);
      setEngineRunning(summaryData.engine_running);
      setFormData({
        fixed_margin_usdt: String(configData.fixed_margin_usdt),
        fixed_leverage: String(configData.fixed_leverage),
        expiration_days: String(configData.expiration_days),
        max_positions: String(configData.max_positions),
      });
      setError(null);
    } catch (err) {
      setError('Failed to load config');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConfig();
  }, []);

  const handleSave = async () => {
    try {
      setSaving(true);
      await updateLiveConfig({
        fixed_margin_usdt: parseNumber(formData.fixed_margin_usdt, 50),
        fixed_leverage: parseInteger(formData.fixed_leverage, 10),
        expiration_days: parseInteger(formData.expiration_days, 10),
        max_positions: parseInteger(formData.max_positions, 10),
      });
      await fetchConfig();
      onConfigChange?.();
    } catch (err) {
      setError('Failed to save config');
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  const handleToggleEngine = async () => {
    try {
      setToggling(true);
      if (engineRunning) {
        await stopLiveEngine();
      } else {
        await startLiveEngine();
      }
      await fetchConfig();
      onConfigChange?.();
    } catch (err) {
      setError('Failed to toggle engine');
      console.error(err);
    } finally {
      setToggling(false);
    }
  };

  const handleToggleReverse = async () => {
    if (!config) return;
    try {
      await updateLiveConfig({ reverse_enabled: !config.reverse_enabled });
      await fetchConfig();
      onConfigChange?.();
    } catch (err) {
      setError('Failed to toggle reverse mode');
      console.error(err);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <RefreshCw className="h-6 w-6 animate-spin text-neutral-400" />
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-neutral-800 bg-[#1a1a1a] p-6">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Settings className="h-5 w-5 text-neutral-400" />
          <h3 className="text-lg font-semibold text-white">Live Trading Config</h3>
        </div>
        <button
          onClick={handleToggleEngine}
          disabled={toggling}
          className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-all ${
            engineRunning
              ? 'bg-rose-500/20 text-rose-400 hover:bg-rose-500/30'
              : 'bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30'
          } ${toggling ? 'opacity-50 cursor-not-allowed' : ''}`}
        >
          {toggling ? (
            <RefreshCw className="h-4 w-4 animate-spin" />
          ) : engineRunning ? (
            <PowerOff className="h-4 w-4" />
          ) : (
            <Power className="h-4 w-4" />
          )}
          {engineRunning ? 'Stop Engine' : 'Start Engine'}
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-lg bg-rose-500/10 border border-rose-500/30 p-3 text-sm text-rose-400">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
        <div>
          <label className="block text-sm text-neutral-400 mb-2">Reverse Mode</label>
          <button
            onClick={handleToggleReverse}
            className={`w-full rounded-lg px-3 py-2 text-sm font-medium transition-all ${
              config?.reverse_enabled
                ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                : 'bg-neutral-800 text-neutral-400 border border-neutral-700'
            }`}
          >
            {config?.reverse_enabled ? 'ON' : 'OFF'}
          </button>
        </div>

        <div>
          <label className="block text-sm text-neutral-400 mb-2">Margin (USDT)</label>
          <input
            type="number"
            value={formData.fixed_margin_usdt}
            onChange={(e) => setFormData({ ...formData, fixed_margin_usdt: e.target.value })}
            className="w-full rounded-lg border border-neutral-700 bg-neutral-800 px-3 py-2 text-white focus:border-blue-500 focus:outline-none"
            min="1"
            max="100000"
          />
        </div>

        <div>
          <label className="block text-sm text-neutral-400 mb-2">Leverage</label>
          <input
            type="number"
            value={formData.fixed_leverage}
            onChange={(e) => setFormData({ ...formData, fixed_leverage: e.target.value })}
            className="w-full rounded-lg border border-neutral-700 bg-neutral-800 px-3 py-2 text-white focus:border-blue-500 focus:outline-none"
            min="1"
            max="125"
          />
        </div>

        <div>
          <label className="block text-sm text-neutral-400 mb-2">Expiration (Days)</label>
          <input
            type="number"
            value={formData.expiration_days}
            onChange={(e) => setFormData({ ...formData, expiration_days: e.target.value })}
            className="w-full rounded-lg border border-neutral-700 bg-neutral-800 px-3 py-2 text-white focus:border-blue-500 focus:outline-none"
            min="1"
            max="30"
          />
        </div>

        <div>
          <label className="block text-sm text-neutral-400 mb-2">Max Positions</label>
          <input
            type="number"
            value={formData.max_positions}
            onChange={(e) => setFormData({ ...formData, max_positions: e.target.value })}
            className="w-full rounded-lg border border-neutral-700 bg-neutral-800 px-3 py-2 text-white focus:border-blue-500 focus:outline-none"
            min="1"
            max="100"
          />
        </div>
      </div>

      <div className="flex justify-end">
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors disabled:opacity-50"
        >
          {saving ? (
            <RefreshCw className="h-4 w-4 animate-spin" />
          ) : (
            <Save className="h-4 w-4" />
          )}
          Save Config
        </button>
      </div>
    </div>
  );
}
