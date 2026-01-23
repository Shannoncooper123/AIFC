'use client';

import { Clock, TrendingUp, TrendingDown, CheckCircle, XCircle } from 'lucide-react';
import type { PendingOrders } from '@/lib/types';

interface PendingOrdersCardProps {
  data: PendingOrders | null;
}

export default function PendingOrdersCard({ data }: PendingOrdersCardProps) {
  // 只显示未成交的订单（pending, active, NEW 状态）
  const pendingOrders = data?.orders?.filter(
    order => order.status !== 'filled' && order.status !== 'cancelled' && order.status !== 'expired'
  ) || [];

  if (pendingOrders.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
        <div className="flex items-center space-x-2 mb-4">
          <Clock className="w-6 h-6 text-orange-600" />
          <h2 className="text-xl font-bold text-gray-800 dark:text-white">待处理订单</h2>
        </div>
        <div className="flex items-center justify-center h-32 text-gray-500">
          暂无待处理订单
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
      <div className="flex items-center space-x-2 mb-4">
        <Clock className="w-6 h-6 text-orange-600" />
        <h2 className="text-xl font-bold text-gray-800 dark:text-white">待处理订单</h2>
        <span className="bg-orange-100 text-orange-800 text-xs font-semibold px-2 py-1 rounded-full">
          {pendingOrders.length}
        </span>
      </div>

      <div className="space-y-3">
        {pendingOrders.map((order) => {
          const isLong = order.side === 'long';

          return (
            <div 
              key={order.id} 
              className="border dark:border-gray-700 rounded-lg p-4 hover:shadow-md transition-shadow"
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center space-x-2">
                  <span className="font-bold text-lg text-gray-800 dark:text-white">
                    {order.symbol}
                  </span>
                  {isLong ? (
                    <>
                      <TrendingUp className="w-4 h-4 text-green-600" />
                      <span className="px-2 py-1 rounded text-xs font-semibold bg-green-100 text-green-800">
                        {order.leverage}x 做多
                      </span>
                    </>
                  ) : (
                    <>
                      <TrendingDown className="w-4 h-4 text-red-600" />
                      <span className="px-2 py-1 rounded text-xs font-semibold bg-red-100 text-red-800">
                        {order.leverage}x 做空
                      </span>
                    </>
                  )}
                </div>
                <span className="px-2 py-1 rounded text-xs font-semibold bg-yellow-100 text-yellow-800">
                  {order.status}
                </span>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm mb-3">
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400">订单类型</p>
                  <p className="font-semibold text-gray-800 dark:text-white capitalize">{order.order_type}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400">限价</p>
                  <p className="font-semibold text-gray-800 dark:text-white">${order.limit_price.toFixed(4)}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400">保证金</p>
                  <p className="font-semibold text-gray-800 dark:text-white">${order.margin_usdt.toFixed(2)}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400">创建时间</p>
                  <p className="font-semibold text-gray-800 dark:text-white text-xs">
                    {new Date(order.create_time).toLocaleString('zh-CN', {
                      month: '2-digit',
                      day: '2-digit',
                      hour: '2-digit',
                      minute: '2-digit'
                    })}
                  </p>
                </div>
              </div>

              {(order.tp_price || order.sl_price) && (
                <div className="pt-3 border-t dark:border-gray-700 flex gap-4 text-sm">
                  {order.tp_price && (
                    <div className="flex items-center space-x-1">
                      <CheckCircle className="w-4 h-4 text-green-600" />
                      <span className="text-xs text-gray-500 dark:text-gray-400">止盈:</span>
                      <span className="font-semibold text-green-600">${order.tp_price.toFixed(4)}</span>
                    </div>
                  )}
                  {order.sl_price && (
                    <div className="flex items-center space-x-1">
                      <XCircle className="w-4 h-4 text-red-600" />
                      <span className="text-xs text-gray-500 dark:text-gray-400">止损:</span>
                      <span className="font-semibold text-red-600">${order.sl_price.toFixed(4)}</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
