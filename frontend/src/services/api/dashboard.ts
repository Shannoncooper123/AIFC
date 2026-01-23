/**
 * Dashboard 相关 API
 */

import { apiClient } from './client';
import type {
  SystemStatus,
  ServiceInfo,
  TradeState,
  PositionsSummary,
} from '../../types';

export async function getSystemStatus(): Promise<SystemStatus> {
  const { data } = await apiClient.get<SystemStatus>('/status');
  return data;
}

export async function getServiceStatus(name: string): Promise<ServiceInfo> {
  const { data } = await apiClient.get<ServiceInfo>(`/services/${name}`);
  return data;
}

export async function controlService(
  name: string,
  action: 'start' | 'stop' | 'restart'
): Promise<{ success: boolean; message: string; service: ServiceInfo }> {
  const { data } = await apiClient.post(`/services/${name}`, { action });
  return data;
}

export async function getServiceLogs(
  name: string,
  lines = 100
): Promise<{ service: string; lines: string[]; total: number }> {
  const { data } = await apiClient.get(`/services/${name}/logs`, { params: { lines } });
  return data;
}

export async function startAllServices(): Promise<{ success: boolean; results: Record<string, boolean> }> {
  const { data } = await apiClient.post('/services/start-all');
  return data;
}

export async function stopAllServices(): Promise<{ success: boolean; results: Record<string, boolean> }> {
  const { data } = await apiClient.post('/services/stop-all');
  return data;
}

export async function getTradeState(): Promise<TradeState> {
  const { data } = await apiClient.get<TradeState>('/positions/trade-state');
  return data;
}

export async function getPositionsSummary(): Promise<PositionsSummary> {
  const { data } = await apiClient.get<PositionsSummary>('/positions/summary');
  return data;
}
