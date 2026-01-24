/**
 * 全局常量定义
 */

/**
 * API 刷新间隔（毫秒）
 */
export const REFRESH_INTERVALS = {
  SYSTEM_STATUS: 5000,
  TRADE_STATE: 10000,
  POSITIONS: 10000,
  ALERTS: 30000,
  HISTORY: 30000,
  WORKFLOW: 10000,
} as const;

/**
 * 分页默认值
 */
export const PAGINATION = {
  DEFAULT_LIMIT: 50,
  LIMIT_OPTIONS: [25, 50, 100, 200],
} as const;

/**
 * 状态颜色映射
 */
export const STATUS_COLORS = {
  success: {
    text: 'text-green-400',
    bg: 'bg-green-500/20',
    border: 'border-green-500/30',
  },
  error: {
    text: 'text-red-400',
    bg: 'bg-red-500/20',
    border: 'border-red-500/30',
  },
  running: {
    text: 'text-yellow-400',
    bg: 'bg-yellow-500/20',
    border: 'border-yellow-500/30',
  },
  pending: {
    text: 'text-slate-400',
    bg: 'bg-slate-500/20',
    border: 'border-slate-500/30',
  },
} as const;

/**
 * 服务状态配置
 */
export const SERVICE_STATUS_CONFIG = {
  stopped: {
    color: 'text-gray-400',
    bgColor: 'bg-gray-400/20',
    label: 'Stopped',
  },
  starting: {
    color: 'text-yellow-400',
    bgColor: 'bg-yellow-400/20',
    label: 'Starting',
  },
  running: {
    color: 'text-green-400',
    bgColor: 'bg-green-400/20',
    label: 'Running',
  },
  stopping: {
    color: 'text-orange-400',
    bgColor: 'bg-orange-400/20',
    label: 'Stopping',
  },
  error: {
    color: 'text-red-400',
    bgColor: 'bg-red-400/20',
    label: 'Error',
  },
} as const;

/**
 * 导航菜单项
 */
export const NAV_ITEMS = [
  { path: '/', label: 'Dashboard', icon: 'LayoutDashboard' },
  { path: '/alerts', label: 'Alerts', icon: 'Bell' },
  { path: '/positions', label: 'Positions', icon: 'TrendingUp' },
  { path: '/workflow', label: 'Workflow', icon: 'Activity' },
  { path: '/settings', label: 'Settings', icon: 'Settings' },
] as const;
