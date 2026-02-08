/**
 * 实盘交易相关类型定义
 */

export interface LiveTradingConfig {
  reverse_enabled: boolean;
  fixed_margin_usdt: number;
  fixed_leverage: number;
  expiration_days: number;
  max_positions: number;
}

export interface LivePosition {
  id: string;
  symbol: string;
  side: 'LONG' | 'SHORT' | string;
  size: number;
  entry_price: number;
  mark_price?: number;
  take_profit?: number;
  stop_loss?: number;
  tp_order_id?: number;
  tp_algo_id?: string;
  sl_algo_id?: string;
  unrealized_pnl?: number;
  roe?: number;
  leverage: number;
  margin: number;
  opened_at?: string;
  algo_order_id?: string;
  agent_order_id?: string;
  source?: string;
}

export interface LivePendingOrder {
  id: string;
  algo_id?: string;
  order_id?: number;
  order_kind: 'CONDITIONAL' | 'LIMIT' | string;
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
  agent_limit_price?: number;
  source?: string;
  triggered_at?: string;
  filled_at?: string;
  filled_price?: number;
}

export interface LiveHistoryEntry {
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
  entry_commission?: number;
  exit_commission?: number;
  total_commission?: number;
  source?: string;
}

export interface LiveStatistics {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  total_pnl: number;
  avg_pnl: number;
  max_profit: number;
  max_loss: number;
  total_commission?: number;
  open_count?: number;
  engine_running?: boolean;
}

export interface LiveSummary {
  engine_running: boolean;
  reverse_enabled: boolean;
  config: LiveTradingConfig;
  pending_orders_count: number;
  positions_count: number;
  statistics: LiveStatistics;
}

export interface LivePositionsResponse {
  positions: LivePosition[];
  total: number;
  engine_running?: boolean;
}

export interface LivePendingOrdersResponse {
  orders: LivePendingOrder[];
  total: number;
  total_conditional: number;
  total_limit: number;
  engine_running?: boolean;
}

export interface LiveHistoryResponse {
  history: LiveHistoryEntry[];
  total: number;
  engine_running?: boolean;
}
