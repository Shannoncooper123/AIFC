import type { ServiceStatus } from '../../types';

interface StatusBadgeProps {
  status: ServiceStatus;
  size?: 'sm' | 'md' | 'lg';
}

const sizeClasses = {
  sm: 'px-2 py-0.5 text-xs',
  md: 'px-2.5 py-1 text-sm',
  lg: 'px-3 py-1.5 text-base',
};

const statusConfig: Record<ServiceStatus, { label: string; dotClass: string; textClass: string; bgClass: string }> = {
  stopped: {
    label: 'Stopped',
    dotClass: 'bg-neutral-500',
    textClass: 'text-neutral-400',
    bgClass: 'bg-neutral-500/10',
  },
  starting: {
    label: 'Starting',
    dotClass: 'bg-neutral-400 animate-pulse-subtle',
    textClass: 'text-neutral-300',
    bgClass: 'bg-neutral-400/10',
  },
  running: {
    label: 'Running',
    dotClass: 'bg-white animate-pulse-subtle',
    textClass: 'text-white',
    bgClass: 'bg-white/10',
  },
  stopping: {
    label: 'Stopping',
    dotClass: 'bg-neutral-400 animate-pulse-subtle',
    textClass: 'text-neutral-300',
    bgClass: 'bg-neutral-400/10',
  },
  error: {
    label: 'Error',
    dotClass: 'bg-neutral-400',
    textClass: 'text-neutral-400',
    bgClass: 'bg-neutral-500/10',
  },
};

export function StatusBadge({ status, size = 'md' }: StatusBadgeProps) {
  const config = statusConfig[status];

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-medium border border-[#2a2a2a] ${config.bgClass} ${config.textClass} ${sizeClasses[size]}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${config.dotClass}`} />
      {config.label}
    </span>
  );
}
