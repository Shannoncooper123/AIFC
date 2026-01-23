import { create } from 'zustand';
import type { AlertRecord, Position, PositionsSummary, ServiceInfo, WebSocketEvent } from '../types';

interface AppState {
  services: Record<string, ServiceInfo>;
  positions: Position[];
  positionsSummary: PositionsSummary | null;
  alerts: AlertRecord[];
  logs: string[];
  isConnected: boolean;
  
  setServices: (services: Record<string, ServiceInfo>) => void;
  updateService: (name: string, info: Partial<ServiceInfo>) => void;
  setPositions: (positions: Position[]) => void;
  setPositionsSummary: (summary: PositionsSummary) => void;
  setAlerts: (alerts: AlertRecord[]) => void;
  addAlert: (alert: AlertRecord) => void;
  addLog: (log: string) => void;
  clearLogs: () => void;
  setIsConnected: (connected: boolean) => void;
  handleWebSocketEvent: (event: WebSocketEvent) => void;
}

export const useAppStore = create<AppState>((set, get) => ({
  services: {},
  positions: [],
  positionsSummary: null,
  alerts: [],
  logs: [],
  isConnected: false,

  setServices: (services) => set({ services }),
  
  updateService: (name, info) =>
    set((state) => ({
      services: {
        ...state.services,
        [name]: { ...state.services[name], ...info },
      },
    })),

  setPositions: (positions) => set({ positions }),
  
  setPositionsSummary: (summary) => set({ positionsSummary: summary }),
  
  setAlerts: (alerts) => set({ alerts }),
  
  addAlert: (alert) =>
    set((state) => ({
      alerts: [alert, ...state.alerts].slice(0, 100),
    })),

  addLog: (log) =>
    set((state) => ({
      logs: [...state.logs, log].slice(-500),
    })),

  clearLogs: () => set({ logs: [] }),
  
  setIsConnected: (connected) => set({ isConnected: connected }),

  handleWebSocketEvent: (event) => {
    const { type, data } = event;
    
    switch (type) {
      case 'system_status':
      case 'monitor_status':
      case 'agent_status':
      case 'workflow_status': {
        const status = data.status as string;
        const service = data.service as string | undefined;
        const serviceName = service || type.replace('_status', '');
        get().updateService(serviceName, { status: status as ServiceInfo['status'] });
        break;
      }
      
      case 'new_alert': {
        const alertData = data as unknown as AlertRecord;
        get().addAlert(alertData);
        break;
      }
      
      case 'position_update': {
        break;
      }
      
      case 'log_message': {
        const message = data.message as string;
        const source = data.source as string;
        get().addLog(`[${source}] ${message}`);
        break;
      }
      
      case 'error': {
        const error = data.error as string;
        get().addLog(`[ERROR] ${error}`);
        break;
      }
    }
  },
}));
