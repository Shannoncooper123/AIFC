/**
 * Workflow 相关 API
 */

import { apiClient } from './client';
import type {
  WorkflowRunSummary,
  WorkflowRunEvent,
  WorkflowArtifact,
  WorkflowTimeline,
} from '../../types';

export async function getWorkflowRuns(
  limit = 50
): Promise<{ runs: WorkflowRunSummary[]; total: number }> {
  const { data } = await apiClient.get('/workflow/runs', { params: { limit } });
  return data;
}

export async function getWorkflowRun(runId: string): Promise<{ run_id: string; events: WorkflowRunEvent[] }> {
  const { data } = await apiClient.get(`/workflow/runs/${runId}`);
  return data;
}

export async function getWorkflowTimeline(runId: string): Promise<{ timeline: WorkflowTimeline }> {
  const { data } = await apiClient.get(`/workflow/runs/${runId}/timeline`);
  return data;
}

export async function getWorkflowArtifacts(runId: string): Promise<WorkflowArtifact[]> {
  const { data } = await apiClient.get(`/workflow/runs/${runId}/artifacts`);
  return data;
}
