/**
 * Alerts 相关 hooks
 */

import { useQuery } from '@tanstack/react-query';
import { getAlerts, getAlertSymbols } from '../../../services/api';
import { REFRESH_INTERVALS } from '../../../utils';

/**
 * 获取 alerts 列表
 */
export function useAlerts(limit = 50, symbol?: string) {
  return useQuery({
    queryKey: ['alerts', limit, symbol],
    queryFn: () => getAlerts(limit, symbol),
    refetchInterval: REFRESH_INTERVALS.ALERTS,
  });
}

/**
 * 获取 alert symbols 列表
 */
export function useAlertSymbols() {
  return useQuery({
    queryKey: ['alertSymbols'],
    queryFn: getAlertSymbols,
  });
}
