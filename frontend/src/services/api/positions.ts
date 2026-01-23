/**
 * Positions 相关 API
 */

import { apiClient } from './client';
import type { Position, PositionHistory } from '../../types';

export async function getPositions(): Promise<{ positions: Position[]; total: number }> {
  const { data } = await apiClient.get('/positions');
  return data;
}

export async function getPositionHistory(
  limit = 50
): Promise<{ positions: PositionHistory[]; total: number; total_pnl: number }> {
  const { data } = await apiClient.get('/positions/history', { params: { limit } });
  return data;
}
