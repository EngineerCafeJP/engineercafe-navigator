'use client';

import { Check } from 'lucide-react';

import { cn } from '@/lib/cn';
import type { ReceptionStage } from '@/lib/reception-api';

const STAGES = [
  { key: 'welcome', label: 'Welcome' },
  { key: 'greeting', label: 'Greeting' },
  { key: 'purpose_hearing', label: 'Purpose' },
  { key: 'routing', label: 'Routing' },
  { key: 'completed', label: 'Complete' },
] as const;

/** Maps any stage to the corresponding index in the STAGES array. */
function resolveActiveIndex(currentStage: ReceptionStage): number {
  if (currentStage === 'idle') return -1;
  // camera_ocr and text_input are sub-states of welcome
  if (currentStage === 'camera_ocr' || currentStage === 'text_input') return 0;
  return STAGES.findIndex((s) => s.key === currentStage);
}

interface StageIndicatorProps {
  currentStage: ReceptionStage;
}

export function StageIndicator({ currentStage }: StageIndicatorProps) {
  const activeIndex = resolveActiveIndex(currentStage);

  return (
    <ol className="flex items-start gap-3" aria-label="Reception progress">
      {STAGES.map((stage, index) => {
        const isCompleted = activeIndex > index;
        const isCurrent = activeIndex === index;

        return (
          <li key={stage.key} className="flex min-w-0 flex-1 items-start gap-3">
            <div className="flex flex-col items-center gap-2">
              <div
                className={cn(
                  'flex size-8 items-center justify-center rounded-full border text-sm font-semibold',
                  isCompleted && 'border-emerald-600 bg-emerald-600 text-white',
                  isCurrent && 'border-slate-900 bg-slate-900 text-white',
                  !isCompleted && !isCurrent && 'border-slate-300 bg-white text-slate-400',
                )}
              >
                {isCompleted ? <Check className="size-4" aria-hidden="true" /> : index + 1}
              </div>
              <span
                className={cn(
                  'text-center text-xs font-medium',
                  isCompleted || isCurrent ? 'text-slate-900' : 'text-slate-400',
                )}
              >
                {stage.label}
              </span>
            </div>
            {index < STAGES.length - 1 && (
              <div
                className={cn(
                  'mt-4 h-px flex-1',
                  activeIndex > index ? 'bg-emerald-600' : 'bg-slate-200',
                )}
                aria-hidden="true"
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}
