'use client';

import { TrendingUp, TrendingDown } from 'lucide-react';
import type { PositionHistory } from '@/lib/types';

interface PositionHistoryTableProps {
  data: PositionHistory | null;
}

export default function PositionHistoryTable({ data }: PositionHistoryTableProps) {
  if (!data || !data.positions || data.positions.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
        <h2 className="text-xl font-bold mb-4 text-gray-800 dark:text-white">持仓历史</h2>
        <div className="flex items-center justify-center h-32 text-gray-500">
          暂无历史数据
        </div>
      </div>
    );
  }

  // 只显示已平仓的持仓（有 close_price 的）
  const closedPositions = data.positions.filter(p => p.close_price !== null && p.close_price !== undefined);
  
  // 计算统计数据
  const totalTrades = closedPositions.length;
  const winningTrades = closedPositions.filter(p => (p.realized_pnl || 0) > 0).length;
  const losingTrades = closedPositions.filter(p => (p.realized_pnl || 0) < 0).length;
  const winRate = totalTrades > 0 ? (winningTrades / totalTrades) * 100 : 0;
  const totalPnl = closedPositions.reduce((sum, p) => sum + (p.realized_pnl || 0), 0);
  const totalFees = closedPositions.reduce((sum, p) => sum + (p.fees_open || 0) + (p.fees_close || 0), 0);
  const avgPnl = totalTrades > 0 ? totalPnl / totalTrades : 0;

  // 最近20条记录
  const recentPositions = closedPositions.slice(-20).reverse();

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
      <h2 className="text-xl font-bold mb-4 text-gray-800 dark:text-white">持仓历史</h2>

      <div className="grid grid-cols-2 md:grid-cols-6 gap-4 mb-6">
        <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3">
          <p className="text-xs text-gray-500 dark:text-gray-400">总交易次数</p>
          <p className="text-lg font-bold text-gray-800 dark:text-white">{totalTrades}</p>
        </div>
        <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-3">
          <p className="text-xs text-green-700 dark:text-green-400">盈利次数</p>
          <p className="text-lg font-bold text-green-600">{winningTrades}</p>
        </div>
        <div className="bg-red-50 dark:bg-red-900/20 rounded-lg p-3">
          <p className="text-xs text-red-700 dark:text-red-400">亏损次数</p>
          <p className="text-lg font-bold text-red-600">{losingTrades}</p>
        </div>
        <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3">
          <p className="text-xs text-blue-700 dark:text-blue-400">胜率</p>
          <p className="text-lg font-bold text-blue-900 dark:text-blue-100">
            {winRate.toFixed(1)}%
          </p>
        </div>
        <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-3">
          <p className="text-xs text-purple-700 dark:text-purple-400">总盈亏</p>
          <p className={`text-lg font-bold ${totalPnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
            ${totalPnl.toFixed(2)}
          </p>
        </div>
        <div className="bg-orange-50 dark:bg-orange-900/20 rounded-lg p-3">
          <p className="text-xs text-orange-700 dark:text-orange-400">总手续费</p>
          <p className="text-lg font-bold text-orange-900 dark:text-orange-100">
            ${totalFees.toFixed(2)}
          </p>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b dark:border-gray-700">
              <th className="text-left py-3 px-2 text-gray-600 dark:text-gray-400 font-semibold">交易对</th>
              <th className="text-left py-3 px-2 text-gray-600 dark:text-gray-400 font-semibold">方向</th>
              <th className="text-right py-3 px-2 text-gray-600 dark:text-gray-400 font-semibold">入场价</th>
              <th className="text-right py-3 px-2 text-gray-600 dark:text-gray-400 font-semibold">出场价</th>
              <th className="text-right py-3 px-2 text-gray-600 dark:text-gray-400 font-semibold">盈亏</th>
              <th className="text-left py-3 px-2 text-gray-600 dark:text-gray-400 font-semibold">平仓原因</th>
              <th className="text-right py-3 px-2 text-gray-600 dark:text-gray-400 font-semibold">开仓时间</th>
              <th className="text-right py-3 px-2 text-gray-600 dark:text-gray-400 font-semibold">平仓时间</th>
            </tr>
          </thead>
          <tbody>
            {recentPositions.map((position) => {
              const pnlPercent = position.entry_price > 0 
                ? ((position.close_price! - position.entry_price) / position.entry_price) * 100 * (position.side === 'long' ? 1 : -1)
                : 0;

              return (
                <tr key={position.id} className="border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700">
                  <td className="py-3 px-2 text-gray-800 dark:text-white font-medium">
                    {position.symbol}
                  </td>
                  <td className="py-3 px-2">
                    <div className="flex items-center space-x-1">
                      {position.side === 'long' ? (
                        <>
                          <TrendingUp className="w-4 h-4 text-green-600" />
                          <span className="text-green-600 font-semibold">{position.leverage}x 多</span>
                        </>
                      ) : (
                        <>
                          <TrendingDown className="w-4 h-4 text-red-600" />
                          <span className="text-red-600 font-semibold">{position.leverage}x 空</span>
                        </>
                      )}
                    </div>
                  </td>
                  <td className="py-3 px-2 text-right text-gray-800 dark:text-white">
                    ${position.entry_price.toFixed(4)}
                  </td>
                  <td className="py-3 px-2 text-right text-gray-800 dark:text-white">
                    ${position.close_price!.toFixed(4)}
                  </td>
                  <td className="py-3 px-2 text-right">
                    <div className="flex flex-col items-end">
                      <span className={`font-semibold ${position.realized_pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        ${position.realized_pnl.toFixed(2)}
                      </span>
                      <span className={`text-xs ${position.realized_pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        ({pnlPercent >= 0 ? '+' : ''}{pnlPercent.toFixed(2)}%)
                      </span>
                    </div>
                  </td>
                  <td className="py-3 px-2">
                    <span className="px-2 py-1 rounded text-xs font-semibold bg-gray-100 dark:bg-gray-600 text-gray-800 dark:text-gray-200">
                      {position.close_reason || '手动'}
                    </span>
                  </td>
                  <td className="py-3 px-2 text-right text-xs text-gray-600 dark:text-gray-400">
                    {position.open_time ? new Date(position.open_time).toLocaleString('zh-CN', {
                      month: '2-digit',
                      day: '2-digit',
                      hour: '2-digit',
                      minute: '2-digit'
                    }) : '-'}
                  </td>
                  <td className="py-3 px-2 text-right text-xs text-gray-600 dark:text-gray-400">
                    {position.close_time ? new Date(position.close_time).toLocaleString('zh-CN', {
                      month: '2-digit',
                      day: '2-digit',
                      hour: '2-digit',
                      minute: '2-digit'
                    }) : '-'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {closedPositions.length > 20 && (
        <div className="mt-4 text-center text-sm text-gray-500">
          仅显示最近 20 条记录，共 {closedPositions.length} 条
        </div>
      )}
    </div>
  );
}
