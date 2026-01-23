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
      className={`rounded-xl border border-[#1a1a1a] bg-[#0a0a0a] transition-all duration-300 hover:border-[#2a2a2a] animate-fade-in ${className}`}
    >
      {(title || headerAction) && (
        <div className="flex items-center justify-between border-b border-[#1a1a1a] px-4 py-3">
          {title && <h3 className="text-base font-medium text-white">{title}</h3>}
          {headerAction && <div>{headerAction}</div>}
        </div>
      )}
      <div className="p-4">{children}</div>
    </div>
  );
}
