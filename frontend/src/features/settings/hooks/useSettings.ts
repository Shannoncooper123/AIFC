/**
 * Settings 相关的 React Query hooks
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getConfig, reloadConfig, updateConfigSection } from '../../../services/api';
import type { ConfigResponse, ConfigUpdateResponse } from '../../../types';

/**
 * 获取配置数据的 hook
 */
export function useConfig() {
  return useQuery<ConfigResponse>({
    queryKey: ['config'],
    queryFn: getConfig,
  });
}

/**
 * 重新加载配置的 hook
 */
export function useReloadConfig() {
  const queryClient = useQueryClient();

  return useMutation<ConfigUpdateResponse, Error>({
    mutationFn: reloadConfig,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['config'] });
    },
  });
}

/**
 * 更新配置节的 hook
 */
export function useUpdateConfigSection(onSuccess?: () => void) {
  const queryClient = useQueryClient();

  return useMutation<
    ConfigUpdateResponse,
    Error,
    { section: string; data: Record<string, unknown> }
  >({
    mutationFn: ({ section, data }) => updateConfigSection(section, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['config'] });
      onSuccess?.();
    },
  });
}
