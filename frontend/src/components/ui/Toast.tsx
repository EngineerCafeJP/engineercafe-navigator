'use client';

import { X } from 'lucide-react';
import { useEffect } from 'react';

interface ToastProps {
  open: boolean;
  message: string;
  actionLabel?: string;
  durationMs?: number;
  onAction?: () => void;
  onDismiss: () => void;
}

export default function Toast({
  open,
  message,
  actionLabel,
  durationMs = 5_000,
  onAction,
  onDismiss,
}: ToastProps) {
  useEffect(() => {
    if (!open || durationMs <= 0) {
      return;
    }

    const timer = window.setTimeout(onDismiss, durationMs);
    return () => window.clearTimeout(timer);
  }, [durationMs, onDismiss, open]);

  if (!open) {
    return null;
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className="pointer-events-auto fixed bottom-5 left-1/2 z-[60] flex w-[calc(100%-2rem)] max-w-md -translate-x-1/2 items-center gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 shadow-lg"
      data-testid="audio-interaction-toast"
    >
      <button
        type="button"
        onClick={onAction}
        className="min-w-0 flex-1 text-left font-medium leading-5"
        data-testid="audio-interaction-toast-action"
      >
        {message}
        {actionLabel && <span className="ml-2 text-blue-700">{actionLabel}</span>}
      </button>
      <button
        type="button"
        onClick={onDismiss}
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900"
        aria-label="Dismiss audio notice"
      >
        <X size={18} aria-hidden="true" />
      </button>
    </div>
  );
}
