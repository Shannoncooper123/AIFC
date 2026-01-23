/**
 * Alerts 相关类型定义
 */

export interface AlertEntry {
  symbol: string;
  price: number;
  price_change_rate: number;
  triggered_indicators: string[];
  engulfing_type?: string;
  timestamp?: string;
}

export interface AlertRecord {
  ts: string;
  interval: string;
  entries: AlertEntry[];
}
