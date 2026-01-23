/**
 * Dashboard 相关类型定义
 */

import type { ServiceStatus } from './common';

export interface ServiceInfo {
  name: string;
  status: ServiceStatus;
  pid: number | null;
  started_at: string | null;
  error: string | null;
}

export interface SystemStatus {
  status: string;
  services: Record<string, ServiceInfo>;
  timestamp: string;
}

export interface AccountSummary {
  total_balance: number;
  available_balance: number;
  unrealized_pnl: number;
  margin_used: number;
  margin_ratio?: number;
}

export interface TradeState {
  account: AccountSummary;
  positions: import('./positions').Position[];
  pending_orders: Record<string, unknown>[];
}

export interface PositionsSummary {
  open_positions: number;
  total_trades: number;
  win_count: number;
  loss_count: number;
  win_rate: number;
  total_unrealized_pnl: number;
  total_realized_pnl: number;
}
