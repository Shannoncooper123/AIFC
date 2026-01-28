import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, useEffect, useCallback } from 'react';
import {
  startBacktest,
  getBacktestStatus,
  stopBacktest,
  listBacktests,
  getBacktestHistory,
  getBacktestTrades,
  deleteBacktest,
  getConcurrency,
  setConcurrency,
} from '../../../services/api/backtest';
import type { BacktestStartRequest, BacktestResult } from '../../../services/api/backtest';

export function useBacktestList(limit = 20) {
  return useQuery({
    queryKey: ['backtests', limit],
    queryFn: () => listBacktests(limit),
    refetchInterval: 5000,
  });
}

export function useBacktestStatus(backtestId: string | null) {
  return useQuery({
    queryKey: ['backtest', backtestId, 'status'],
    queryFn: () => (backtestId ? getBacktestStatus(backtestId) : null),
    enabled: !!backtestId,
    refetchInterval: (query) => {
      if (query.state.data?.status === 'running') return 2000;
      return false;
    },
  });
}

export function useBacktestHistory(backtestId: string | null, limit = 50) {
  return useQuery({
    queryKey: ['backtest', backtestId, 'history', limit],
    queryFn: () => (backtestId ? getBacktestHistory(backtestId, limit) : null),
    enabled: !!backtestId,
  });
}

export function useStartBacktest() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: BacktestStartRequest) => startBacktest(request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['backtests'] });
    },
  });
}

export function useStopBacktest() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (backtestId: string) => stopBacktest(backtestId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['backtests'] });
    },
  });
}

export function useDeleteBacktest() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (backtestId: string) => deleteBacktest(backtestId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['backtests'] });
    },
  });
}

export function useBacktestTrades(backtestId: string | null, limit = 100, isRunning = false) {
  return useQuery({
    queryKey: ['backtest', backtestId, 'trades', limit],
    queryFn: () => (backtestId ? getBacktestTrades(backtestId, limit) : []),
    enabled: !!backtestId,
    refetchInterval: isRunning ? 5000 : false,
  });
}

interface BacktestProgress {
  current_time: string;
  total_steps: number;
  completed_steps: number;
  progress_percent: number;
  current_step_info: string;
  current_running?: number;
  max_concurrency?: number;
}

export function useBacktestWebSocket(backtestId: string | null) {
  const [progress, setProgress] = useState<BacktestProgress | null>(null);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    if (!backtestId) {
      setProgress(null);
      setResult(null);
      return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/backtest/ws/${backtestId}`;
    
    let ws: WebSocket | null = null;
    let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        setIsConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'complete') {
            setResult(data.result);
          } else if (data.type === 'ping') {
          } else {
            setProgress(data);
          }
        } catch (e) {
          console.error('Failed to parse WebSocket message:', e);
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
        reconnectTimeout = setTimeout(connect, 3000);
      };

      ws.onerror = () => {
        ws?.close();
      };
    };

    connect();

    return () => {
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
      }
      if (ws) {
        ws.close();
      }
    };
  }, [backtestId]);

  return { progress, result, isConnected };
}

export function useBacktestConcurrency(backtestId: string | null, isRunning = false) {
  const [isUpdating, setIsUpdating] = useState(false);

  const { data: concurrencyInfo, refetch } = useQuery({
    queryKey: ['backtest', backtestId, 'concurrency'],
    queryFn: () => (backtestId ? getConcurrency(backtestId) : null),
    enabled: !!backtestId && isRunning,
    refetchInterval: isRunning ? 2000 : false,
  });

  const updateConcurrency = useCallback(
    async (newMax: number) => {
      if (!backtestId || isUpdating) return false;

      setIsUpdating(true);
      try {
        await setConcurrency(backtestId, newMax);
        await refetch();
        return true;
      } catch (error) {
        console.error('Failed to update concurrency:', error);
        return false;
      } finally {
        setIsUpdating(false);
      }
    },
    [backtestId, isUpdating, refetch]
  );

  return {
    currentRunning: concurrencyInfo?.current_running ?? 0,
    maxConcurrency: concurrencyInfo?.max_concurrency ?? 0,
    available: concurrencyInfo?.available ?? 0,
    isUpdating,
    updateConcurrency,
  };
}
