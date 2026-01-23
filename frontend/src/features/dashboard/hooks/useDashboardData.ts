/**
 * Dashboard 相关 hooks
 */

import { useQuery } from '@tanstack/react-query';
import {
  getSystemStatus,
  getTradeState,
  getPositionsSummary,
} from '../../../services/api';
import { REFRESH_INTERVALS } from '../../../utils';

/**
 * 获取系统状态
 */
export function useSystemStatus() {
  return useQuery({
    queryKey: ['systemStatus'],
    queryFn: getSystemStatus,
    refetchInterval: REFRESH_INTERVALS.SYSTEM_STATUS,
  });
}

/**
 * 获取交易状态
 */
export function useTradeState() {
  return useQuery({
    queryKey: ['tradeState'],
    queryFn: getTradeState,
    refetchInterval: REFRESH_INTERVALS.TRADE_STATE,
  });
}

/**
 * 获取持仓摘要
 */
export function usePositionsSummary() {
  return useQuery({
    queryKey: ['positionsSummary'],
    queryFn: getPositionsSummary,
    refetchInterval: REFRESH_INTERVALS.POSITIONS,
  });
}

/**
 * 组合 hook，获取 Dashboard 所需的所有数据
 */
export function useDashboardData() {
  const systemStatusQuery = useSystemStatus();
  const tradeStateQuery = useTradeState();
  const summaryQuery = usePositionsSummary();

  const isLoading =
    systemStatusQuery.isLoading ||
    tradeStateQuery.isLoading ||
    summaryQuery.isLoading;

  const hasError =
    systemStatusQuery.error || tradeStateQuery.error || summaryQuery.error;

  return {
    systemStatus: systemStatusQuery.data,
    tradeState: tradeStateQuery.data,
    summary: summaryQuery.data,
    isLoading,
    hasError,
    refetchSystem: systemStatusQuery.refetch,
  };
}
