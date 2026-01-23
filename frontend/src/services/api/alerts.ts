/**
 * Alerts 相关 API
 */

import { apiClient } from './client';
import type { AlertRecord } from '../../types';

export async function getAlerts(
  limit = 50,
  symbol?: string
): Promise<{ alerts: AlertRecord[]; total: number }> {
  const { data } = await apiClient.get('/alerts', { params: { limit, symbol } });
  return data;
}

export async function getLatestAlert(): Promise<AlertRecord> {
  const { data } = await apiClient.get<AlertRecord>('/alerts/latest');
  return data;
}

export async function getAlertSymbols(): Promise<{ symbols: string[]; total: number }> {
  const { data } = await apiClient.get('/alerts/symbols');
  return data;
}
