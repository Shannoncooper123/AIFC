/**
 * Workflow 相关工具函数
 */

import type { TraceType } from '../../../types';

/**
 * 节点显示名称映射
 */
const NODE_NAME_MAP: Record<string, string> = {
  context_injection: '上下文注入',
  position_management: '持仓管理',
  analyze_symbol: '币种分析',
  analysis: '技术分析',
  decision: '开仓决策',
  single_symbol_analysis: '技术分析',
  single_symbol_analysis_long: '做多分析',
  single_symbol_analysis_short: '做空分析',
  opening_decision: '开仓决策',
  reporting: '报告生成',
  barrier: '占位节点',
  analysis_barrier: '占位节点',
  join_node: '汇合节点',
  pm_barrier: '持仓屏障',
  ab_barrier_1: '占位节点',
  ab_barrier_2: '占位节点',
};

/**
 * Trace 类型显示名称映射
 */
const TRACE_TYPE_NAME_MAP: Record<TraceType, string> = {
  workflow: '工作流',
  node: '节点',
  agent: 'Agent',
  model_call: '模型调用',
  tool_call: '工具调用',
  artifact: '产物',
};

/**
 * Trace 类型对应的 lucide-react 图标名称
 */
export const TRACE_TYPE_ICON_MAP: Record<TraceType, string> = {
  workflow: 'Workflow',
  node: 'Box',
  agent: 'Bot',
  model_call: 'Brain',
  tool_call: 'Wrench',
  artifact: 'Image',
};

/**
 * 获取节点显示名称
 * @param node - 节点标识
 * @returns 格式化后的节点名称
 */
export function getNodeDisplayName(node: string): string {
  if (node.startsWith('tool:')) {
    return node.replace('tool:', '');
  }
  return NODE_NAME_MAP[node] || node;
}

/**
 * 获取 Trace 类型显示名称
 * @param type - Trace 类型
 * @returns 格式化后的类型名称
 */
export function getTraceTypeName(type: TraceType): string {
  return TRACE_TYPE_NAME_MAP[type] || type;
}

/**
 * 获取 Trace 类型图标名称
 * @param type - Trace 类型
 * @returns lucide-react 图标名称
 */
export function getTraceTypeIcon(type: TraceType): string {
  return TRACE_TYPE_ICON_MAP[type] || 'Circle';
}

/**
 * 获取状态文字颜色类名
 * @param status - 状态值
 * @returns Tailwind 颜色类名
 */
export function getStatusColor(status: string): string {
  switch (status) {
    case 'success':
      return 'text-emerald-500/80';
    case 'error':
      return 'text-rose-500/80';
    case 'running':
      return 'text-yellow-400/80';
    default:
      return 'text-neutral-400';
  }
}

/**
 * 获取状态背景颜色类名
 * @param status - 状态值
 * @returns Tailwind 背景和边框颜色类名
 */
export function getStatusBgColor(status: string): string {
  switch (status) {
    case 'success':
      return 'bg-emerald-500/20 border-emerald-500/30';
    case 'error':
      return 'bg-rose-500/20 border-rose-500/30';
    case 'running':
      return 'bg-yellow-500/20 border-yellow-500/30';
    default:
      return 'bg-neutral-500/20 border-neutral-500/30';
  }
}

/**
 * 获取 Trace 类型对应的颜色类名
 * @param type - Trace 类型
 * @returns Tailwind 颜色类名
 */
export function getTraceTypeColor(type: TraceType): string {
  switch (type) {
    case 'workflow':
      return 'text-blue-400';
    case 'node':
      return 'text-purple-400';
    case 'agent':
      return 'text-cyan-400';
    case 'model_call':
      return 'text-pink-400';
    case 'tool_call':
      return 'text-orange-400';
    case 'artifact':
      return 'text-green-400';
    default:
      return 'text-neutral-400';
  }
}
