import type { ReactNode } from 'react';

interface PageHeaderProps {
  title: string;
  icon?: ReactNode;
  badge?: ReactNode;
  action?: ReactNode;
}

export function PageHeader({ title, icon, badge, action }: PageHeaderProps) {
  return (
    <div className="flex items-center justify-between animate-slide-up">
      <div className="flex items-center gap-3">
        {icon && <span className="text-neutral-500">{icon}</span>}
        <h1 className="text-xl font-semibold tracking-tight text-white">{title}</h1>
        {badge}
      </div>
      {action}
    </div>
  );
}
