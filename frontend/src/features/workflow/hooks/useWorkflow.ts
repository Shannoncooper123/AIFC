/**
 * Workflow 相关 hooks
 */

import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';
import {
  getWorkflowRuns,
  getWorkflowTimeline,
  getWorkflowArtifacts,
} from '../../../services/api';
import { REFRESH_INTERVALS } from '../../../utils';

/**
 * 获取 workflow 运行列表
 */
export function useWorkflowRuns(limit = 50) {
  return useQuery({
    queryKey: ['workflow-runs'],
    queryFn: () => getWorkflowRuns(limit),
    refetchInterval: REFRESH_INTERVALS.WORKFLOW,
  });
}

/**
 * 获取 workflow 时间线
 */
export function useWorkflowTimeline(runId: string | null) {
  return useQuery({
    queryKey: ['workflow-timeline', runId],
    queryFn: () => getWorkflowTimeline(runId as string),
    enabled: !!runId,
    refetchInterval: runId ? REFRESH_INTERVALS.WORKFLOW : false,
  });
}

/**
 * 获取 workflow artifacts
 */
export function useWorkflowArtifacts(runId: string | null) {
  return useQuery({
    queryKey: ['workflow-artifacts', runId],
    queryFn: () => getWorkflowArtifacts(runId as string),
    enabled: !!runId,
    refetchInterval: runId ? REFRESH_INTERVALS.WORKFLOW : false,
  });
}

/**
 * 从时间线中提取唯一的 symbols
 */
export function useUniqueSymbols(timeline: { symbols?: string[] } | undefined) {
  return useMemo(() => {
    if (!timeline?.symbols) return [];
    return timeline.symbols;
  }, [timeline]);
}
