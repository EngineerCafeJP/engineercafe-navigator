'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';

export interface UseSilenceDetectionOptions {
  enabled?: boolean;
  timeoutMs?: number;
  checkIntervalMs?: number;
  levelThreshold?: number;
  onSilence?: (durationMs: number) => void;
}

export interface UseSilenceDetectionResult {
  isSilent: boolean;
  lastActivityAt: number | null;
  silenceDurationMs: number;
  remainingMs: number;
  markActivity: () => void;
  markAudioLevel: (level: number) => boolean;
  resetSilenceTimer: () => void;
}

const DEFAULT_TIMEOUT_MS = 12_000;
const DEFAULT_CHECK_INTERVAL_MS = 250;
const DEFAULT_LEVEL_THRESHOLD = 0.08;

export function useSilenceDetection({
  enabled = true,
  timeoutMs = DEFAULT_TIMEOUT_MS,
  checkIntervalMs = DEFAULT_CHECK_INTERVAL_MS,
  levelThreshold = DEFAULT_LEVEL_THRESHOLD,
  onSilence,
}: UseSilenceDetectionOptions = {}): UseSilenceDetectionResult {
  const [lastActivityAt, setLastActivityAt] = useState<number | null>(null);
  const [isSilent, setIsSilent] = useState(false);
  const [silenceDurationMs, setSilenceDurationMs] = useState(0);
  const [remainingMs, setRemainingMs] = useState(timeoutMs);

  const markActivity = useCallback(() => {
    const now = Date.now();
    setLastActivityAt(now);
    setIsSilent(false);
    setSilenceDurationMs(0);
    setRemainingMs(timeoutMs);
  }, [timeoutMs]);

  const resetSilenceTimer = useCallback(() => {
    markActivity();
  }, [markActivity]);

  const markAudioLevel = useCallback(
    (level: number) => {
      if (level < levelThreshold) {
        return false;
      }

      markActivity();
      return true;
    },
    [levelThreshold, markActivity],
  );

  useEffect(() => {
    if (!enabled || lastActivityAt === null) {
      setIsSilent(false);
      setSilenceDurationMs(0);
      setRemainingMs(timeoutMs);
      return;
    }

    let callbackFired = false;

    const intervalId = window.setInterval(() => {
      const elapsed = Date.now() - lastActivityAt;
      const nextRemainingMs = Math.max(timeoutMs - elapsed, 0);

      setRemainingMs(nextRemainingMs);

      if (elapsed >= timeoutMs) {
        setIsSilent(true);
        setSilenceDurationMs(elapsed);

        if (!callbackFired) {
          callbackFired = true;
          onSilence?.(elapsed);
        }

        return;
      }

      setIsSilent(false);
      setSilenceDurationMs(0);
    }, checkIntervalMs);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [checkIntervalMs, enabled, lastActivityAt, onSilence, timeoutMs]);

  useEffect(() => {
    setRemainingMs(timeoutMs);
  }, [timeoutMs]);

  const result = useMemo(
    () => ({
      isSilent,
      lastActivityAt,
      silenceDurationMs,
      remainingMs,
      markActivity,
      markAudioLevel,
      resetSilenceTimer,
    }),
    [
      isSilent,
      lastActivityAt,
      markActivity,
      markAudioLevel,
      remainingMs,
      resetSilenceTimer,
      silenceDurationMs,
    ],
  );

  return result;
}
