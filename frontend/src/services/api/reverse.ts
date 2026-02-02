/**
 * 反向交易相关 API
 */

import { apiClient } from './client';
import type {
  ReverseConfig,
  ReversePositionsResponse,
  ReversePendingOrdersResponse,
  ReverseHistoryResponse,
  ReverseStatistics,
  ReverseSummary,
} from '../../types/reverse';

export async function getReverseConfig(): Promise<ReverseConfig> {
  const { data } = await apiClient.get('/reverse/config');
  return data;
}

export async function updateReverseConfig(config: Partial<ReverseConfig>): Promise<ReverseConfig> {
  const { data } = await apiClient.post('/reverse/config', config);
  return data;
}

export async function getReversePositions(): Promise<ReversePositionsResponse> {
  const { data } = await apiClient.get('/reverse/positions');
  return data;
}

export async function getReversePendingOrders(): Promise<ReversePendingOrdersResponse> {
  const { data } = await apiClient.get('/reverse/pending-orders');
  return data;
}

export async function cancelReversePendingOrder(algoId: string): Promise<{ success: boolean; message: string }> {
  const { data } = await apiClient.delete(`/reverse/pending-orders/${algoId}`);
  return data;
}

export async function getReverseHistory(limit = 50): Promise<ReverseHistoryResponse> {
  const { data } = await apiClient.get('/reverse/history', { params: { limit } });
  return data;
}

export async function getReverseStatistics(): Promise<ReverseStatistics> {
  const { data } = await apiClient.get('/reverse/statistics');
  return data;
}

export async function getReverseSummary(): Promise<ReverseSummary> {
  const { data } = await apiClient.get('/reverse/summary');
  return data;
}

export async function startReverseEngine(): Promise<{ success: boolean; message: string }> {
  const { data } = await apiClient.post('/reverse/start');
  return data;
}

export async function stopReverseEngine(): Promise<{ success: boolean; message: string }> {
  const { data } = await apiClient.post('/reverse/stop');
  return data;
}

export async function startSymbolWorkflow(
  symbol: string,
  interval: string = '15m'
): Promise<{ success: boolean; message: string; symbol: string; interval: string }> {
  const { data } = await apiClient.post(`/reverse/workflow/start/${symbol}`, null, {
    params: { interval }
  });
  return data;
}

export async function stopSymbolWorkflow(
  symbol: string
): Promise<{ success: boolean; message: string; symbol: string }> {
  const { data } = await apiClient.post(`/reverse/workflow/stop/${symbol}`);
  return data;
}

export interface WorkflowStatus {
  symbol: string;
  interval: string;
  running: boolean;
  workflow_count: number;
  start_time: string | null;
  last_kline_time: string | null;
}

export interface AllWorkflowStatus {
  running_count: number;
  symbols: Record<string, WorkflowStatus>;
}

export async function getWorkflowStatus(symbol?: string): Promise<WorkflowStatus | AllWorkflowStatus> {
  const { data } = await apiClient.get('/reverse/workflow/status', {
    params: symbol ? { symbol } : undefined
  });
  return data;
}

export async function getRunningWorkflows(): Promise<{ count: number; symbols: string[] }> {
  const { data } = await apiClient.get('/reverse/workflow/running');
  return data;
}
