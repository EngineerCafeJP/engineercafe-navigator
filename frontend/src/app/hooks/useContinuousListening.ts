'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

export type ContinuousListeningMode =
  | 'idle'
  | 'wake-word'
  | 'listening'
  | 'processing'
  | 'speaking';

export type ContinuousListeningStartSource = 'manual' | 'wake-word' | 'button';
export type ContinuousListeningEndReason = 'manual' | 'silence' | 'error';

export interface UseContinuousListeningOptions {
  enabled?: boolean;
  autoResumeDelayMs?: number;
  onSessionStart?: (source: ContinuousListeningStartSource) => void;
  onSessionEnd?: (reason: ContinuousListeningEndReason) => void;
  onListeningChange?: (shouldListen: boolean) => void;
}

export interface UseContinuousListeningResult {
  mode: ContinuousListeningMode;
  isConversationActive: boolean;
  shouldListen: boolean;
  shouldArmWakeWord: boolean;
  turnCount: number;
  sessionStartedAt: number | null;
  startSession: (source?: ContinuousListeningStartSource) => void;
  endSession: (reason?: ContinuousListeningEndReason) => void;
  beginListening: () => void;
  beginProcessing: () => void;
  beginSpeaking: () => void;
  completeAssistantTurn: () => void;
  pauseListening: () => void;
  resumeListening: () => void;
}

const DEFAULT_AUTO_RESUME_DELAY_MS = 800;

export function useContinuousListening({
  enabled = true,
  autoResumeDelayMs = DEFAULT_AUTO_RESUME_DELAY_MS,
  onSessionStart,
  onSessionEnd,
  onListeningChange,
}: UseContinuousListeningOptions = {}): UseContinuousListeningResult {
  const resumeTimerRef = useRef<number | null>(null);

  const [mode, setMode] = useState<ContinuousListeningMode>(
    enabled ? 'wake-word' : 'idle',
  );
  const [isConversationActive, setIsConversationActive] = useState(false);
  const [shouldListen, setShouldListen] = useState(false);
  const [turnCount, setTurnCount] = useState(0);
  const [sessionStartedAt, setSessionStartedAt] = useState<number | null>(null);

  const updateShouldListen = useCallback(
    (value: boolean) => {
      setShouldListen(value);
      onListeningChange?.(value);
    },
    [onListeningChange],
  );

  const clearResumeTimer = useCallback(() => {
    if (resumeTimerRef.current !== null) {
      window.clearTimeout(resumeTimerRef.current);
      resumeTimerRef.current = null;
    }
  }, []);

  const startSession = useCallback(
    (source: ContinuousListeningStartSource = 'manual') => {
      clearResumeTimer();
      setIsConversationActive(true);
      setSessionStartedAt(Date.now());
      setTurnCount(0);
      setMode('listening');
      updateShouldListen(true);
      onSessionStart?.(source);
    },
    [clearResumeTimer, onSessionStart, updateShouldListen],
  );

  const endSession = useCallback(
    (reason: ContinuousListeningEndReason = 'manual') => {
      clearResumeTimer();
      setIsConversationActive(false);
      setTurnCount(0);
      setSessionStartedAt(null);
      setMode(enabled ? 'wake-word' : 'idle');
      updateShouldListen(false);
      onSessionEnd?.(reason);
    },
    [clearResumeTimer, enabled, onSessionEnd, updateShouldListen],
  );

  const beginListening = useCallback(() => {
    clearResumeTimer();
    setMode('listening');
    updateShouldListen(true);
  }, [clearResumeTimer, updateShouldListen]);

  const beginProcessing = useCallback(() => {
    clearResumeTimer();
    setMode('processing');
    updateShouldListen(false);
  }, [clearResumeTimer, updateShouldListen]);

  const beginSpeaking = useCallback(() => {
    clearResumeTimer();
    setMode('speaking');
    updateShouldListen(false);
    setTurnCount((currentTurnCount) => currentTurnCount + 1);
  }, [clearResumeTimer, updateShouldListen]);

  const completeAssistantTurn = useCallback(() => {
    clearResumeTimer();

    if (!enabled || !isConversationActive) {
      setMode(enabled ? 'wake-word' : 'idle');
      updateShouldListen(false);
      return;
    }

    setMode('idle');
    updateShouldListen(false);

    resumeTimerRef.current = window.setTimeout(() => {
      setMode('listening');
      updateShouldListen(true);
    }, autoResumeDelayMs);
  }, [
    autoResumeDelayMs,
    clearResumeTimer,
    enabled,
    isConversationActive,
    updateShouldListen,
  ]);

  const pauseListening = useCallback(() => {
    clearResumeTimer();
    updateShouldListen(false);

    if (isConversationActive) {
      setMode('idle');
    }
  }, [clearResumeTimer, isConversationActive, updateShouldListen]);

  const resumeListening = useCallback(() => {
    if (!enabled) {
      return;
    }

    if (!isConversationActive) {
      startSession('manual');
      return;
    }

    beginListening();
  }, [beginListening, enabled, isConversationActive, startSession]);

  useEffect(() => {
    if (enabled) {
      if (!isConversationActive) {
        setMode('wake-word');
      }
      return;
    }

    clearResumeTimer();
    setMode('idle');
    setIsConversationActive(false);
    setTurnCount(0);
    setSessionStartedAt(null);
    updateShouldListen(false);
  }, [clearResumeTimer, enabled, isConversationActive, updateShouldListen]);

  useEffect(() => () => clearResumeTimer(), [clearResumeTimer]);

  return {
    mode,
    isConversationActive,
    shouldListen,
    shouldArmWakeWord: enabled && !isConversationActive,
    turnCount,
    sessionStartedAt,
    startSession,
    endSession,
    beginListening,
    beginProcessing,
    beginSpeaking,
    completeAssistantTurn,
    pauseListening,
    resumeListening,
  };
}
