import { useState, useEffect } from 'react';
import { Settings, Power, PowerOff, Save, RefreshCw } from 'lucide-react';
import type { ReverseConfig } from '../../../types/reverse';
import { getReverseConfig, updateReverseConfig, startReverseEngine, stopReverseEngine } from '../../../services/api/reverse';

interface ReverseConfigPanelProps {
  onConfigChange?: () => void;
}

export function ReverseConfigPanel({ onConfigChange }: ReverseConfigPanelProps) {
  const [config, setConfig] = useState<ReverseConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [formData, setFormData] = useState({
    fixed_margin_usdt: 50,
    fixed_leverage: 10,
    expiration_days: 10,
    max_positions: 10,
  });

  const fetchConfig = async () => {
    try {
      setLoading(true);
      const data = await getReverseConfig();
      setConfig(data);
      setFormData({
        fixed_margin_usdt: data.fixed_margin_usdt,
        fixed_leverage: data.fixed_leverage,
        expiration_days: data.expiration_days,
        max_positions: data.max_positions,
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
      await updateReverseConfig(formData);
      await fetchConfig();
      onConfigChange?.();
    } catch (err) {
      setError('Failed to save config');
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  const handleToggle = async () => {
    if (!config) return;
    
    try {
      setToggling(true);
      if (config.enabled) {
        await stopReverseEngine();
      } else {
        await startReverseEngine();
      }
      await updateReverseConfig({ enabled: !config.enabled });
      await fetchConfig();
      onConfigChange?.();
    } catch (err) {
      setError('Failed to toggle engine');
      console.error(err);
    } finally {
      setToggling(false);
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
          <h3 className="text-lg font-semibold text-white">Reverse Trading Config</h3>
        </div>
        <button
          onClick={handleToggle}
          disabled={toggling}
          className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-all ${
            config?.enabled
              ? 'bg-rose-500/20 text-rose-400 hover:bg-rose-500/30'
              : 'bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30'
          } ${toggling ? 'opacity-50 cursor-not-allowed' : ''}`}
        >
          {toggling ? (
            <RefreshCw className="h-4 w-4 animate-spin" />
          ) : config?.enabled ? (
            <PowerOff className="h-4 w-4" />
          ) : (
            <Power className="h-4 w-4" />
          )}
          {config?.enabled ? 'Disable' : 'Enable'}
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-lg bg-rose-500/10 border border-rose-500/30 p-3 text-sm text-rose-400">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-neutral-400 mb-2">
            Fixed Margin (USDT)
          </label>
          <input
            type="number"
            min={10}
            max={10000}
            step={10}
            value={formData.fixed_margin_usdt}
            onChange={(e) => setFormData({ ...formData, fixed_margin_usdt: Number(e.target.value) })}
            className="w-full rounded-lg border border-neutral-700 bg-neutral-800 px-4 py-2.5 text-white placeholder-neutral-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
          <p className="mt-1 text-xs text-neutral-500">Amount of margin per trade (10-10000)</p>
        </div>

        <div>
          <label className="block text-sm font-medium text-neutral-400 mb-2">
            Fixed Leverage
          </label>
          <input
            type="number"
            min={1}
            max={125}
            value={formData.fixed_leverage}
            onChange={(e) => setFormData({ ...formData, fixed_leverage: Number(e.target.value) })}
            className="w-full rounded-lg border border-neutral-700 bg-neutral-800 px-4 py-2.5 text-white placeholder-neutral-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
          <p className="mt-1 text-xs text-neutral-500">Leverage multiplier (1-125x)</p>
        </div>

        <div>
          <label className="block text-sm font-medium text-neutral-400 mb-2">
            Order Expiration (Days)
          </label>
          <input
            type="number"
            min={1}
            max={30}
            value={formData.expiration_days}
            onChange={(e) => setFormData({ ...formData, expiration_days: Number(e.target.value) })}
            className="w-full rounded-lg border border-neutral-700 bg-neutral-800 px-4 py-2.5 text-white placeholder-neutral-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
          <p className="mt-1 text-xs text-neutral-500">Auto-cancel pending orders after (1-30 days)</p>
        </div>

        <div>
          <label className="block text-sm font-medium text-neutral-400 mb-2">
            Max Positions
          </label>
          <input
            type="number"
            min={1}
            max={100}
            value={formData.max_positions}
            onChange={(e) => setFormData({ ...formData, max_positions: Number(e.target.value) })}
            className="w-full rounded-lg border border-neutral-700 bg-neutral-800 px-4 py-2.5 text-white placeholder-neutral-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
          <p className="mt-1 text-xs text-neutral-500">Maximum concurrent positions (1-100)</p>
        </div>
      </div>

      <div className="mt-6 flex justify-end">
        <button
          onClick={handleSave}
          disabled={saving}
          className={`flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-all hover:bg-blue-700 ${
            saving ? 'opacity-50 cursor-not-allowed' : ''
          }`}
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
