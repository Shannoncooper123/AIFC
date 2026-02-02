/**
 * 反向交易相关类型定义
 */

export interface ReverseConfig {
  enabled: boolean;
  fixed_margin_usdt: number;
  fixed_leverage: number;
  expiration_days: number;
  max_positions: number;
}

export interface ReversePosition {
  symbol: string;
  side: 'LONG' | 'SHORT';
  size: number;
  entry_price: number;
  mark_price?: number;
  take_profit?: number;
  stop_loss?: number;
  unrealized_pnl?: number;
  roe?: number;
  leverage: number;
  margin: number;
  opened_at?: string;
  algo_order_id?: string;
  agent_order_id?: string;
}

export interface ReversePendingOrder {
  algo_id: string;
  symbol: string;
  side: string;
  trigger_price: number;
  quantity: number;
  status: string;
  tp_price?: number;
  sl_price?: number;
  leverage: number;
  margin_usdt: number;
  created_at: string;
  expires_at?: string;
  agent_order_id?: string;
  agent_side?: string;
}

export interface ReverseHistoryEntry {
  id: string;
  symbol: string;
  side: string;
  qty: number;
  entry_price: number;
  exit_price: number;
  leverage: number;
  margin_usdt: number;
  realized_pnl: number;
  pnl_percent: number;
  open_time: string;
  close_time: string;
  close_reason: string;
  algo_order_id?: string;
  agent_order_id?: string;
}

export interface ReverseStatistics {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  total_pnl: number;
  avg_pnl: number;
  max_profit: number;
  max_loss: number;
}

export interface ReverseSummary {
  enabled: boolean;
  config: ReverseConfig;
  pending_orders_count: number;
  positions_count: number;
  statistics: ReverseStatistics;
}

export interface ReversePositionsResponse {
  positions: ReversePosition[];
  total: number;
}

export interface ReversePendingOrdersResponse {
  orders: ReversePendingOrder[];
  total: number;
}

export interface ReverseHistoryResponse {
  history: ReverseHistoryEntry[];
  total: number;
}
