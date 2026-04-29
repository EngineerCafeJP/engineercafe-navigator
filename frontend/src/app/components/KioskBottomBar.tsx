'use client';

import { markAudioUserInteraction } from '@/lib/audio/audio-user-interaction-gate';
import { cn } from '@/lib/cn';
import { overlayLabels } from '@/lib/kiosk-labels';
import type { KioskMicMode, KioskPhase } from '@/lib/kiosk-constants';
import { Camera, Mic, PenLine, Presentation, Sparkles } from 'lucide-react';
import { KioskVoiceStatusStack } from './KioskVoiceStatusStack';
import type { VoiceInterfaceRenderProps } from './VoiceInterface';

export function KioskBottomBar({
  kioskPhase,
  setKioskPhase,
  kioskVoiceLocked,
  setKioskVoiceLocked,
  micInputMode,
  showKioskScreenChrome,
  welcomeCooldown,
  labels,
  ocrStatus,
  voice,
  onPlayWelcome,
  onStartPresentation,
  clearReturnToIdleTimer,
  setWelcomeMemberOcrOpen,
  setOcrMode,
}: {
  kioskPhase: KioskPhase;
  setKioskPhase: (phase: KioskPhase | ((prev: KioskPhase) => KioskPhase)) => void;
  kioskVoiceLocked: boolean;
  setKioskVoiceLocked: (locked: boolean) => void;
  micInputMode: KioskMicMode;
  showKioskScreenChrome: boolean;
  welcomeCooldown: boolean;
  labels: (typeof overlayLabels)['ja'] | (typeof overlayLabels)['en'];
  ocrStatus: {
    kind: 'member_card' | 'handwriting' | 'error';
    text: string;
    visibleUntil: number;
  } | null;
  voice: VoiceInterfaceRenderProps;
  onPlayWelcome: () => void | Promise<void>;
  onStartPresentation: () => void;
  clearReturnToIdleTimer: () => void;
  setWelcomeMemberOcrOpen: (open: boolean) => void;
  setOcrMode: (mode: 'member_card' | 'handwriting') => void;
}) {
  const isVoiceCaptureActive = kioskPhase === 'voice' && kioskVoiceLocked;
  const isPushToTalk = micInputMode === 'push_to_talk';
  const voiceButtonLabel = isPushToTalk
    ? isVoiceCaptureActive
      ? labels.kioskVoicePushActive
      : labels.kioskVoicePushIdle
    : isVoiceCaptureActive
      ? labels.kioskVoiceToggleActive
      : labels.kioskVoice;

  const handleKioskVoiceStart = () => {
    markAudioUserInteraction();
    clearReturnToIdleTimer();
    setWelcomeMemberOcrOpen(false);
    setKioskPhase('voice');
    setKioskVoiceLocked(true);
    void voice.startListening();
  };

  const handleKioskVoiceStop = () => {
    setKioskVoiceLocked(false);
    if (isPushToTalk) {
      voice.stopListening();
      return;
    }
    if (voice.sessionState === 'listening') {
      voice.stopListening();
      return;
    }
    voice.cancelSession();
  };

  const statusEnabled =
    kioskPhase === 'voice' || kioskPhase === 'idle' || kioskPhase === 'notice';

  return (
    <div className="pointer-events-auto absolute inset-x-0 bottom-0 z-[25] flex justify-center pb-[max(0.75rem,env(safe-area-inset-bottom))] pl-[max(1rem,env(safe-area-inset-left))] pr-[max(1rem,env(safe-area-inset-right))] pt-2">
      <div className="flex w-full max-w-5xl flex-col items-stretch justify-center gap-2 sm:gap-3">
        <KioskVoiceStatusStack
          enabled={statusEnabled}
          phase={kioskPhase}
          labels={labels}
          transcript={voice.transcript}
          response={voice.response}
          error={voice.error}
          ocrStatus={ocrStatus}
          isLoading={voice.isLoading}
          loadingPhase={voice.loadingPhase}
          sessionState={voice.sessionState}
        />
        <div className="flex w-full flex-row flex-wrap items-stretch justify-center gap-2 sm:gap-3">
            {showKioskScreenChrome && (
            <button
              type="button"
              onClick={() => {
                void onPlayWelcome();
              }}
              disabled={isVoiceCaptureActive || voice.isLoading || welcomeCooldown}
              className={cn(
                'flex min-h-[72px] min-w-[min(100%,7rem)] flex-1 flex-col items-center justify-center gap-1 rounded-2xl px-3 py-3 shadow-md backdrop-blur-sm transition-transform sm:min-h-[80px] sm:flex-initial sm:px-5',
                isVoiceCaptureActive || voice.isLoading || welcomeCooldown
                  ? 'cursor-not-allowed border border-slate-500/40 bg-slate-600/40 text-slate-300'
                  : 'border border-white/35 bg-white/15 text-white hover:scale-[1.02]',
              )}
            >
              <Sparkles className="size-6 shrink-0 sm:size-7" aria-hidden />
              <span className="text-center text-xs font-semibold leading-tight sm:text-sm">
                {labels.kioskWelcome}
              </span>
            </button>
            )}
            <button
              data-testid="kiosk-voice-button"
              type="button"
              onPointerDown={(event) => {
                if (!isPushToTalk) {
                  return;
                }
                event.preventDefault();
                event.currentTarget.setPointerCapture(event.pointerId);
                if (!isVoiceCaptureActive) {
                  handleKioskVoiceStart();
                }
              }}
              onPointerUp={(event) => {
                if (!isPushToTalk) {
                  return;
                }
                if (event.currentTarget.hasPointerCapture(event.pointerId)) {
                  event.currentTarget.releasePointerCapture(event.pointerId);
                }
                if (isVoiceCaptureActive) {
                  handleKioskVoiceStop();
                }
              }}
              onPointerCancel={(event) => {
                if (!isPushToTalk) {
                  return;
                }
                if (event.currentTarget.hasPointerCapture(event.pointerId)) {
                  event.currentTarget.releasePointerCapture(event.pointerId);
                }
                if (isVoiceCaptureActive) {
                  handleKioskVoiceStop();
                }
              }}
              onClick={(event) => {
                if (isPushToTalk) {
                  event.preventDefault();
                  return;
                }
                if (isVoiceCaptureActive) {
                  handleKioskVoiceStop();
                  return;
                }
                handleKioskVoiceStart();
              }}
              className={cn(
                'flex min-h-[72px] min-w-[min(100%,7rem)] flex-1 flex-col items-center justify-center gap-1 rounded-2xl px-3 py-3 shadow-md backdrop-blur-sm transition-transform sm:min-h-[80px] sm:flex-initial sm:px-5',
                isVoiceCaptureActive
                  ? 'border border-emerald-300/70 bg-emerald-500/55 text-white shadow-lg'
                  : 'border border-white/35 bg-white/15 text-white hover:scale-[1.02]',
              )}
            >
              <Mic className="size-6 shrink-0 sm:size-7" aria-hidden />
              <span className="text-center text-xs font-semibold leading-tight sm:text-sm">
                {voiceButtonLabel}
              </span>
            </button>
            <button
              type="button"
              onClick={() => {
                markAudioUserInteraction();
                setWelcomeMemberOcrOpen(false);
                setOcrMode('member_card');
                setKioskPhase('ocr');
              }}
              disabled={isVoiceCaptureActive}
              className={cn(
                'flex min-h-[72px] min-w-[min(100%,7rem)] flex-1 flex-col items-center justify-center gap-1 rounded-2xl px-3 py-3 shadow-md backdrop-blur-sm transition-transform sm:min-h-[80px] sm:flex-initial sm:px-5',
                isVoiceCaptureActive
                  ? 'cursor-not-allowed border border-slate-500/40 bg-slate-600/40 text-slate-300'
                  : 'border border-white/35 bg-white/15 text-white hover:scale-[1.02]',
              )}
            >
              <Camera className="size-6 shrink-0 sm:size-7" aria-hidden />
              <span className="text-center text-xs font-semibold leading-tight sm:text-sm">
                {labels.kioskOcrMember}
              </span>
            </button>
            <button
              type="button"
              onClick={() => {
                markAudioUserInteraction();
                setWelcomeMemberOcrOpen(false);
                setOcrMode('handwriting');
                setKioskPhase('ocr');
              }}
              disabled={isVoiceCaptureActive}
              className={cn(
                'flex min-h-[72px] min-w-[min(100%,7rem)] flex-1 flex-col items-center justify-center gap-1 rounded-2xl px-3 py-3 shadow-md backdrop-blur-sm transition-transform sm:min-h-[80px] sm:flex-initial sm:px-5',
                isVoiceCaptureActive
                  ? 'cursor-not-allowed border border-slate-500/40 bg-slate-600/40 text-slate-300'
                  : 'border border-white/35 bg-white/15 text-white hover:scale-[1.02]',
              )}
            >
              <PenLine className="size-6 shrink-0 sm:size-7" aria-hidden />
              <span className="text-center text-xs font-semibold leading-tight sm:text-sm">
                {labels.kioskOcrHandwriting}
              </span>
            </button>
            <button
              data-testid="kiosk-slides-button"
              type="button"
              onClick={() => {
                markAudioUserInteraction();
                setWelcomeMemberOcrOpen(false);
                onStartPresentation();
              }}
              disabled={isVoiceCaptureActive}
              className={cn(
                'flex min-h-[72px] min-w-[min(100%,7rem)] flex-1 flex-col items-center justify-center gap-1 rounded-2xl px-3 py-3 shadow-md backdrop-blur-sm transition-transform sm:min-h-[80px] sm:flex-initial sm:px-5',
                isVoiceCaptureActive
                  ? 'cursor-not-allowed border border-slate-500/40 bg-slate-600/40 text-slate-300'
                  : 'border border-white/35 bg-white/15 text-white hover:scale-[1.02]',
              )}
            >
              <Presentation className="size-6 shrink-0 sm:size-7" aria-hidden />
              <span className="text-center text-xs font-semibold leading-tight sm:text-sm">
                {labels.kioskSlides}
              </span>
            </button>
          </div>
      </div>
    </div>
  );
}
