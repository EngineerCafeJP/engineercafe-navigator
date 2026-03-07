'use client';

import { cn } from '@/lib/cn';
import { Loader2 } from 'lucide-react';
import { useEffect, useState } from 'react';

interface ClarificationButtonsProps {
  options: string[];
  onSelect: (option: string) => Promise<void>;
}

export default function ClarificationButtons({
  options,
  onSelect,
}: ClarificationButtonsProps) {
  const [selectedOption, setSelectedOption] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    setSelectedOption(null);
    setIsSubmitting(false);
  }, [options]);

  if (options.length === 0 || selectedOption) {
    return null;
  }

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
      {options.map((option) => (
        <button
          key={option}
          type="button"
          onClick={() => {
            setSelectedOption(option);
            setIsSubmitting(true);
            void onSelect(option).finally(() => {
              setIsSubmitting(false);
            });
          }}
          disabled={isSubmitting}
          className={cn(
            'inline-flex min-h-11 items-center justify-center rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-800 shadow-sm transition-colors',
            'hover:bg-slate-50 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400',
          )}
        >
          {isSubmitting && selectedOption === option ? (
            <span className="inline-flex items-center gap-2">
              <Loader2 className="size-4 animate-spin" />
              {option}
            </span>
          ) : (
            option
          )}
        </button>
      ))}
    </div>
  );
}
