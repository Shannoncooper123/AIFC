import type { ReactNode } from 'react';

interface CardProps {
  title?: string;
  children: ReactNode;
  className?: string;
  headerAction?: ReactNode;
}

export function Card({ title, children, className = '', headerAction }: CardProps) {
  return (
    <div
      className={`rounded-xl border border-gray-700 bg-gray-800/50 backdrop-blur-sm ${className}`}
    >
      {(title || headerAction) && (
        <div className="flex items-center justify-between border-b border-gray-700 px-4 py-3">
          {title && <h3 className="text-lg font-semibold text-gray-100">{title}</h3>}
          {headerAction && <div>{headerAction}</div>}
        </div>
      )}
      <div className="p-4">{children}</div>
    </div>
  );
}
