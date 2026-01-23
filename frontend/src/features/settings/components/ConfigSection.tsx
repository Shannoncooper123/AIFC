/**
 * 可展开的配置节组件
 */
import type { ReactNode } from 'react';

interface ConfigSectionProps {
  name: string;
  isExpanded: boolean;
  onToggle: () => void;
  children?: ReactNode;
}

/**
 * 可展开的配置节组件，用于显示配置分组
 */
export function ConfigSection({
  name,
  isExpanded,
  onToggle,
  children,
}: ConfigSectionProps) {
  const displayName = name.replace(/_/g, ' ');

  return (
    <>
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between text-left transition-all duration-200"
      >
        <h3 className="text-lg font-semibold text-white capitalize">
          {displayName}
        </h3>
        <span className="text-neutral-400">{isExpanded ? '−' : '+'}</span>
      </button>

      {isExpanded && children}
    </>
  );
}
