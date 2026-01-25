/**
 * Positions 相关类型定义
 */

export type PositionSide = 'LONG' | 'SHORT';

export interface Position {
  symbol: string;
  side: PositionSide;
  size: number;
  entry_price: number;
  mark_price?: number;
  unrealized_pnl?: number;
  leverage: number;
  margin?: number;
  liquidation_price?: number;
  take_profit?: number;
  stop_loss?: number;
  opened_at?: string;
  open_run_id?: string;
}

export interface PositionHistory {
  symbol: string;
  side: PositionSide;
  size: number;
  entry_price: number;
  exit_price: number;
  realized_pnl: number;
  pnl_percent: number;
  opened_at: string;
  closed_at: string;
  close_reason?: string;
  open_run_id?: string;
  close_run_id?: string;
}

export interface LimitOrder {
  id: string;
  symbol: string;
  side: string;
  order_type: string;
  limit_price: number;
  margin_usdt: number;
  leverage: number;
  tp_price?: number;
  sl_price?: number;
  create_time: string;
  status: string;
  filled_time?: string;
  filled_price?: number;
  position_id?: string;
}
