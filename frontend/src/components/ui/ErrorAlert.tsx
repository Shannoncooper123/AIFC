import { AlertCircle } from 'lucide-react';

interface ErrorAlertProps {
  message: string;
}

export function ErrorAlert({ message }: ErrorAlertProps) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-[#2a2a2a] bg-[#141414] p-4 text-neutral-300 animate-slide-up">
      <AlertCircle className="h-5 w-5 flex-shrink-0 text-neutral-500" />
      <span className="text-sm">{message}</span>
    </div>
  );
}
