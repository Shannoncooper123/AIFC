import type { ReactNode } from 'react';

interface PageHeaderProps {
  title: string;
  icon?: ReactNode;
  badge?: ReactNode;
  action?: ReactNode;
}

export function PageHeader({ title, icon, badge, action }: PageHeaderProps) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-3">
        {icon}
        <h1 className="text-2xl font-bold text-gray-100">{title}</h1>
        {badge}
      </div>
      {action}
    </div>
  );
}
