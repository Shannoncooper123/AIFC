import type { ServiceStatus } from '../../types';
import { SERVICE_STATUS_CONFIG } from '../../utils';

interface StatusBadgeProps {
  status: ServiceStatus;
  size?: 'sm' | 'md' | 'lg';
}

const sizeClasses = {
  sm: 'px-2 py-0.5 text-xs',
  md: 'px-2.5 py-1 text-sm',
  lg: 'px-3 py-1.5 text-base',
};

export function StatusBadge({ status, size = 'md' }: StatusBadgeProps) {
  const config = SERVICE_STATUS_CONFIG[status];

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-medium ${config.bgColor} ${config.color} ${sizeClasses[size]}`}
    >
      <span
        className={`h-2 w-2 rounded-full ${
          status === 'running'
            ? 'animate-pulse bg-green-400'
            : status === 'starting' || status === 'stopping'
            ? 'animate-pulse bg-yellow-400'
            : status === 'error'
            ? 'bg-red-400'
            : 'bg-gray-400'
        }`}
      />
      {config.label}
    </span>
  );
}
