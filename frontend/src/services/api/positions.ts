/**
 * Positions 相关 API
 */

import { apiClient } from './client';
import type { Position, PositionHistory, LimitOrder } from '../../types';

export async function getPositions(): Promise<{ positions: Position[]; total: number; pending_orders: LimitOrder[] }> {
  const { data } = await apiClient.get('/positions');
  return data;
}

export async function getPositionHistory(
  limit = 50
): Promise<{ positions: PositionHistory[]; total: number; total_pnl: number }> {
  const { data } = await apiClient.get('/positions/history', { params: { limit } });
  return data;
}
