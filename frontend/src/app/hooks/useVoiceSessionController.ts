'use client';

import { useCallback, useEffect, useMemo, useRef } from 'react';
import {
  useContinuousListening,
  type ContinuousListeningEndReason,
  type ContinuousListeningMode,
  type ContinuousListeningStartSource,
} from './useContinuousListening';
import { useSilenceDetection } from './useSilenceDetection';
import { useVoiceWaveform } from './useVoiceWaveform';
import { useWakeWord, type WakeWordMatch } from './useWakeWord';

export type VoiceCharacterState = 'idle' | 'listening' | 'thinking' | 'speaking';

export interface UseVoiceSessionControllerOptions {
  enabled?: boolean;
  /** When false, wake-word listening is disabled (no Web Speech mic while idle). */
  wakeWordEnabled?: boolean;
  stream?: MediaStream | null;
  wakeWords?: string[];
  language?: string;
  wakeWordContinuous?: boolean;
  wakeWordInterimResults?: boolean;
  wakeWordRestartDelayMs?: number;
  wakeWordDebounceMs?: number;
  silenceTimeoutMs?: number;
  silenceCheckIntervalMs?: number;
  silenceLevelThreshold?: number;
  waveformBarCount?: number;
  waveformFftSize?: number;
  waveformSmoothingTimeConstant?: number;
  autoResumeDelayMs?: number;
  onWakeWord?: (match: WakeWordMatch) => void;
  onSessionStart?: (source: ContinuousListeningStartSource) => void;
  onSessionEnd?: (reason: ContinuousListeningEndReason) => void;
  onThinkingWatchdogExpire?: () => void;
  onStateTransition?: (transition: {
    from: ContinuousListeningMode;
    to: ContinuousListeningMode;
    characterState: VoiceCharacterState;
    isConversationActive: boolean;
    shouldListen: boolean;
  }) => void;
}

export interface UseVoiceSessionControllerResult {
  mode: ContinuousListeningMode;
  characterState: VoiceCharacterState;
  isConversationActive: boolean;
  shouldListen: boolean;
  shouldArmWakeWord: boolean;
  waveformBars: number[];
  startManualSession: () => void;
  endManualSession: () => void;
  notifyProcessing: () => void;
  notifySpeaking: () => void;
  notifySpeakingComplete: (skipAutoResume?: boolean) => void;
  isWakeWordSupported: boolean;
  isWakeWordListening: boolean;
  wakeWordError: string | null;
  lastWakeWordMatch: WakeWordMatch | null;
}

const DEFAULT_WAKE_WORDS = ['すみません', 'hello'];
export const VOICE_SESSION_THINKING_WATCHDOG_MS = 5000;

const logVoiceSessionDebug = (message: string, details: Record<string, unknown>): void => {
  if (process.env.NODE_ENV === 'production') {
    return;
  }

  console.debug(`[VoiceSessionController] ${message}`, details);
};

export function useVoiceSessionController({
  enabled = true,
  wakeWordEnabled = true,
  stream = null,
  wakeWords = DEFAULT_WAKE_WORDS,
  language = 'ja-JP',
  wakeWordContinuous = true,
  wakeWordInterimResults = true,
  wakeWordRestartDelayMs,
  wakeWordDebounceMs,
  silenceTimeoutMs,
  silenceCheckIntervalMs,
  silenceLevelThreshold,
  waveformBarCount,
  waveformFftSize,
  waveformSmoothingTimeConstant,
  autoResumeDelayMs,
  onWakeWord,
  onSessionStart,
  onSessionEnd,
  onThinkingWatchdogExpire,
  onStateTransition,
}: UseVoiceSessionControllerOptions = {}): UseVoiceSessionControllerResult {
  const hasDetectedSpeechRef = useRef(false);
  const onWakeWordRef = useRef(onWakeWord);
  const onThinkingWatchdogExpireRef = useRef(onThinkingWatchdogExpire);
  const onStateTransitionRef = useRef(onStateTransition);
  const previousModeRef = useRef<ContinuousListeningMode | null>(null);
  const thinkingWatchdogRef = useRef<number | null>(null);

  useEffect(() => {
    onWakeWordRef.current = onWakeWord;
  }, [onWakeWord]);

  useEffect(() => {
    onThinkingWatchdogExpireRef.current = onThinkingWatchdogExpire;
  }, [onThinkingWatchdogExpire]);

  useEffect(() => {
    onStateTransitionRef.current = onStateTransition;
  }, [onStateTransition]);

  const clearThinkingWatchdog = useCallback(() => {
    if (thinkingWatchdogRef.current !== null) {
      window.clearTimeout(thinkingWatchdogRef.current);
      thinkingWatchdogRef.current = null;
    }
  }, []);

  const {
    mode,
    isConversationActive,
    shouldListen,
    shouldArmWakeWord,
    startSession,
    endSession,
    beginListening,
    beginProcessing,
    beginSpeaking,
    completeAssistantTurn,
  } = useContinuousListening({
    enabled,
    autoResumeDelayMs,
    onSessionStart,
    onSessionEnd,
  });

  const silenceEnabled = enabled && isConversationActive && mode === 'listening';

  useEffect(() => {
    const previousMode = previousModeRef.current;
    previousModeRef.current = mode;

    if (previousMode === null || previousMode === mode) {
      return;
    }

    const nextCharacterState: VoiceCharacterState =
      mode === 'processing' ? 'thinking' : mode === 'wake-word' ? 'idle' : mode;
    const transition = {
      from: previousMode,
      to: mode,
      characterState: nextCharacterState,
      isConversationActive,
      shouldListen,
    };

    logVoiceSessionDebug('state transition', transition);
    onStateTransitionRef.current?.(transition);
  }, [isConversationActive, mode, shouldListen]);

  useEffect(() => {
    clearThinkingWatchdog();

    if (!enabled || mode !== 'processing') {
      return;
    }

    logVoiceSessionDebug('thinking watchdog armed', {
      timeoutMs: VOICE_SESSION_THINKING_WATCHDOG_MS,
    });

    thinkingWatchdogRef.current = window.setTimeout(() => {
      thinkingWatchdogRef.current = null;
      hasDetectedSpeechRef.current = false;
      logVoiceSessionDebug('thinking watchdog expired', {
        timeoutMs: VOICE_SESSION_THINKING_WATCHDOG_MS,
      });
      onThinkingWatchdogExpireRef.current?.();
      completeAssistantTurn(true);
    }, VOICE_SESSION_THINKING_WATCHDOG_MS);

    return clearThinkingWatchdog;
  }, [clearThinkingWatchdog, completeAssistantTurn, enabled, mode]);

  const handleWakeWord = useCallback(
    (match: WakeWordMatch) => {
      if (!enabled || isConversationActive) {
        return;
      }

      hasDetectedSpeechRef.current = false;
      startSession('wake-word');
      onWakeWordRef.current?.(match);
    },
    [enabled, isConversationActive, startSession],
  );

  const {
    isSupported: isWakeWordSupported,
    isListening: isWakeWordListening,
    error: wakeWordError,
    detectedWakeWord: lastWakeWordMatch,
  } = useWakeWord({
    wakeWords,
    enabled: enabled && shouldArmWakeWord && wakeWordEnabled,
    language,
    continuous: wakeWordContinuous,
    interimResults: wakeWordInterimResults,
    restartDelayMs: wakeWordRestartDelayMs,
    debounceMs: wakeWordDebounceMs,
    onWakeWord: handleWakeWord,
  });

  // Only wire the mic stream into Web Audio while actively listening; keeping a stale
  // MediaStream here can leave Chrome's mic indicator on after tracks should have stopped.
  const waveformStream = enabled && shouldListen && stream ? stream : null;

  const { levels: waveformBars, averageLevel } = useVoiceWaveform({
    stream: waveformStream,
    enabled: Boolean(waveformStream),
    barCount: waveformBarCount,
    fftSize: waveformFftSize,
    smoothingTimeConstant: waveformSmoothingTimeConstant,
  });

  const { markAudioLevel, resetSilenceTimer } = useSilenceDetection({
    enabled: silenceEnabled,
    timeoutMs: silenceTimeoutMs,
    checkIntervalMs: silenceCheckIntervalMs,
    levelThreshold: silenceLevelThreshold,
    onSilence: () => {
      if (hasDetectedSpeechRef.current) {
        hasDetectedSpeechRef.current = false;
        beginProcessing();
        return;
      }

      endSession('silence');
    },
  });

  useEffect(() => {
    if (mode !== 'listening') {
      hasDetectedSpeechRef.current = false;
      return;
    }

    resetSilenceTimer();
  }, [mode, resetSilenceTimer]);

  useEffect(() => {
    if (!silenceEnabled) {
      return;
    }

    if (!markAudioLevel(averageLevel)) {
      return;
    }

    hasDetectedSpeechRef.current = true;
  }, [averageLevel, markAudioLevel, silenceEnabled]);

  const startManualSession = useCallback(() => {
    if (!enabled) {
      return;
    }

    hasDetectedSpeechRef.current = false;

    if (isConversationActive) {
      beginListening();
      return;
    }

    startSession('button');
  }, [beginListening, enabled, isConversationActive, startSession]);

  const endManualSession = useCallback(() => {
    hasDetectedSpeechRef.current = false;
    endSession('manual');
  }, [endSession]);

  const notifyProcessing = useCallback(() => {
    if (!enabled) {
      return;
    }

    logVoiceSessionDebug('notify processing', {
      isConversationActive,
    });

    if (!isConversationActive) {
      startSession('manual');
    }

    hasDetectedSpeechRef.current = false;
    beginProcessing();
  }, [beginProcessing, enabled, isConversationActive, startSession]);

  const notifySpeaking = useCallback(() => {
    if (!enabled) {
      return;
    }

    logVoiceSessionDebug('notify speaking', {
      isConversationActive,
    });

    if (!isConversationActive) {
      startSession('manual');
    }

    hasDetectedSpeechRef.current = false;
    beginSpeaking();
  }, [beginSpeaking, enabled, isConversationActive, startSession]);

  const notifySpeakingComplete = useCallback(
    (skipAutoResume = false) => {
      logVoiceSessionDebug('notify speaking complete', {
        skipAutoResume,
      });
      hasDetectedSpeechRef.current = false;
      completeAssistantTurn(skipAutoResume);
    },
    [completeAssistantTurn],
  );

  const characterState = useMemo<VoiceCharacterState>(() => {
    if (mode === 'listening') {
      return 'listening';
    }

    if (mode === 'processing') {
      return 'thinking';
    }

    if (mode === 'speaking') {
      return 'speaking';
    }

    return 'idle';
  }, [mode]);

  return useMemo(
    () => ({
      mode,
      characterState,
      isConversationActive,
      shouldListen,
      shouldArmWakeWord,
      waveformBars,
      startManualSession,
      endManualSession,
      notifyProcessing,
      notifySpeaking,
      notifySpeakingComplete,
      isWakeWordSupported,
      isWakeWordListening,
      wakeWordError,
      lastWakeWordMatch,
    }),
    [
      characterState,
      endManualSession,
      isConversationActive,
      isWakeWordListening,
      isWakeWordSupported,
      lastWakeWordMatch,
      mode,
      notifyProcessing,
      notifySpeaking,
      notifySpeakingComplete,
      shouldArmWakeWord,
      shouldListen,
      startManualSession,
      wakeWordError,
      waveformBars,
    ],
  );
}
