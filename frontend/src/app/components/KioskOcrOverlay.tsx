'use client';

import { overlayLabels } from '@/lib/kiosk-labels';
import { OcrCameraView } from '@/components/reception/OcrCameraView';
import type { OcrResponse } from '@/lib/api/ocr-api';

export function KioskOcrOverlay({
  visible,
  ocrMode,
  labels,
  sessionId,
  bumpUserActivity,
  onSuccess,
  onFallback,
  onSkip,
  onBackToIdle,
}: {
  visible: boolean;
  ocrMode: 'member_card' | 'handwriting';
  labels: (typeof overlayLabels)['ja'] | (typeof overlayLabels)['en'];
  sessionId: string;
  bumpUserActivity: () => void;
  onSuccess: (result: OcrResponse) => void;
  onFallback: () => void;
  onSkip: () => void;
  onBackToIdle: () => void;
}) {
  if (!visible) {
    return null;
  }

  return (
    <div
      data-testid="kiosk-ocr-overlay"
      className="absolute inset-0 z-40 grid min-h-0 place-items-center overflow-y-auto bg-black/60"
      style={{
        paddingTop: 'max(1rem, env(safe-area-inset-top))',
        paddingRight: 'max(1rem, env(safe-area-inset-right))',
        paddingBottom: 'max(1rem, env(safe-area-inset-bottom))',
        paddingLeft: 'max(1rem, env(safe-area-inset-left))',
      }}
      onPointerDownCapture={bumpUserActivity}
    >
      <div className="mx-auto max-h-full w-full max-w-lg overflow-y-auto rounded-[28px] border border-white/15 bg-white/95 p-5 shadow-xl md:p-8">
        <h3
          data-testid="kiosk-ocr-overlay-title"
          className="mb-4 text-center text-lg font-semibold text-slate-900"
        >
          {ocrMode === 'member_card' ? labels.kioskOcrMember : labels.kioskOcrHandwriting}
        </h3>
        <OcrCameraView
          key={ocrMode}
          mode={ocrMode}
          autoStart
          sessionId={sessionId}
          onSuccess={onSuccess}
          onFallback={onFallback}
          onSkip={onSkip}
        />
        <div className="mt-6 flex justify-center">
          <button
            type="button"
            onClick={onBackToIdle}
            className="inline-flex min-h-11 items-center justify-center rounded-full bg-slate-900 px-6 py-3 text-sm font-medium text-white transition-colors hover:bg-slate-800"
          >
            {labels.kioskBackIdle}
          </button>
        </div>
      </div>
    </div>
  );
}
