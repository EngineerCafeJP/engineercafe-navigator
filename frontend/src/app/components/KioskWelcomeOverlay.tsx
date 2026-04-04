'use client';

import { overlayLabels } from '@/lib/kiosk-labels';
import type { KioskPhase } from '@/lib/kiosk-constants';
import { OcrCameraView } from '@/components/reception/OcrCameraView';
import type { OcrResponse } from '@/lib/api/ocr-api';

export function KioskWelcomeOverlay({
  open,
  welcomeMemberOcrSessionKey,
  kioskPhase,
  showSlideMode,
  labels,
  sessionId,
  bumpUserActivity,
  onMemberOcrSuccess,
  onMemberOcrEnd,
}: {
  open: boolean;
  welcomeMemberOcrSessionKey: number;
  kioskPhase: KioskPhase;
  showSlideMode: boolean;
  labels: (typeof overlayLabels)['ja'] | (typeof overlayLabels)['en'];
  sessionId: string;
  bumpUserActivity: () => void;
  onMemberOcrSuccess: (result: OcrResponse) => void;
  onMemberOcrEnd: () => void;
}) {
  if (!open || kioskPhase === 'ocr' || showSlideMode) {
    return null;
  }

  return (
    <div
      className="pointer-events-auto absolute z-[38] w-[min(92vw,13.5rem)] rounded-xl border border-white/25 bg-white/95 p-3 shadow-2xl backdrop-blur-md"
      style={{
        top: 'calc(max(1.5rem, env(safe-area-inset-top)) + 3.25rem)',
        right: 'max(1rem, env(safe-area-inset-right))',
      }}
      onPointerDownCapture={bumpUserActivity}
    >
      <p className="mb-2 text-center text-xs font-semibold text-slate-800">{labels.kioskOcrMember}</p>
      <OcrCameraView
        key={welcomeMemberOcrSessionKey}
        mode="member_card"
        autoStart
        compact
        hideSkip
        sessionId={sessionId}
        onSuccess={onMemberOcrSuccess}
        onFallback={onMemberOcrEnd}
        onSkip={onMemberOcrEnd}
        onCameraInitFailed={onMemberOcrEnd}
      />
    </div>
  );
}
