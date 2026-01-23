import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Play, Square, RotateCcw, Clock } from 'lucide-react';
import type { ServiceInfo } from '../../../types';
import { controlService } from '../../../services/api';
import { Card, StatusBadge } from '../../../components/ui';

interface ServiceCardProps {
  service: ServiceInfo;
}

export function ServiceCard({ service }: ServiceCardProps) {
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: (action: 'start' | 'stop' | 'restart') =>
      controlService(service.name, action),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['systemStatus'] });
    },
  });

  const isLoading = mutation.isPending;
  const isRunning = service.status === 'running';
  const isStopped = service.status === 'stopped';

  const formatUptime = (startedAt: string | null) => {
    if (!startedAt) return '-';
    const start = new Date(startedAt);
    const now = new Date();
    const diff = Math.floor((now.getTime() - start.getTime()) / 1000);

    if (diff < 60) return `${diff}s`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ${Math.floor((diff % 3600) / 60)}m`;
    return `${Math.floor(diff / 86400)}d ${Math.floor((diff % 86400) / 3600)}h`;
  };

  return (
    <Card>
      <div className="flex items-start justify-between">
        <div className="space-y-2">
          <h4 className="text-base font-medium capitalize text-gray-100">
            {service.name.replace(/_/g, ' ')}
          </h4>
          <StatusBadge status={service.status} size="sm" />
          {isRunning && service.started_at && (
            <div className="flex items-center gap-1.5 text-xs text-gray-400">
              <Clock className="h-3 w-3" />
              <span>Uptime: {formatUptime(service.started_at)}</span>
            </div>
          )}
          {service.error && (
            <p className="text-xs text-red-400">{service.error}</p>
          )}
        </div>

        <div className="flex gap-1">
          <button
            onClick={() => mutation.mutate('start')}
            disabled={isLoading || isRunning}
            className="rounded-lg p-2 text-gray-400 transition-colors hover:bg-gray-700 hover:text-green-400 disabled:cursor-not-allowed disabled:opacity-50"
            title="Start"
          >
            <Play className="h-4 w-4" />
          </button>
          <button
            onClick={() => mutation.mutate('stop')}
            disabled={isLoading || isStopped}
            className="rounded-lg p-2 text-gray-400 transition-colors hover:bg-gray-700 hover:text-red-400 disabled:cursor-not-allowed disabled:opacity-50"
            title="Stop"
          >
            <Square className="h-4 w-4" />
          </button>
          <button
            onClick={() => mutation.mutate('restart')}
            disabled={isLoading || isStopped}
            className="rounded-lg p-2 text-gray-400 transition-colors hover:bg-gray-700 hover:text-yellow-400 disabled:cursor-not-allowed disabled:opacity-50"
            title="Restart"
          >
            <RotateCcw className="h-4 w-4" />
          </button>
        </div>
      </div>
    </Card>
  );
}
