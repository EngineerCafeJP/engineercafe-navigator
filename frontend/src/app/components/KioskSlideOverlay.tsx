'use client';

import { overlayLabels } from '@/lib/kiosk-labels';
import { X } from 'lucide-react';
import type { CSSProperties } from 'react';
import ReceptionPdfGuide from './ReceptionPdfGuide';

type KioskSlideOverlayProps = {
  open: boolean;
  screenPadding: CSSProperties;
  labels: (typeof overlayLabels)['ja'] | (typeof overlayLabels)['en'];
  language: 'ja' | 'en';
  autoStartKey: number;
  sessionId: string;
  volume: number;
  onClose: () => void;
  onPointerActivity: () => void;
  onPresentationComplete: () => void;
  onVisemeControl?: ((viseme: string, intensity: number) => void) | null;
  onExpressionControl?: ((expression: string, weight: number) => void) | null;
};

export function KioskSlideOverlay({
  open,
  screenPadding,
  labels,
  language,
  autoStartKey,
  sessionId,
  volume,
  onClose,
  onPointerActivity,
  onPresentationComplete,
  onVisemeControl,
  onExpressionControl,
}: KioskSlideOverlayProps) {
  if (!open) {
    return null;
  }

  return (
    <div className="pointer-events-none absolute inset-0 z-50 flex h-full w-full flex-col" style={screenPadding}>
      <div
        className="pointer-events-auto relative flex h-full min-h-0 w-full flex-col overflow-hidden rounded-2xl bg-white/95 shadow-2xl transition-all duration-300 ease-out sm:rounded-[28px]"
        onPointerDownCapture={onPointerActivity}
      >
        <button
          type="button"
          onClick={onClose}
          aria-label={labels.closeSlides}
          className="absolute right-2 top-2 z-30 inline-flex size-9 items-center justify-center rounded-full bg-black/70 text-white shadow-lg transition-transform duration-200 ease-out hover:scale-105 sm:right-3 sm:top-3 sm:size-10"
        >
          <X className="size-4 sm:size-5" />
        </button>
        <ReceptionPdfGuide
          language={language}
          rotateLandscapeHint={labels.slideRotateHint}
          autoStartKey={autoStartKey}
          className="min-h-0 flex-1"
          sessionId={sessionId}
          onVisemeControl={onVisemeControl}
          onExpressionControl={onExpressionControl}
          volume={volume}
          onPresentationComplete={onPresentationComplete}
        />
      </div>
    </div>
  );
}
