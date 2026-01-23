// 数据类型定义

export interface TradeStateAccount {
  balance: number;
  equity: number;
  positions_count: number;
  realized_pnl: number;
  reserved_margin_sum: number;
  unrealized_pnl: number;
}

export interface OperationDetail {
  // 开仓相关
  entry_price?: number;
  tp_price?: number | null;
  sl_price?: number | null;
  notional?: number;
  leverage?: number;
  margin_usdt?: number;

  // 更新 TP/SL 相关
  old_tp?: number | null;
  new_tp?: number | null;
  old_sl?: number | null;
  new_sl?: number | null;

  // 加仓相关
  add_qty?: number;
  add_margin?: number;
  add_notional?: number;
  current_price?: number;
  old_entry?: number;
  new_entry?: number;
  old_qty?: number;
  new_qty?: number;
  old_margin?: number;
  new_margin?: number;

  // 平仓相关
  close_price?: number;
  realized_pnl?: number;
  close_reason?: string;
  trigger_type?: string;

  note?: string;
}

export interface OperationHistoryItem {
  timestamp: string;
  operation: 'open' | 'update_tp_sl' | 'add_position' | 'close';
  details: OperationDetail;
}

export interface TradeStatePosition {
  id: string;
  symbol: string;
  side: string;
  entry_price: number;
  latest_mark_price: number;
  qty: number;
  leverage: number;
  margin_used: number;
  notional_usdt: number;
  tp_price: number | null;
  sl_price: number | null;
  original_tp_price?: number | null;  // 新增
  original_sl_price?: number | null;
  operation_history?: OperationHistoryItem[];  // 新增
  status: string;
  open_time: string;
  close_price: number | null;
  close_reason: string | null;
  close_time: string | null;
  fees_open: number;
  fees_close: number;
  realized_pnl: number;
}

export interface TradeState {
  account: TradeStateAccount;
  positions: TradeStatePosition[];
  ts: string;
}

export interface HistoricalPosition {
  id: string;
  symbol: string;
  side: string;
  entry_price: number;
  close_price: number | null;
  close_reason: string | null;
  close_time: string | null;
  open_time: string;
  leverage: number;
  notional_usdt: number;
  realized_pnl: number;
  tp_price: number | null;
  sl_price: number | null;
  fees_open: number;
  fees_close: number;
}

export interface PositionHistory {
  positions: HistoricalPosition[];
}

export interface AgentReport {
  ts: number;
  summary: string;
  symbols: string[];
  next_focus: string;
  next_wakeup_minutes: number;
  next_wakeup_at: string;
}

export interface AgentReports {
  reports: AgentReport[];
}

export interface PendingOrder {
  id: string;
  symbol: string;
  side: string;
  order_type: string;
  limit_price: number;
  margin_usdt: number;
  leverage: number;
  status: string;
  create_time: string;
  filled_price: number | null;
  filled_time: string | null;
  tp_price: number | null;
  sl_price: number | null;
  position_id: string | null;
}

export interface PendingOrders {
  orders: PendingOrder[];
}

export interface AssetSnapshot {
  timestamp: string;
  equity: number;
  balance: number;
  unrealized_pnl: number;
  realized_pnl: number;
  reserved_margin: number;
  positions_count: number;
}

export interface AssetTimeline {
  timeline: AssetSnapshot[];
}

export interface DashboardData {
  trade_state: TradeState | null;
  position_history: PositionHistory | null;
  agent_reports: AgentReports | null;
  pending_orders: PendingOrders | null;
  asset_timeline: AssetTimeline | null;
  last_update: string;
}

