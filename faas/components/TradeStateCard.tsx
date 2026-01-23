'use client';

import { TrendingUp, TrendingDown, DollarSign, Activity, Package, Clock, ChevronDown, ChevronUp, Edit, XCircle } from 'lucide-react';
import { useState } from 'react';
import type { TradeState, OperationHistoryItem } from '@/lib/types';

interface TradeStateCardProps {
  data: TradeState | null;
}

// 操作历史时间线组件
function OperationTimeline({ operations }: { operations: OperationHistoryItem[] }) {
  if (!operations || operations.length === 0) {
    return (
      <div className="text-xs text-gray-400 italic">暂无操作记录</div>
    );
  }

  const getOperationIcon = (operation: string) => {
    switch (operation) {
      case 'open':
        return <Package className="w-3.5 h-3.5 text-blue-500" />;
      case 'add_position':
        return <TrendingUp className="w-3.5 h-3.5 text-green-500" />;
      case 'update_tp_sl':
        return <Edit className="w-3.5 h-3.5 text-yellow-500" />;
      case 'close':
        return <XCircle className="w-3.5 h-3.5 text-red-500" />;
      default:
        return <Clock className="w-3.5 h-3.5 text-gray-500" />;
    }
  };

  const getOperationLabel = (operation: string) => {
    switch (operation) {
      case 'open':
        return '开仓';
      case 'add_position':
        return '加仓';
      case 'update_tp_sl':
        return '调整止盈止损';
      case 'close':
        return '平仓';
      default:
        return operation;
    }
  };

  const formatDateTime = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  return (
    <div className="mt-3 space-y-2">
      <div className="flex items-center gap-2 mb-2">
        <Clock className="w-3.5 h-3.5 text-gray-500" />
        <span className="text-xs font-semibold text-gray-600 dark:text-gray-400">操作历史 ({operations.length})</span>
      </div>
      <div className="space-y-2 max-h-60 overflow-y-auto scrollbar-thin scrollbar-thumb-gray-300 dark:scrollbar-thumb-gray-600">
        {operations.map((op, idx) => (
          <div key={idx} className="relative pl-6 pb-2">
            {/* 时间线 */}
            {idx < operations.length - 1 && (
              <div className="absolute left-[7px] top-5 bottom-0 w-0.5 bg-gray-200 dark:bg-gray-600"></div>
            )}

            {/* 图标 */}
            <div className="absolute left-0 top-0.5 bg-white dark:bg-gray-700 rounded-full p-0.5">
              {getOperationIcon(op.operation)}
            </div>

            {/* 内容 */}
            <div className="bg-gray-50 dark:bg-gray-800 rounded-md p-2 text-xs">
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-gray-700 dark:text-gray-300">
                  {getOperationLabel(op.operation)}
                </span>
                <span className="text-gray-500 dark:text-gray-400 text-[10px]">
                  {formatDateTime(op.timestamp)}
                </span>
              </div>

              {/* 操作详情 */}
              <div className="text-gray-600 dark:text-gray-400 space-y-0.5">
                {op.operation === 'open' && (
                  <>
                    <div>入场: <span className="font-mono">${op.details.entry_price?.toFixed(4)}</span></div>
                    <div className="flex gap-3">
                      {op.details.tp_price && <span className="text-green-600">TP: ${op.details.tp_price.toFixed(4)}</span>}
                      {op.details.sl_price && <span className="text-red-600">SL: ${op.details.sl_price.toFixed(4)}</span>}
                    </div>
                    <div>保证金: <span className="font-mono">${op.details.margin_usdt?.toFixed(2)}</span> ({op.details.leverage}x)</div>
                  </>
                )}

                {op.operation === 'add_position' && (
                  <>
                    <div className="flex items-center gap-1">
                      <span>入场价:</span>
                      <span className="line-through text-gray-400">${op.details.old_entry?.toFixed(4)}</span>
                      <span>→</span>
                      <span className="font-semibold text-blue-600">${op.details.new_entry?.toFixed(4)}</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <span>数量:</span>
                      <span className="text-gray-400">{op.details.old_qty?.toFixed(2)}</span>
                      <span className="text-green-600">+{op.details.add_qty?.toFixed(2)}</span>
                      <span>→</span>
                      <span className="font-semibold">{op.details.new_qty?.toFixed(2)}</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <span>保证金:</span>
                      <span className="text-gray-400">${op.details.old_margin?.toFixed(2)}</span>
                      <span className="text-green-600">+${op.details.add_margin?.toFixed(2)}</span>
                      <span>→</span>
                      <span className="font-semibold">${op.details.new_margin?.toFixed(2)}</span>
                    </div>
                    <div className="text-[10px] text-gray-500">
                      加仓价: ${op.details.current_price?.toFixed(4)} | 名义价值: +${op.details.add_notional?.toFixed(2)}
                    </div>
                    {(op.details.old_tp !== op.details.new_tp || op.details.old_sl !== op.details.new_sl) && (
                      <div className="mt-1 pt-1 border-t border-gray-200 dark:border-gray-600 text-[10px]">
                        {op.details.old_tp !== op.details.new_tp && (
                          <div>TP: ${op.details.old_tp?.toFixed(4)} → ${op.details.new_tp?.toFixed(4)}</div>
                        )}
                        {op.details.old_sl !== op.details.new_sl && (
                          <div>SL: ${op.details.old_sl?.toFixed(4)} → ${op.details.new_sl?.toFixed(4)}</div>
                        )}
                      </div>
                    )}
                  </>
                )}

                {op.operation === 'update_tp_sl' && (
                  <div className="space-y-1">
                    {(op.details.old_tp !== op.details.new_tp) && (
                      <div className="flex items-center gap-1">
                        <span className="text-green-600">TP:</span>
                        <span className="line-through text-gray-400">${op.details.old_tp?.toFixed(4)}</span>
                        <span>→</span>
                        <span className="font-semibold text-green-600">${op.details.new_tp?.toFixed(4)}</span>
                      </div>
                    )}
                    {(op.details.old_sl !== op.details.new_sl) && (
                      <div className="flex items-center gap-1">
                        <span className="text-red-600">SL:</span>
                        <span className="line-through text-gray-400">${op.details.old_sl?.toFixed(4)}</span>
                        <span>→</span>
                        <span className="font-semibold text-red-600">${op.details.new_sl?.toFixed(4)}</span>
                      </div>
                    )}
                  </div>
                )}

                {op.operation === 'close' && (
                  <>
                    <div>平仓价: <span className="font-mono">${op.details.close_price?.toFixed(4)}</span></div>
                    <div className="flex items-center gap-2">
                      <span>盈亏: <span className={`font-semibold ${(op.details.realized_pnl || 0) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        ${op.details.realized_pnl?.toFixed(2)}
                      </span></span>
                      {op.details.trigger_type && (
                        <span className={`px-1.5 py-0.5 rounded text-[10px] ${op.details.trigger_type === 'auto'
                          ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400'
                          : 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-400'
                          }`}>
                          {op.details.trigger_type === 'auto' ? '自动触发' : 'Agent干预'}
                        </span>
                      )}
                    </div>
                    {op.details.close_reason && (
                      <div className="text-[10px] text-gray-500">原因: {op.details.close_reason}</div>
                    )}
                  </>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function TradeStateCard({ data }: TradeStateCardProps) {
  const [expandedPositions, setExpandedPositions] = useState<Set<string>>(new Set());

  const togglePosition = (positionId: string) => {
    setExpandedPositions(prev => {
      const newSet = new Set(prev);
      if (newSet.has(positionId)) {
        newSet.delete(positionId);
      } else {
        newSet.add(positionId);
      }
      return newSet;
    });
  };
  if (!data || !data.account) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
        <h2 className="text-xl font-bold mb-4 text-gray-800 dark:text-white">当前交易状态</h2>
        <div className="flex items-center justify-center h-32 text-gray-500">
          暂无数据
        </div>
      </div>
    );
  }

  const { account, positions } = data;
  const pnlColor = (account.unrealized_pnl || 0) >= 0 ? 'text-green-600' : 'text-red-600';
  const pnlBg = (account.unrealized_pnl || 0) >= 0 ? 'bg-green-50 dark:bg-green-900/20' : 'bg-red-50 dark:bg-red-900/20';

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-bold text-gray-800 dark:text-white">当前交易状态</h2>
        <div className="flex items-center space-x-2">
          <Package className="w-5 h-5 text-purple-600" />
          <span className="px-3 py-1 rounded-full text-sm font-semibold bg-purple-100 text-purple-800">
            {account.positions_count || 0} 个持仓
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
        <div className="bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-900/20 dark:to-blue-800/20 rounded-lg p-4">
          <div className="flex items-center space-x-2 mb-2">
            <DollarSign className="w-4 h-4 text-blue-600" />
            <p className="text-xs text-blue-700 dark:text-blue-400">权益资产</p>
          </div>
          <p className="text-lg font-bold text-blue-900 dark:text-blue-100">
            ${(account.equity || 0).toFixed(2)}
          </p>
        </div>

        <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4">
          <div className="flex items-center space-x-2 mb-2">
            <DollarSign className="w-4 h-4 text-gray-500" />
            <p className="text-xs text-gray-500 dark:text-gray-400">账户余额</p>
          </div>
          <p className="text-lg font-bold text-gray-800 dark:text-white">
            ${(account.balance || 0).toFixed(2)}
          </p>
        </div>

        <div className={`${pnlBg} rounded-lg p-4`}>
          <div className="flex items-center space-x-2 mb-2">
            <Activity className="w-4 h-4 text-gray-500" />
            <p className="text-xs text-gray-500 dark:text-gray-400">未实现盈亏</p>
          </div>
          <p className={`text-lg font-bold ${pnlColor}`}>
            ${(account.unrealized_pnl || 0).toFixed(2)}
          </p>
        </div>

        <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-4">
          <div className="flex items-center space-x-2 mb-2">
            <DollarSign className="w-4 h-4 text-purple-600" />
            <p className="text-xs text-purple-700 dark:text-purple-400">已实现盈亏</p>
          </div>
          <p className={`text-lg font-bold ${(account.realized_pnl || 0) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
            ${(account.realized_pnl || 0).toFixed(2)}
          </p>
        </div>
      </div>

      {positions && positions.length > 0 && (
        <div className="border-t dark:border-gray-700 pt-4">
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
            持仓列表（{positions.length}个）
          </h3>
          <div className="space-y-3">
            {positions.map((position) => {
              const isLong = position.side === 'long';
              const pnl = (position.latest_mark_price - position.entry_price) * position.qty * (isLong ? 1 : -1);
              const pnlPercent = ((position.latest_mark_price - position.entry_price) / position.entry_price) * 100 * (isLong ? 1 : -1);
              const isExpanded = expandedPositions.has(position.id);
              const hasOperationHistory = position.operation_history && position.operation_history.length > 0;

              return (
                <div key={position.id} className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3">
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center space-x-2">
                      {isLong ? (
                        <TrendingUp className="w-4 h-4 text-green-600" />
                      ) : (
                        <TrendingDown className="w-4 h-4 text-red-600" />
                      )}
                      <span className="font-bold text-gray-800 dark:text-white">{position.symbol}</span>
                      <span className={`px-2 py-0.5 rounded text-xs font-semibold ${isLong ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                        }`}>
                        {isLong ? '多头' : '空头'} {position.leverage}x
                      </span>
                      {hasOperationHistory && (
                        <button
                          onClick={() => togglePosition(position.id)}
                          className="ml-auto p-1 hover:bg-gray-200 dark:hover:bg-gray-600 rounded transition-colors"
                          title={isExpanded ? '收起操作历史' : '查看操作历史'}
                        >
                          {isExpanded ? (
                            <ChevronUp className="w-4 h-4 text-gray-500" />
                          ) : (
                            <ChevronDown className="w-4 h-4 text-gray-500" />
                          )}
                        </button>
                      )}
                    </div>
                    <div className="text-right">
                      <p className={`text-sm font-bold ${pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        ${pnl.toFixed(2)} ({pnlPercent >= 0 ? '+' : ''}{pnlPercent.toFixed(2)}%)
                      </p>
                    </div>
                  </div>

                  <div className="grid grid-cols-4 gap-2 text-xs">
                    <div>
                      <p className="text-gray-500 dark:text-gray-400">入场价</p>
                      <p className="font-semibold text-gray-800 dark:text-white">${position.entry_price.toFixed(4)}</p>
                    </div>
                    <div>
                      <p className="text-gray-500 dark:text-gray-400">当前价</p>
                      <p className="font-semibold text-gray-800 dark:text-white">${position.latest_mark_price.toFixed(4)}</p>
                    </div>
                    <div>
                      <p className="text-gray-500 dark:text-gray-400">数量</p>
                      <p className="font-semibold text-gray-800 dark:text-white">{position.qty.toFixed(2)}</p>
                    </div>
                    <div>
                      <p className="text-gray-500 dark:text-gray-400">保证金</p>
                      <p className="font-semibold text-gray-800 dark:text-white">${position.margin_used.toFixed(2)}</p>
                    </div>
                  </div>

                  {(position.tp_price || position.sl_price) && (
                    <div className="mt-2 pt-2 border-t dark:border-gray-600 flex gap-3 text-xs">
                      {position.tp_price && (
                        <span className="text-green-600">
                          TP: <span className="font-semibold">${position.tp_price.toFixed(4)}</span>
                          {position.original_tp_price && position.original_tp_price !== position.tp_price && (
                            <span className="ml-1 text-gray-400 line-through text-[10px]">${position.original_tp_price.toFixed(4)}</span>
                          )}
                        </span>
                      )}
                      {position.sl_price && (
                        <span className="text-red-600">
                          SL: <span className="font-semibold">${position.sl_price.toFixed(4)}</span>
                          {position.original_sl_price && position.original_sl_price !== position.sl_price && (
                            <span className="ml-1 text-gray-400 line-through text-[10px]">${position.original_sl_price.toFixed(4)}</span>
                          )}
                        </span>
                      )}
                    </div>
                  )}

                  {/* 操作历史展示 */}
                  {isExpanded && hasOperationHistory && (
                    <div className="mt-3 pt-3 border-t dark:border-gray-600">
                      <OperationTimeline operations={position.operation_history!} />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="mt-4 text-xs text-gray-500 dark:text-gray-400">
        最后更新: {new Date(data.ts).toLocaleString('zh-CN')}
      </div>
    </div>
  );
}
