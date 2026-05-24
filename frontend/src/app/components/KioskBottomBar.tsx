'use client';

import { unlockAudioForUserGesture } from '@/lib/audio/audio-interaction-manager';
import { cn } from '@/lib/cn';
import { overlayLabels } from '@/lib/kiosk-labels';
import type { KioskMicMode, KioskPhase } from '@/lib/kiosk-constants';
import { Camera, Mic, PenLine, Presentation, Sparkles } from 'lucide-react';
import { useEffect, useRef } from 'react';
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
  welcomeCooldownRemainingMs,
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
  welcomeCooldownRemainingMs: number;
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
  const isVoiceCaptureActive =
    kioskPhase === 'voice' &&
    ((voice.sessionState === 'listening' &&
      voice.loadingPhase !== 'llm' &&
      voice.loadingPhase !== 'tts') ||
      voice.loadingPhase === 'mic' ||
      voice.loadingPhase === 'stt');
  const controlsLocked = voice.uiLockState === 'locked';
  const controlsInterruptible = voice.uiLockState === 'interruptible';
  const welcomeDisabled = controlsLocked || welcomeCooldown;
  const nonWelcomeDisabled = controlsLocked;
  const isPushToTalk = micInputMode === 'push_to_talk';
  const pushToTalkPointerActiveRef = useRef(false);
  const voiceRestartSuppressedUntilRef = useRef(0);
  const voiceButtonLabel = isPushToTalk
    ? isVoiceCaptureActive
      ? labels.kioskVoicePushActive
      : labels.kioskVoicePushIdle
    : isVoiceCaptureActive
      ? labels.kioskVoiceToggleActive
      : labels.kioskVoice;

  const handleKioskVoiceStart = async () => {
    if (controlsLocked) {
      return;
    }
    if (voice.uiLockState === 'normal') {
      voiceRestartSuppressedUntilRef.current = 0;
    }
    if (Date.now() < voiceRestartSuppressedUntilRef.current) {
      return;
    }
    if (controlsInterruptible) {
      voice.cancelSession();
    }
    unlockAudioForUserGesture();
    clearReturnToIdleTimer();
    setWelcomeMemberOcrOpen(false);
    setKioskPhase('voice');
    setKioskVoiceLocked(true);
    const started = await voice.startListening();
    if (!started) {
      setKioskVoiceLocked(false);
    }
  };

  const handleKioskVoiceStop = () => {
    voiceRestartSuppressedUntilRef.current = Date.now() + 450;
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

  const interruptActiveVoiceTurn = () => {
    if (controlsInterruptible) {
      setKioskVoiceLocked(false);
      voice.cancelSession();
    }
  };

  useEffect(() => {
    if (voice.uiLockState === 'normal') {
      voiceRestartSuppressedUntilRef.current = 0;
    }
  }, [voice.uiLockState]);

  useEffect(() => {
    if (!kioskVoiceLocked || !voice.error || voice.uiLockState !== 'normal') {
      return;
    }

    setKioskVoiceLocked(false);
  }, [kioskVoiceLocked, setKioskVoiceLocked, voice.error, voice.uiLockState]);

  const statusEnabled =
    kioskPhase === 'voice' || kioskPhase === 'idle' || kioskPhase === 'notice';
  const cooldownRemainingSeconds = Math.max(0, Math.ceil(welcomeCooldownRemainingMs / 1000));
  const cooldownMinutes = Math.floor(cooldownRemainingSeconds / 60);
  const cooldownSeconds = cooldownRemainingSeconds % 60;
  const welcomeCooldownMessage = labels.welcomeCooldownRemaining
    .replace('{minutes}', String(cooldownMinutes))
    .replace('{seconds}', String(cooldownSeconds).padStart(2, '0'));

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
        {welcomeCooldown && welcomeCooldownRemainingMs > 0 ? (
          <div
            className="flex w-full items-center justify-center rounded-xl border border-amber-200/50 bg-amber-500/25 px-4 py-2 text-center text-sm font-semibold text-amber-50 shadow-sm backdrop-blur-sm"
            data-testid="kiosk-welcome-cooldown"
          >
            {welcomeCooldownMessage}
          </div>
        ) : null}
        <div className="flex w-full flex-row flex-wrap items-stretch justify-center gap-2 sm:gap-3">
          {showKioskScreenChrome && (
            <button
              type="button"
              onClick={() => {
                interruptActiveVoiceTurn();
                unlockAudioForUserGesture();
                void onPlayWelcome();
              }}
              disabled={welcomeDisabled}
              className={cn(
                'flex min-h-[72px] min-w-[min(100%,7rem)] flex-1 flex-col items-center justify-center gap-1 rounded-2xl px-3 py-3 shadow-md backdrop-blur-sm transition-transform sm:min-h-[80px] sm:flex-initial sm:px-5',
                welcomeDisabled
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
            onTouchStart={(event) => {
              if (isPushToTalk) {
                event.preventDefault();
              }
            }}
            onPointerDown={(event) => {
              if (!isPushToTalk) {
                return;
              }
              if (nonWelcomeDisabled && !isVoiceCaptureActive) {
                return;
              }
              event.preventDefault();
              event.currentTarget.setPointerCapture(event.pointerId);
              pushToTalkPointerActiveRef.current = true;
              if (!isVoiceCaptureActive) {
                void handleKioskVoiceStart();
              }
            }}
            onPointerUp={(event) => {
              if (!isPushToTalk) {
                return;
              }
              if (event.currentTarget.hasPointerCapture(event.pointerId)) {
                event.currentTarget.releasePointerCapture(event.pointerId);
              }
              if (pushToTalkPointerActiveRef.current) {
                pushToTalkPointerActiveRef.current = false;
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
              if (pushToTalkPointerActiveRef.current) {
                pushToTalkPointerActiveRef.current = false;
                handleKioskVoiceStop();
              }
            }}
            onClick={(event) => {
              if (isPushToTalk) {
                event.preventDefault();
                return;
              }
              if (nonWelcomeDisabled && !isVoiceCaptureActive) {
                return;
              }
              if (isVoiceCaptureActive) {
                handleKioskVoiceStop();
                return;
              }
              void handleKioskVoiceStart();
            }}
            disabled={nonWelcomeDisabled && !isVoiceCaptureActive}
            className={cn(
              'flex min-h-[72px] min-w-[min(100%,7rem)] flex-1 touch-manipulation select-none flex-col items-center justify-center gap-1 rounded-2xl px-3 py-3 shadow-md backdrop-blur-sm transition-transform [-webkit-touch-callout:none] sm:min-h-[80px] sm:flex-initial sm:px-5',
              isVoiceCaptureActive
                ? 'border border-emerald-300/70 bg-emerald-500/55 text-white shadow-lg'
                : nonWelcomeDisabled
                  ? 'cursor-not-allowed border border-slate-500/40 bg-slate-600/40 text-slate-300'
                  : 'border border-white/35 bg-white/15 text-white hover:scale-[1.02]',
            )}
          >
            <Mic
              className="pointer-events-none size-6 shrink-0 touch-manipulation select-none [-webkit-touch-callout:none] sm:size-7"
              aria-hidden
            />
            <span className="pointer-events-none touch-manipulation select-none text-center text-xs font-semibold leading-tight [-webkit-touch-callout:none] sm:text-sm">
              {voiceButtonLabel}
            </span>
          </button>
          <button
            type="button"
            onClick={() => {
              interruptActiveVoiceTurn();
              unlockAudioForUserGesture();
              setWelcomeMemberOcrOpen(false);
              setOcrMode('member_card');
              setKioskPhase('ocr');
            }}
            disabled={nonWelcomeDisabled}
            className={cn(
              'flex min-h-[72px] min-w-[min(100%,7rem)] flex-1 flex-col items-center justify-center gap-1 rounded-2xl px-3 py-3 shadow-md backdrop-blur-sm transition-transform sm:min-h-[80px] sm:flex-initial sm:px-5',
              nonWelcomeDisabled
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
              interruptActiveVoiceTurn();
              unlockAudioForUserGesture();
              setWelcomeMemberOcrOpen(false);
              setOcrMode('handwriting');
              setKioskPhase('ocr');
            }}
            disabled={nonWelcomeDisabled}
            className={cn(
              'flex min-h-[72px] min-w-[min(100%,7rem)] flex-1 flex-col items-center justify-center gap-1 rounded-2xl px-3 py-3 shadow-md backdrop-blur-sm transition-transform sm:min-h-[80px] sm:flex-initial sm:px-5',
              nonWelcomeDisabled
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
              interruptActiveVoiceTurn();
              unlockAudioForUserGesture();
              setWelcomeMemberOcrOpen(false);
              onStartPresentation();
            }}
            disabled={nonWelcomeDisabled}
            className={cn(
              'flex min-h-[72px] min-w-[min(100%,7rem)] flex-1 flex-col items-center justify-center gap-1 rounded-2xl px-3 py-3 shadow-md backdrop-blur-sm transition-transform sm:min-h-[80px] sm:flex-initial sm:px-5',
              nonWelcomeDisabled
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
