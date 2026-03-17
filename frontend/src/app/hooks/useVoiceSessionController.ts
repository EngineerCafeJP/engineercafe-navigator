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

export function useVoiceSessionController({
  enabled = true,
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
}: UseVoiceSessionControllerOptions = {}): UseVoiceSessionControllerResult {
  const hasDetectedSpeechRef = useRef(false);
  const onWakeWordRef = useRef(onWakeWord);

  useEffect(() => {
    onWakeWordRef.current = onWakeWord;
  }, [onWakeWord]);

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
    enabled: enabled && shouldArmWakeWord,
    language,
    continuous: wakeWordContinuous,
    interimResults: wakeWordInterimResults,
    restartDelayMs: wakeWordRestartDelayMs,
    debounceMs: wakeWordDebounceMs,
    onWakeWord: handleWakeWord,
  });

  const { levels: waveformBars, averageLevel } = useVoiceWaveform({
    stream,
    enabled: enabled && shouldListen,
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

    if (!isConversationActive) {
      startSession('manual');
    }

    hasDetectedSpeechRef.current = false;
    beginSpeaking();
  }, [beginSpeaking, enabled, isConversationActive, startSession]);

  const notifySpeakingComplete = useCallback(
    (skipAutoResume = false) => {
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
