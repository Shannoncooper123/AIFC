/**
 * 通用格式化工具函数
 */

/**
 * 格式化时间戳为本地时间字符串
 * @param value - ISO 时间字符串
 * @returns 格式化后的本地时间字符串
 */
export function formatTime(value?: string): string {
  if (!value) return '—';
  return new Date(value).toLocaleString();
}

/**
 * 格式化毫秒为可读的持续时间
 * @param ms - 毫秒数
 * @returns 格式化后的持续时间字符串
 */
export function formatDuration(ms?: number): string {
  if (ms === undefined || ms === null) return '—';
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
}

/**
 * 格式化数字为货币格式
 * @param value - 数值
 * @param currency - 货币类型，默认 USD
 * @returns 格式化后的货币字符串
 */
export function formatCurrency(value: number, currency = 'USD'): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

/**
 * 格式化百分比
 * @param value - 小数形式的百分比值
 * @param decimals - 小数位数
 * @returns 格式化后的百分比字符串
 */
export function formatPercent(value: number, decimals = 2): string {
  return `${(value * 100).toFixed(decimals)}%`;
}

/**
 * 格式化数字，添加千分位分隔符
 * @param value - 数值
 * @param decimals - 小数位数
 * @returns 格式化后的数字字符串
 */
export function formatNumber(value: number, decimals = 2): string {
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

/**
 * 截断字符串并添加省略号
 * @param str - 原始字符串
 * @param maxLength - 最大长度
 * @returns 截断后的字符串
 */
export function truncate(str: string, maxLength: number): string {
  if (str.length <= maxLength) return str;
  return `${str.slice(0, maxLength)}...`;
}
