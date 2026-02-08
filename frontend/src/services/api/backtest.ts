import { apiClient } from './client';

export interface BacktestStartRequest {
  symbols: string[];
  start_time: string;
  end_time: string;
  interval: string;
  initial_balance: number;
  concurrency: number;
  fixed_margin_usdt: number;
  fixed_leverage: number;
  reverse_mode: boolean;
}

export interface BacktestStartResponse {
  backtest_id: string;
  status: string;
  message: string;
}

export interface BacktestStatusResponse {
  backtest_id: string;
  status: string;
  progress?: {
    current_time: string;
    total_steps: number;
    completed_steps: number;
    progress_percent: number;
    current_step_info: string;
  };
  result?: BacktestResult;
}

export interface BacktestTradeResult {
  trade_id: string;
  kline_time: string;
  symbol: string;
  side: string;
  entry_price: number;
  exit_price: number;
  tp_price: number;
  sl_price: number;
  size: number;
  exit_time: string;
  exit_type: string;
  realized_pnl: number;
  pnl_percent: number;
  holding_bars: number;
  workflow_run_id: string;
  order_type?: string;
  margin_usdt?: number;
  leverage?: number;
  notional_usdt?: number;
  original_tp_price?: number;
  original_sl_price?: number;
  limit_price?: number;
  fees_total?: number;
  r_multiple?: number;
  tp_distance_percent?: number;
  sl_distance_percent?: number;
  close_reason?: string;
  order_created_time?: string;
}

export interface CancelledLimitOrder {
  order_id: string;
  symbol: string;
  side: string;
  limit_price: number;
  tp_price: number;
  sl_price: number;
  margin_usdt: number;
  leverage: number;
  created_time: string;
  cancelled_time: string;
  cancel_reason: string;
  workflow_run_id: string;
}

export interface BacktestResult {
  backtest_id: string;
  config: {
    symbols: string[];
    start_time: string;
    end_time: string;
    interval: string;
    initial_balance: number;
    concurrency: number;
    reverse_mode?: boolean;
  };
  status: string;
  start_timestamp: string;
  end_timestamp?: string;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  total_pnl: number;
  max_drawdown: number;
  final_balance: number;
  win_rate: number;
  return_rate: number;
  avg_win: number;
  avg_loss: number;
  profit_factor: number;
  total_klines_analyzed: number;
  completed_batches: number;
  total_batches: number;
  trades: BacktestTradeResult[];
  cancelled_orders: CancelledLimitOrder[];
  workflow_runs: string[];
  error_message?: string;
}

export interface BacktestListItem {
  backtest_id: string;
  status: string;
  config: {
    symbols: string[];
    start_time: string;
    end_time: string;
    interval: string;
    initial_balance: number;
    reverse_mode?: boolean;
  };
  start_timestamp: string;
  end_timestamp?: string;
  total_trades: number;
  total_pnl: number;
  win_rate: number;
}

export interface BacktestListResponse {
  backtests: BacktestListItem[];
  total: number;
}

export interface BacktestHistoryResponse {
  backtest_id: string;
  positions: Array<{
    symbol: string;
    side: string;
    entry_price: number;
    close_price: number;
    size: number;
    open_time: string;
    close_time: string;
    realized_pnl: number;
    close_reason?: string;
  }>;
  total: number;
  total_pnl: number;
}

export async function startBacktest(request: BacktestStartRequest): Promise<BacktestStartResponse> {
  const { data } = await apiClient.post('/backtest/start', request);
  return data;
}

export async function getBacktestStatus(backtestId: string): Promise<BacktestStatusResponse> {
  const { data } = await apiClient.get(`/backtest/${backtestId}/status`);
  return data;
}

export async function stopBacktest(backtestId: string): Promise<{ message: string }> {
  const { data } = await apiClient.post(`/backtest/${backtestId}/stop`);
  return data;
}

export async function listBacktests(limit = 20): Promise<BacktestListResponse> {
  const { data } = await apiClient.get('/backtest/list', { params: { limit } });
  return data;
}

export async function getBacktestHistory(
  backtestId: string,
  limit = 50
): Promise<BacktestHistoryResponse> {
  const { data } = await apiClient.get(`/backtest/${backtestId}/history`, { params: { limit } });
  return data;
}

export async function deleteBacktest(backtestId: string): Promise<{ message: string }> {
  const { data } = await apiClient.delete(`/backtest/${backtestId}`);
  return data;
}

export interface BacktestTradesResponse {
  backtest_id: string;
  trades: BacktestTradeResult[];
  cancelled_orders: CancelledLimitOrder[];
  total: number;
  stats: {
    total_trades: number;
    winning_trades: number;
    losing_trades: number;
    win_rate: number;
    profit_factor: number;
    avg_win: number;
    avg_loss: number;
    total_pnl: number;
  };
}

export interface BacktestTradesData {
  trades: BacktestTradeResult[];
  cancelledOrders: CancelledLimitOrder[];
}

export async function getBacktestTrades(
  backtestId: string,
  limit = 100
): Promise<BacktestTradesData> {
  const { data } = await apiClient.get<BacktestTradesResponse>(`/backtest/${backtestId}/trades`, { params: { limit } });
  return {
    trades: data.trades,
    cancelledOrders: data.cancelled_orders ?? [],
  };
}

export interface ConcurrencyInfo {
  backtest_id: string;
  current_running: number;
  max_concurrency: number;
  available: number;
}

export interface ConcurrencyUpdateResponse {
  success: boolean;
  backtest_id: string;
  max_concurrency: number;
  message: string;
}

export async function getConcurrency(backtestId: string): Promise<ConcurrencyInfo> {
  const { data } = await apiClient.get<ConcurrencyInfo>(`/backtest/${backtestId}/concurrency`);
  return data;
}

export async function setConcurrency(
  backtestId: string,
  maxConcurrency: number
): Promise<ConcurrencyUpdateResponse> {
  const { data } = await apiClient.put<ConcurrencyUpdateResponse>(
    `/backtest/${backtestId}/concurrency`,
    { max_concurrency: maxConcurrency }
  );
  return data;
}
