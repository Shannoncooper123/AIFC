/**
 * Workflow 相关工具函数
 */

/**
 * 节点显示名称映射
 */
const NODE_NAME_MAP: Record<string, string> = {
  context_injection: '📋 上下文注入',
  position_management: '💼 持仓管理',
  analyze_symbol: '📊 币种分析',
  single_symbol_analysis: '📊 币种分析',
  reporting: '📝 报告生成',
  analysis_barrier: '⏸️ 分析屏障',
  join_node: '🔗 汇合节点',
};

/**
 * 获取节点显示名称
 * @param node - 节点标识
 * @returns 格式化后的节点名称
 */
export function getNodeDisplayName(node: string): string {
  if (node.startsWith('tool:')) {
    return `🔧 ${node.replace('tool:', '')}`;
  }
  return NODE_NAME_MAP[node] || node;
}

/**
 * 获取状态文字颜色类名
 * @param status - 状态值
 * @returns Tailwind 颜色类名
 */
export function getStatusColor(status: string): string {
  switch (status) {
    case 'success':
      return 'text-green-400';
    case 'error':
      return 'text-red-400';
    case 'running':
      return 'text-yellow-400';
    default:
      return 'text-slate-400';
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
      return 'bg-green-500/20 border-green-500/30';
    case 'error':
      return 'bg-red-500/20 border-red-500/30';
    case 'running':
      return 'bg-yellow-500/20 border-yellow-500/30';
    default:
      return 'bg-slate-500/20 border-slate-500/30';
  }
}
