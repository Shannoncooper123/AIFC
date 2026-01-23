interface LoadingProps {
  size?: 'sm' | 'md' | 'lg';
  text?: string;
}

const sizeClasses = {
  sm: 'h-4 w-4',
  md: 'h-6 w-6',
  lg: 'h-8 w-8',
};

export function Loading({ size = 'md', text }: LoadingProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-8 animate-fade-in">
      <div
        className={`animate-spin rounded-full border-2 border-[#2a2a2a] border-t-white ${sizeClasses[size]}`}
      />
      {text && <span className="text-sm text-neutral-500">{text}</span>}
    </div>
  );
}
