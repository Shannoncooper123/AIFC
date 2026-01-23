import type { SelectHTMLAttributes } from 'react';

interface SelectOption {
  value: string | number;
  label: string;
}

interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'children'> {
  options: SelectOption[];
  label?: string;
  placeholder?: string;
}

export function Select({
  options,
  label,
  placeholder,
  className = '',
  id,
  ...props
}: SelectProps) {
  return (
    <div className="flex items-center gap-2">
      {label && (
        <label htmlFor={id} className="text-sm text-neutral-500">
          {label}
        </label>
      )}
      <select
        id={id}
        className={`rounded-lg border border-[#2a2a2a] bg-[#141414] px-3 py-1.5 text-sm text-neutral-200 transition-all duration-200 focus:border-[#3a3a3a] focus:outline-none focus:ring-1 focus:ring-[#3a3a3a] hover:border-[#3a3a3a] ${className}`}
        {...props}
      >
        {placeholder && (
          <option value="">{placeholder}</option>
        )}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}
