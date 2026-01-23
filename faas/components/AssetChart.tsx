'use client';

import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { format } from 'date-fns';
import type { AssetTimeline } from '@/lib/types';

interface AssetChartProps {
  data: AssetTimeline | null;
}

export default function AssetChart({ data }: AssetChartProps) {
  if (!data || !data.timeline || data.timeline.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
        <h2 className="text-xl font-bold mb-4 text-gray-800 dark:text-white">资产走势</h2>
        <div className="flex items-center justify-center h-64 text-gray-500">
          暂无数据
        </div>
      </div>
    );
  }

  const chartData = data.timeline.map(snapshot => ({
    time: format(new Date(snapshot.timestamp), 'MM-dd HH:mm'),
    权益资产: Number((snapshot.equity || 0).toFixed(2)),
    账户余额: Number((snapshot.balance || 0).toFixed(2)),
  }));

  // 计算统计数据
  const equities = data.timeline.map(s => s.equity || 0);
  const currentEquity = equities[equities.length - 1] || 0;
  const startEquity = equities[0] || 0;
  const maxEquity = Math.max(...equities);
  const minEquity = Math.min(...equities);
  const totalReturn = currentEquity - startEquity;
  const totalReturnPercent = startEquity > 0 ? (totalReturn / startEquity) * 100 : 0;

  const currentRealized = data.timeline[data.timeline.length - 1]?.realized_pnl || 0;
  const currentUnrealized = data.timeline[data.timeline.length - 1]?.unrealized_pnl || 0;
  const currentMargin = data.timeline[data.timeline.length - 1]?.reserved_margin || 0;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
      <div className="mb-6">
        <h2 className="text-xl font-bold mb-4 text-gray-800 dark:text-white">资产走势</h2>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <div className="bg-gradient-to-br from-purple-50 to-purple-100 dark:from-purple-900/20 dark:to-purple-800/20 rounded-lg p-3">
            <p className="text-xs text-purple-700 dark:text-purple-400">当前权益</p>
            <p className="text-lg font-bold text-purple-900 dark:text-purple-100">
              ${currentEquity.toFixed(2)}
            </p>
          </div>
          <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3">
            <p className="text-xs text-gray-500 dark:text-gray-400">总收益</p>
            <p className={`text-lg font-bold ${totalReturn >= 0 ? 'text-green-600' : 'text-red-600'}`}>
              ${totalReturn.toFixed(2)}
            </p>
          </div>
          <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3">
            <p className="text-xs text-gray-500 dark:text-gray-400">收益率</p>
            <p className={`text-lg font-bold ${totalReturnPercent >= 0 ? 'text-green-600' : 'text-red-600'}`}>
              {totalReturnPercent >= 0 ? '+' : ''}{totalReturnPercent.toFixed(2)}%
            </p>
          </div>
          <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-3">
            <p className="text-xs text-green-700 dark:text-green-400">已实现盈亏</p>
            <p className={`text-lg font-bold ${currentRealized >= 0 ? 'text-green-600' : 'text-red-600'}`}>
              ${currentRealized.toFixed(2)}
            </p>
          </div>
          <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3">
            <p className="text-xs text-blue-700 dark:text-blue-400">占用保证金</p>
            <p className="text-lg font-bold text-blue-900 dark:text-blue-100">
              ${currentMargin.toFixed(2)}
            </p>
          </div>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={350}>
        <LineChart data={chartData} margin={{ top: 10, right: 30, left: 10, bottom: 20 }}>
          <defs>
            <linearGradient id="colorEquity" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.3}/>
              <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0}/>
            </linearGradient>
            <linearGradient id="colorBalance" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/>
              <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
            </linearGradient>
          </defs>
          <XAxis 
            dataKey="time" 
            tick={{ fontSize: 11, fill: '#6b7280' }}
            axisLine={{ stroke: '#e5e7eb' }}
            tickLine={false}
            angle={-30}
            textAnchor="end"
            height={70}
          />
          <YAxis 
            tick={{ fontSize: 11, fill: '#6b7280' }}
            axisLine={{ stroke: '#e5e7eb' }}
            tickLine={false}
            domain={['dataMin - 50', 'dataMax + 50']}
          />
          <Tooltip 
            contentStyle={{ 
              backgroundColor: 'rgba(255, 255, 255, 0.98)',
              border: 'none',
              borderRadius: '12px',
              boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)'
            }}
            cursor={{ stroke: '#e5e7eb', strokeWidth: 1 }}
          />
          <Legend 
            wrapperStyle={{ paddingTop: '20px' }}
            iconType="line"
          />
          <Line 
            type="monotone" 
            dataKey="权益资产" 
            stroke="#8b5cf6" 
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 5, strokeWidth: 2, stroke: '#fff' }}
            fill="url(#colorEquity)"
          />
          <Line 
            type="monotone" 
            dataKey="账户余额" 
            stroke="#3b82f6" 
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 5, strokeWidth: 2, stroke: '#fff' }}
            fill="url(#colorBalance)"
          />
        </LineChart>
      </ResponsiveContainer>

      <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
        <div className="bg-gray-50 dark:bg-gray-700 rounded p-2">
          <p className="text-xs text-gray-500 dark:text-gray-400">最高权益</p>
          <p className="font-semibold text-gray-800 dark:text-white">${maxEquity.toFixed(2)}</p>
        </div>
        <div className="bg-gray-50 dark:bg-gray-700 rounded p-2">
          <p className="text-xs text-gray-500 dark:text-gray-400">最低权益</p>
          <p className="font-semibold text-gray-800 dark:text-white">${minEquity.toFixed(2)}</p>
        </div>
        <div className="bg-gray-50 dark:bg-gray-700 rounded p-2">
          <p className="text-xs text-gray-500 dark:text-gray-400">数据点数</p>
          <p className="font-semibold text-gray-800 dark:text-white">{data.timeline.length}</p>
        </div>
        <div className="bg-gray-50 dark:bg-gray-700 rounded p-2">
          <p className="text-xs text-gray-500 dark:text-gray-400">时间跨度</p>
          <p className="font-semibold text-gray-800 dark:text-white">
            {data.timeline.length > 1 ? `${Math.floor((new Date(data.timeline[data.timeline.length - 1].timestamp).getTime() - new Date(data.timeline[0].timestamp).getTime()) / (1000 * 60 * 60))}小时` : '-'}
          </p>
        </div>
      </div>
    </div>
  );
}
