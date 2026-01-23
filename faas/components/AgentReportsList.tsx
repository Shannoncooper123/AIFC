'use client';

import { Brain, Clock, Target, AlertCircle } from 'lucide-react';
import type { AgentReports } from '@/lib/types';

interface AgentReportsListProps {
  data: AgentReports | null;
}

export default function AgentReportsList({ data }: AgentReportsListProps) {
  if (!data || !data.reports || data.reports.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
        <h2 className="text-xl font-bold mb-4 text-gray-800 dark:text-white">AI 分析报告</h2>
        <div className="flex items-center justify-center h-32 text-gray-500">
          暂无报告数据
        </div>
      </div>
    );
  }

  const recentReports = data.reports.slice(-5).reverse(); // 显示最近5条

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
      <div className="flex items-center space-x-2 mb-4">
        <Brain className="w-6 h-6 text-purple-600" />
        <h2 className="text-xl font-bold text-gray-800 dark:text-white">AI 分析报告</h2>
        <span className="bg-purple-100 text-purple-800 text-xs font-semibold px-2 py-1 rounded-full">
          {data.reports.length} 条记录
        </span>
      </div>

      <div className="space-y-4">
        {recentReports.map((report, index) => {
          const reportTime = new Date(report.ts);
          const nextWakeupTime = new Date(report.next_wakeup_at);
          const anyReport = report as any;
          const symbolFocusMap: Record<string, string> | undefined = anyReport.symbol_focus_map;
          const positionNextFocus: string | undefined = anyReport.position_next_focus;
          
          return (
            <div 
              key={index} 
              className="border dark:border-gray-700 rounded-lg p-4 hover:shadow-md transition-shadow"
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex-1">
                  <div className="flex items-center space-x-2 mb-2">
                    <Clock className="w-4 h-4 text-blue-600" />
                    <span className="text-sm font-semibold text-gray-800 dark:text-white">
                      {reportTime.toLocaleString('zh-CN')}
                    </span>
                    <span className="px-2 py-0.5 rounded text-xs font-semibold bg-blue-100 text-blue-800">
                      {report.next_wakeup_minutes} 分钟后唤醒
                    </span>
                  </div>
                </div>
              </div>

              {symbolFocusMap && Object.keys(symbolFocusMap).length > 0 ? (
                <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3 mb-3">
                  <div className="flex items-start space-x-2">
                    <Target className="w-4 h-4 text-green-600 mt-0.5" />
                    <div className="flex-1">
                      <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">逐币种关注重点 ({Object.keys(symbolFocusMap).length})</p>
                      <div className="flex flex-wrap gap-2 mb-2">
                        {Object.keys(symbolFocusMap).map((symbol) => (
                          <span
                            key={symbol}
                            className="px-2 py-1 rounded text-xs font-semibold bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300"
                          >
                            {symbol}
                          </span>
                        ))}
                      </div>
                      <div className="space-y-1">
                        {Object.entries(symbolFocusMap).map(([symbol, focus]) => (
                          <p key={symbol} className="text-xs text-gray-700 dark:text-gray-300">
                            <span className="font-semibold text-gray-800 dark:text-white mr-1">{symbol}:</span>
                            <span className="whitespace-pre-wrap">{focus}</span>
                          </p>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                report.symbols && report.symbols.length > 0 && (
                  <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3 mb-3">
                    <div className="flex items-start space-x-2">
                      <Target className="w-4 h-4 text-green-600 mt-0.5" />
                      <div className="flex-1">
                        <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">关注币种 ({report.symbols.length})</p>
                        <div className="flex flex-wrap gap-2">
                          {report.symbols.map((symbol, idx) => (
                            <span
                              key={idx}
                              className="px-2 py-1 rounded text-xs font-semibold bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300"
                            >
                              {symbol}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                )
              )}

              {report.summary && (
                <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3 mb-3">
                  <div className="flex items-start space-x-2">
                    <AlertCircle className="w-4 h-4 text-blue-600 mt-0.5 flex-shrink-0" />
                    <div className="flex-1">
                      <p className="text-xs text-blue-700 dark:text-blue-400 mb-1 font-semibold">市场分析</p>
                      <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed">
                        {report.summary}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {(positionNextFocus || report.next_focus) && (
                <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-3">
                  <div className="flex items-start space-x-2">
                    <Target className="w-4 h-4 text-purple-600 mt-0.5 flex-shrink-0" />
                    <div className="flex-1">
                      <p className="text-xs text-purple-700 dark:text-purple-400 mb-1 font-semibold">持仓关注重点</p>
                      <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
                        {positionNextFocus || report.next_focus}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              <div className="mt-3 pt-3 border-t dark:border-gray-700 flex items-center justify-between text-xs">
                <span className="text-gray-500 dark:text-gray-400">
                  下次唤醒: {nextWakeupTime.toLocaleString('zh-CN')}
                </span>
                <span className="text-gray-500 dark:text-gray-400">
                  {Math.round((Date.now() - reportTime.getTime()) / (1000 * 60))} 分钟前
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {data.reports.length > 5 && (
        <div className="mt-4 text-center text-sm text-gray-500">
          仅显示最近 5 条报告，共 {data.reports.length} 条
        </div>
      )}
    </div>
  );
}
