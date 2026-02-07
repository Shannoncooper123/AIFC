/**
 * 通用类型定义
 */

export type ServiceStatus = 'stopped' | 'starting' | 'running' | 'stopping' | 'error';

export type EventType =
  | 'system_status'
  | 'monitor_status'
  | 'agent_status'
  | 'workflow_status'
  | 'new_alert'
  | 'position_update'
  | 'trade_executed'
  | 'mark_price_update'
  | 'config_updated'
  | 'log_message'
  | 'error';

export interface WebSocketEvent {
  type: EventType;
  data: Record<string, unknown>;
  timestamp: string;
}
