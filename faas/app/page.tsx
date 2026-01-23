'use client';

import { useEffect, useState } from 'react';
import { Activity, RefreshCw } from 'lucide-react';
import AssetChart from '@/components/AssetChart';
import TradeStateCard from '@/components/TradeStateCard';
import PositionHistoryTable from '@/components/PositionHistoryTable';
import AgentReportsList from '@/components/AgentReportsList';
import PendingOrdersCard from '@/components/PendingOrdersCard';
import type { DashboardData } from '@/lib/types';

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState<string>('');
  const [isRefreshing, setIsRefreshing] = useState(false);

  const fetchData = async () => {
    try {
      setIsRefreshing(true);
      const response = await fetch('/api/data');
      if (response.ok) {
        const result = await response.json();
        setData(result);
        setLastUpdate(new Date().toLocaleString('zh-CN'));
      }
    } catch (error) {
      console.error('Error fetching data:', error);
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
  };

  // 新增：资产快照打点逻辑（每10分钟一次，且页面加载时立即触发一次）
  const recordAssetSnapshot = async () => {
    try {
      const resp = await fetch('/api/asset/snapshot', { method: 'POST' });
      // 可选：调试输出
      if (!resp.ok) {
        console.warn('Asset snapshot request failed');
      }
    } catch (e) {
      console.warn('Asset snapshot request error:', e);
    }
  };

  useEffect(() => {
    fetchData();
    // 页面加载时立即记录一次资产快照（服务器端有最短间隔保护）
    recordAssetSnapshot();
    
    // 每10秒自动刷新一次数据
    const dataInterval = setInterval(fetchData, 10000);
    // 每10分钟记录一次资产快照
    const snapshotInterval = setInterval(recordAssetSnapshot, 10 * 60 * 1000);
    
    return () => {
      clearInterval(dataInterval);
      clearInterval(snapshotInterval);
    };
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 dark:from-gray-900 dark:to-gray-800 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-purple-600 mx-auto mb-4"></div>
          <p className="text-gray-600 dark:text-gray-400">加载数据中...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 dark:from-gray-900 dark:to-gray-800">
      {/* Header */}
      <header className="bg-white dark:bg-gray-800 shadow-md border-b dark:border-gray-700">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="bg-gradient-to-br from-purple-500 to-blue-600 p-2 rounded-lg">
                <Activity className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-2xl font-bold text-gray-800 dark:text-white">
                  交易监控仪表板
                </h1>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  实时监控 · 数据分析 · 智能决策
                </p>
              </div>
            </div>
            
            <div className="flex items-center space-x-4">
              <div className="text-right">
                <p className="text-xs text-gray-500 dark:text-gray-400">最后更新</p>
                <p className="text-sm font-semibold text-gray-800 dark:text-white">
                  {lastUpdate}
                </p>
              </div>
              <button
                onClick={fetchData}
                disabled={isRefreshing}
                className="bg-purple-600 hover:bg-purple-700 disabled:bg-gray-400 text-white px-4 py-2 rounded-lg flex items-center space-x-2 transition-colors"
              >
                <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
                <span>刷新</span>
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="space-y-6">
          {/* 交易状态卡片 */}
          <TradeStateCard data={data?.trade_state || null} />

          {/* 资产走势图 */}
          <AssetChart data={data?.asset_timeline || null} />

          {/* 待处理订单 */}
          <PendingOrdersCard data={data?.pending_orders || null} />

          {/* AI 分析报告 */}
          <AgentReportsList data={data?.agent_reports || null} />

          {/* 持仓历史 */}
          <PositionHistoryTable data={data?.position_history || null} />
        </div>
      </main>

      {/* Footer */}
      <footer className="bg-white dark:bg-gray-800 border-t dark:border-gray-700 mt-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="text-center text-sm text-gray-500 dark:text-gray-400">
            <p>交易监控系统 · 实时数据更新 · Powered by Next.js</p>
            <p className="mt-2">
              {data?.trade_state && (
                <span className="inline-flex items-center px-3 py-1 rounded-full bg-green-100 text-green-800 text-xs font-semibold">
                  <span className="w-2 h-2 bg-green-600 rounded-full mr-2 animate-pulse"></span>
                  系统运行中
                </span>
              )}
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
