/**
 * Settings 相关 API
 */

import { apiClient } from './client';
import type { ConfigResponse, ConfigUpdateResponse } from '../../types';

export async function getConfig(): Promise<ConfigResponse> {
  const { data } = await apiClient.get('/config');
  return data;
}

export async function getConfigSection(
  section: string
): Promise<{ section: string; data: Record<string, unknown> }> {
  const { data } = await apiClient.get(`/config/${section}`);
  return data;
}

export async function updateConfigSection(
  section: string,
  configData: Record<string, unknown>
): Promise<ConfigUpdateResponse> {
  const { data } = await apiClient.put(`/config/${section}`, { section, data: configData });
  return data;
}

export async function reloadConfig(): Promise<ConfigUpdateResponse> {
  const { data } = await apiClient.post('/config/reload');
  return data;
}
