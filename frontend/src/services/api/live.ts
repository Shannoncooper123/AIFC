/**
 * 实盘交易相关 API
 */

import { apiClient } from './client';
import type {
  LiveTradingConfig,
  LivePositionsResponse,
  LivePendingOrdersResponse,
  LiveHistoryResponse,
  LiveStatistics,
  LiveSummary,
} from '../../types/live';

export async function getLiveConfig(): Promise<LiveTradingConfig> {
  const { data } = await apiClient.get('/live/config');
  return data;
}

export async function updateLiveConfig(config: Partial<LiveTradingConfig>): Promise<LiveTradingConfig> {
  const { data } = await apiClient.post('/live/config', config);
  return data;
}

export async function getLivePositions(source?: string): Promise<LivePositionsResponse> {
  const { data } = await apiClient.get('/live/positions', { params: source ? { source } : undefined });
  return data;
}

export async function getLivePendingOrders(source?: string): Promise<LivePendingOrdersResponse> {
  const { data } = await apiClient.get('/live/pending-orders', { params: source ? { source } : undefined });
  return data;
}

export async function cancelLivePendingOrder(orderId: string): Promise<{ success: boolean; message: string }> {
  const { data } = await apiClient.delete(`/live/pending-orders/${orderId}`);
  return data;
}

export async function closeLivePosition(recordId: string): Promise<{ success: boolean; message: string }> {
  const { data } = await apiClient.delete(`/live/positions/${recordId}`);
  return data;
}

export async function closeLivePositionsBySymbol(
  symbol: string,
  source?: string
): Promise<{ success: boolean; message: string; closed_count: number }> {
  const { data } = await apiClient.delete(`/live/positions/symbol/${symbol}`, {
    params: source ? { source } : undefined
  });
  return data;
}

export async function getLiveHistory(limit = 50, source?: string): Promise<LiveHistoryResponse> {
  const params: Record<string, unknown> = { limit };
  if (source) params.source = source;
  const { data } = await apiClient.get('/live/history', { params });
  return data;
}

export async function getLiveStatistics(source?: string): Promise<LiveStatistics> {
  const { data } = await apiClient.get('/live/statistics', { params: source ? { source } : undefined });
  return data;
}

export async function getLiveSummary(): Promise<LiveSummary> {
  const { data } = await apiClient.get('/live/summary');
  return data;
}

export async function startLiveEngine(): Promise<{ success: boolean; message: string }> {
  const { data } = await apiClient.post('/live/start');
  return data;
}

export async function stopLiveEngine(): Promise<{ success: boolean; message: string }> {
  const { data } = await apiClient.post('/live/stop');
  return data;
}

export async function startSymbolWorkflow(
  symbol: string,
  interval: string = '15m'
): Promise<{ success: boolean; message: string; symbol: string; interval: string }> {
  const { data } = await apiClient.post(`/live/workflow/start/${symbol}`, null, {
    params: { interval }
  });
  return data;
}

export async function stopSymbolWorkflow(
  symbol: string
): Promise<{ success: boolean; message: string; symbol: string }> {
  const { data } = await apiClient.post(`/live/workflow/stop/${symbol}`);
  return data;
}

export interface WorkflowStatus {
  symbol: string;
  interval: string;
  running: boolean;
  workflow_count: number;
  start_time: string | null;
  last_kline_time: string | null;
  reverse_mode: boolean;
}

export interface AllWorkflowStatus {
  running_count: number;
  symbols: Record<string, WorkflowStatus>;
}

export async function getWorkflowStatus(symbol?: string): Promise<WorkflowStatus | AllWorkflowStatus> {
  const { data } = await apiClient.get('/live/workflow/status', {
    params: symbol ? { symbol } : undefined
  });
  return data;
}

export async function getRunningWorkflows(): Promise<{ count: number; symbols: string[] }> {
  const { data } = await apiClient.get('/live/workflow/running');
  return data;
}
