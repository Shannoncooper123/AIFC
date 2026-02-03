/**
 * 通用格式化工具函数
 */

/**
 * 格式化时间戳为本地时间字符串
 * @param value - ISO 时间字符串
 * @returns 格式化后的本地时间字符串，格式：YYYY-MM-DD HH:mm
 */
export function formatTime(value?: string): string {
  if (!value) return '—';
  const date = new Date(value);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  return `${year}-${month}-${day} ${hours}:${minutes}`;
}

/**
 * 格式化时间戳为 UTC 时间字符串
 * @param value - ISO 时间字符串
 * @returns 格式化后的 UTC 时间字符串，格式：YYYY-MM-DD HH:mm (UTC)
 */
export function formatTimeUTC(value?: string): string {
  if (!value) return '—';
  const date = new Date(value);
  const year = date.getUTCFullYear();
  const month = String(date.getUTCMonth() + 1).padStart(2, '0');
  const day = String(date.getUTCDate()).padStart(2, '0');
  const hours = String(date.getUTCHours()).padStart(2, '0');
  const minutes = String(date.getUTCMinutes()).padStart(2, '0');
  return `${year}-${month}-${day} ${hours}:${minutes}`;
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
 * 智能格式化价格，根据价格大小自动调整小数位数
 * 适用于加密货币价格显示，如 BTC ($50000) 和 DOGE ($0.10952)
 * @param value - 价格数值
 * @param showDollar - 是否显示美元符号，默认 true
 * @returns 格式化后的价格字符串
 */
export function formatPrice(value: number | undefined | null, showDollar = true): string {
  if (value === undefined || value === null || isNaN(value)) return '—';
  
  let decimals: number;
  const absValue = Math.abs(value);
  
  if (absValue === 0) {
    decimals = 2;
  } else if (absValue >= 1000) {
    decimals = 2;
  } else if (absValue >= 100) {
    decimals = 3;
  } else if (absValue >= 10) {
    decimals = 4;
  } else if (absValue >= 1) {
    decimals = 4;
  } else if (absValue >= 0.1) {
    decimals = 5;
  } else if (absValue >= 0.01) {
    decimals = 6;
  } else if (absValue >= 0.001) {
    decimals = 7;
  } else {
    decimals = 8;
  }
  
  const formatted = value.toFixed(decimals);
  return showDollar ? `$${formatted}` : formatted;
}

/**
 * 格式化价格变化百分比
 * @param current - 当前价格
 * @param target - 目标价格
 * @returns 格式化后的百分比字符串，带正负号
 */
export function formatPriceChange(current: number, target: number): string {
  if (!current || !target) return '—';
  const change = ((target - current) / current) * 100;
  const sign = change >= 0 ? '+' : '';
  return `${sign}${change.toFixed(2)}%`;
}

/**
 * 计算距离目标价格的百分比
 * @param current - 当前价格
 * @param target - 目标价格
 * @returns 百分比数值
 */
export function calcPriceDistance(current: number, target: number): number {
  if (!current || !target) return 0;
  return ((target - current) / current) * 100;
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
