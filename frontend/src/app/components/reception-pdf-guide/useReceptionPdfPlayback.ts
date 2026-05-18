import { audioStateManager } from '@/lib/audio-state-manager';
import {
  AudioInteractionManager,
  unlockAudioForUserGesture,
} from '@/lib/audio/audio-interaction-manager';
import { AudioError, AudioErrorType, type AudioDataInput, type AudioOperationResult } from '@/lib/audio/audio-interfaces';
import { MobileAudioService } from '@/lib/audio/mobile-audio-service';
import {
  canUseStaticNarrationAudio,
  shouldFallbackToGeneratedNarration,
} from '@/lib/reception/reception-audio-readiness';
import { getReceptionNarrationAdvanceDelay } from '@/lib/reception/reception-narration-timing';
import { slideEventManager } from '@/lib/slide-events';
import { preprocessTTS } from '@/utils/tts-preprocess';
import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import { receptionPageAudioUrl } from './receptionPdfGuideUtils';
import type { ReceptionPdfGuideProps } from './types';
import { useReceptionNarrationText } from './useReceptionNarrationText';
import { useStaticNarrationAudioPreloader } from './useStaticNarrationAudioPreloader';

const SLIDE_DELAY_MS = 500;
const NARRATION_GAP_MS = 300;
const NARRATION_ASSET_RETRY_MS = 250;
const MIN_STATIC_NARRATION_PLAYBACK_MS = 1200;

type NarrationRun = {
  id: number;
  playbackSessionId: number;
  page: number;
  slideShownAtMs: number;
  playbackStartedAtMs: number | null;
  controller: AbortController;
  audioService: MobileAudioService | null;
};

type UseReceptionPdfPlaybackArgs = Pick<
  ReceptionPdfGuideProps,
  | 'autoStartKey'
  | 'language'
  | 'onExpressionControl'
  | 'onPresentationComplete'
  | 'onVisemeControl'
  | 'sessionId'
  | 'volume'
> & {
  currentPage: number;
  isLoading: boolean;
  landscapeReady: boolean;
  setCurrentPage: Dispatch<SetStateAction<number>>;
  setError: Dispatch<SetStateAction<string | null>>;
  totalPages: number;
};

export function useReceptionPdfPlayback({
  autoStartKey,
  currentPage,
  isLoading,
  language,
  landscapeReady,
  onExpressionControl,
  onPresentationComplete,
  onVisemeControl,
  sessionId = '',
  setCurrentPage,
  setError,
  totalPages,
  volume = 80,
}: UseReceptionPdfPlaybackArgs) {
  const [settings] = useState(() => ({
    autoAdvance: true,
    enableLipSync: true,
  }));
  const [isPlaying, setIsPlaying] = useState(false);
  const [isNarrating, setIsNarrating] = useState(false);
  const [isNarrationInProgress, setIsNarrationInProgress] = useState(false);
  const [audioPermissionRequired, setAudioPermissionRequired] = useState(false);
  const { isNarrationTextReady, narrationTexts } = useReceptionNarrationText(language);
  const preloadedAudioStateRef = useStaticNarrationAudioPreloader(language, totalPages);

  const autoPlayTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const narrationScheduleRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeNarrationRunRef = useRef<NarrationRun | null>(null);
  const narrationRunSeqRef = useRef(0);

  const playbackSessionRef = useRef(0);
  const isPlayingRef = useRef(isPlaying);
  const isNarratingRef = useRef(isNarrating);
  const isNarrationInProgressRef = useRef(isNarrationInProgress);
  const currentPageRef = useRef(currentPage);
  const totalPagesRef = useRef(totalPages);

  const pendingAutoStartRef = useRef(false);
  const lastAutoStartKeyRef = useRef<number | null>(null);
  const languageRef = useRef(language);

  languageRef.current = language;
  isPlayingRef.current = isPlaying;
  isNarratingRef.current = isNarrating;
  isNarrationInProgressRef.current = isNarrationInProgress;
  currentPageRef.current = currentPage;
  totalPagesRef.current = totalPages;

  useEffect(() => {
    const onAutoStart = (ev: Event) => {
      const ce = ev as CustomEvent<{ autoPlay?: boolean; language?: string }>;
      const lang = ce.detail?.language === 'en' ? 'en' : 'ja';
      if (lang !== languageRef.current) {
        return;
      }
      pendingAutoStartRef.current = true;
    };
    window.addEventListener('autoStartPresentation', onAutoStart as EventListener);
    return () => {
      window.removeEventListener('autoStartPresentation', onAutoStart as EventListener);
    };
  }, []);

  const setNarrationFlags = useCallback((active: boolean) => {
    isNarratingRef.current = active;
    isNarrationInProgressRef.current = active;
    setIsNarrating(active);
    setIsNarrationInProgress(active);
  }, []);

  const stopActiveNarration = useCallback(
    (resetUi = true) => {
      const run = activeNarrationRunRef.current;
      if (run) {
        run.controller.abort();
        run.audioService?.stop();
        run.audioService?.dispose();
        run.audioService = null;
        slideEventManager.emitNarrationComplete(run.page, {
          sessionId: String(run.playbackSessionId),
          narrationRunId: run.id,
        });
        activeNarrationRunRef.current = null;
      }
      if (resetUi) {
        setNarrationFlags(false);
      }
    },
    [setNarrationFlags],
  );

  const startPlaybackSession = useCallback(() => {
    stopActiveNarration();
    playbackSessionRef.current += 1;
    isPlayingRef.current = true;
    return playbackSessionRef.current;
  }, [stopActiveNarration]);

  const invalidatePlaybackSession = useCallback(() => {
    playbackSessionRef.current += 1;
    isPlayingRef.current = false;
    return playbackSessionRef.current;
  }, []);

  const isActiveSession = useCallback(
    (id: number) => playbackSessionRef.current === id && isPlayingRef.current,
    [],
  );

  const isActiveNarrationRun = useCallback(
    (run: NarrationRun) =>
      activeNarrationRunRef.current === run &&
      !run.controller.signal.aborted &&
      playbackSessionRef.current === run.playbackSessionId &&
      isPlayingRef.current &&
      currentPageRef.current === run.page,
    [],
  );

  const beginNarrationRun = useCallback(
    (playbackSessionId: number, page: number): NarrationRun => {
      stopActiveNarration(false);
      const run: NarrationRun = {
        id: narrationRunSeqRef.current + 1,
        playbackSessionId,
        page,
        slideShownAtMs: Date.now(),
        playbackStartedAtMs: null,
        controller: new AbortController(),
        audioService: null,
      };
      narrationRunSeqRef.current = run.id;
      activeNarrationRunRef.current = run;
      setNarrationFlags(true);
      slideEventManager.emitNarrationStart(page, {
        sessionId: String(playbackSessionId),
        narrationRunId: run.id,
      });
      return run;
    },
    [setNarrationFlags, stopActiveNarration],
  );

  const finishNarrationRun = useCallback(
    (run: NarrationRun) => {
      if (activeNarrationRunRef.current !== run) {
        return;
      }
      run.audioService?.dispose();
      run.audioService = null;
      activeNarrationRunRef.current = null;
      setNarrationFlags(false);
      slideEventManager.emitNarrationComplete(run.page, {
        sessionId: String(run.playbackSessionId),
        narrationRunId: run.id,
      });
    },
    [setNarrationFlags],
  );

  const playNarrationAudio = useCallback(
    async (audioData: AudioDataInput, run: NarrationRun): Promise<AudioOperationResult> => {
      if (!isActiveNarrationRun(run)) {
        return { success: false, method: 'cancelled' };
      }

      return new Promise<AudioOperationResult>((resolve) => {
        let settled = false;
        let didStartPlayback = false;
        let service: MobileAudioService | null = null;

        const settle = (result: AudioOperationResult) => {
          if (settled) {
            return;
          }
          settled = true;
          run.controller.signal.removeEventListener('abort', onAbort);
          if (run.audioService === service) {
            run.audioService = null;
          }
          service?.dispose();
          resolve(result);
        };

        const stopAsCancelled = () => {
          settle({ success: false, method: 'cancelled' });
        };

        const onAbort = () => {
          stopAsCancelled();
        };

        service = new MobileAudioService({
          volume: volume / 100,
          onPlay: () => {
            if (!isActiveNarrationRun(run)) {
              stopAsCancelled();
              return;
            }
            didStartPlayback = true;
            run.playbackStartedAtMs = Date.now();
          },
          onEnded: () => {
            onVisemeControl?.('Closed', 0);
            if (!isActiveNarrationRun(run)) {
              stopAsCancelled();
              return;
            }
            if (!didStartPlayback) {
              settle({
                success: false,
                method: service?.getCurrentMethod() ?? undefined,
                error: new AudioError(
                  AudioErrorType.PLAYBACK_FAILED,
                  'Audio ended before playback start was observed',
                ),
              });
              return;
            }
            settle({ success: true, method: service?.getCurrentMethod() ?? undefined });
          },
          onError: (error) => {
            settle({ success: false, error, method: service?.getCurrentMethod() ?? undefined });
          },
        });
        run.audioService = service;
        run.controller.signal.addEventListener('abort', onAbort, { once: true });

        service
          .playAudio(audioData)
          .then((result) => {
            if (!isActiveNarrationRun(run)) {
              stopAsCancelled();
              return;
            }
            if (!result.success) {
              settle(result);
            }
          })
          .catch(() => {
            settle({
              success: false,
              method: service?.getCurrentMethod() ?? undefined,
            });
          });
      });
    },
    [isActiveNarrationRun, onVisemeControl, volume],
  );

  const clearPlaybackWork = useCallback(() => {
    stopActiveNarration();
    if (autoPlayTimerRef.current) {
      clearTimeout(autoPlayTimerRef.current);
      autoPlayTimerRef.current = null;
    }
    if (narrationScheduleRef.current) {
      clearTimeout(narrationScheduleRef.current);
      narrationScheduleRef.current = null;
    }
    audioStateManager.stopAll();
    onVisemeControl?.('Closed', 0);
    onExpressionControl?.('neutral', 1.0);
  }, [onExpressionControl, onVisemeControl, stopActiveNarration]);

  const setPageState = useCallback(
    (p: number) => {
      slideEventManager.emitSlideTransitionStart(p, {
        sessionId: String(playbackSessionRef.current),
      });
      currentPageRef.current = p;
      setCurrentPage(p);
      slideEventManager.emitSlideTransitionComplete(p, {
        sessionId: String(playbackSessionRef.current),
      });
    },
    [setCurrentPage],
  );

  const advancePresentation = useCallback(
    (delayMs = SLIDE_DELAY_MS) => {
      const sid = playbackSessionRef.current;
      const step = () => {
        autoPlayTimerRef.current = null;
        setIsNarrating(false);
        if (!isActiveSession(sid)) {
          return;
        }
        const p = currentPageRef.current;
        const max = totalPagesRef.current;
        if (p < max) {
          setPageState(p + 1);
          narrationScheduleRef.current = setTimeout(() => {
            narrationScheduleRef.current = null;
            if (isActiveSession(sid)) {
              void narrateWithRetryRef.current();
            }
          }, NARRATION_GAP_MS);
          return;
        }
        invalidatePlaybackSession();
        setIsPlaying(false);
        onPresentationComplete?.('completed');
      };
      if (delayMs <= 0) {
        step();
        return;
      }
      if (autoPlayTimerRef.current) {
        clearTimeout(autoPlayTimerRef.current);
      }
      autoPlayTimerRef.current = setTimeout(() => {
        if (!isActiveSession(sid)) {
          autoPlayTimerRef.current = null;
          return;
        }
        step();
      }, delayMs);
    },
    [invalidatePlaybackSession, isActiveSession, onPresentationComplete, setPageState],
  );

  const advanceAfterSafeDwell = useCallback(
    (run: NarrationRun, requestedDelayMs = SLIDE_DELAY_MS) => {
      if (!isActiveNarrationRun(run)) {
        return;
      }
      advancePresentation(
        getReceptionNarrationAdvanceDelay({
          slideShownAtMs: run.slideShownAtMs,
          nowMs: Date.now(),
          requestedDelayMs,
        }),
      );
    },
    [advancePresentation, isActiveNarrationRun],
  );

  const scheduleNarrationRetry = useCallback(
    (playbackSessionId: number, page: number) => {
      if (narrationScheduleRef.current) {
        clearTimeout(narrationScheduleRef.current);
      }
      narrationScheduleRef.current = setTimeout(() => {
        narrationScheduleRef.current = null;
        if (
          isActiveSession(playbackSessionId) &&
          currentPageRef.current === page &&
          !isNarratingRef.current &&
          !isNarrationInProgressRef.current
        ) {
          void narrateWithRetryRef.current();
        }
      }, NARRATION_ASSET_RETRY_MS);
    },
    [isActiveSession],
  );

  const narrateCurrentSlide = useCallback(async () => {
    if (!isPlayingRef.current || isNarratingRef.current || isNarrationInProgressRef.current) {
      return;
    }
    const sid = playbackSessionRef.current;
    const pageAtStart = currentPageRef.current;
    const run = beginNarrationRun(sid, pageAtStart);
    const audioUrl = receptionPageAudioUrl(language, pageAtStart);
    const { signal } = run.controller;

    try {
      if (canUseStaticNarrationAudio(preloadedAudioStateRef.current.get(audioUrl))) {
        if (!isActiveNarrationRun(run)) {
          return;
        }

        let playedStaticAudio = false;
        try {
          const playbackStartedAt = Date.now();
          const result = await playNarrationAudio(audioUrl, run);
          const playbackElapsedMs = Date.now() - playbackStartedAt;
          if (!isActiveNarrationRun(run)) {
            return;
          }
          if (!result.success) {
            throw result.error ?? new Error('Audio playback failed');
          }
          if (playbackElapsedMs < MIN_STATIC_NARRATION_PLAYBACK_MS) {
            preloadedAudioStateRef.current.set(audioUrl, 'failed');
          } else {
            playedStaticAudio = true;
          }
          if (!isActiveNarrationRun(run)) {
            return;
          }
          if (playedStaticAudio && settings.autoAdvance) {
            advanceAfterSafeDwell(run, SLIDE_DELAY_MS);
          }
        } catch (err: unknown) {
          if (!isActiveNarrationRun(run)) {
            return;
          }
          if (!shouldFallbackToGeneratedNarration(err)) {
            setAudioPermissionRequired(true);
            setIsPlaying(false);
            onPresentationComplete?.('stopped');
            return;
          }
          preloadedAudioStateRef.current.set(audioUrl, 'failed');
        }
        if (playedStaticAudio) {
          return;
        }
      }

      const text = narrationTexts[pageAtStart - 1]?.trim() ?? '';
      if (!text) {
        if (!isNarrationTextReady) {
          if (isActiveNarrationRun(run)) {
            scheduleNarrationRetry(sid, pageAtStart);
          }
          return;
        }
        if (isActiveNarrationRun(run)) {
          advanceAfterSafeDwell(run, SLIDE_DELAY_MS);
        }
        return;
      }
      if (!isActiveNarrationRun(run)) {
        return;
      }
      let playedPiper = false;
      const sidTrim = sessionId.trim() || `reception-guide-${sid}`;
      try {
        const res = await fetch('/api/voice', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            action: 'text_to_speech',
            ttsProvider: 'piper',
            text: preprocessTTS(text, language),
            language,
            sessionId: sidTrim,
            includeVrmControl: false,
          }),
          signal,
        });
        const data = (await res.json()) as Record<string, unknown>;
        if (
          res.ok &&
          data.success &&
          typeof data.audioResponse === 'string' &&
          data.audioResponse.length > 0
        ) {
          const raw = Uint8Array.from(atob(data.audioResponse), (c) => c.charCodeAt(0));
          const buf = raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength);
          if (!isActiveNarrationRun(run)) {
            return;
          }
          const result = await playNarrationAudio(buf, run);
          playedPiper = result.success;
        }
      } catch {
        if (!isActiveNarrationRun(run)) {
          return;
        }
        playedPiper = false;
      }
      if (!playedPiper) {
        throw new Error('Piper Plus narration audio is not available');
      }
      if (!isActiveNarrationRun(run)) {
        return;
      }
      if (settings.autoAdvance) {
        advanceAfterSafeDwell(run, SLIDE_DELAY_MS);
      }
    } catch (e) {
      if (e instanceof Error && e.name === 'AbortError') {
        return;
      }
      if (isActiveNarrationRun(run)) {
        setError(
          language === 'ja'
            ? 'Piper Plus の音声を準備できませんでした。'
            : 'Piper Plus narration audio was not available.',
        );
        invalidatePlaybackSession();
        setIsPlaying(false);
        onPresentationComplete?.('stopped');
      }
    } finally {
      finishNarrationRun(run);
    }
  }, [
    advanceAfterSafeDwell,
    beginNarrationRun,
    finishNarrationRun,
    invalidatePlaybackSession,
    isActiveNarrationRun,
    isNarrationTextReady,
    language,
    narrationTexts,
    onPresentationComplete,
    playNarrationAudio,
    preloadedAudioStateRef,
    scheduleNarrationRetry,
    sessionId,
    setError,
    settings.autoAdvance,
  ]);

  const narrateWithRetryRef = useRef<(retries?: number) => Promise<void>>(async () => {});
  const narrateWithRetry = useCallback(
    async (retries = 2) => {
      const sid = playbackSessionRef.current;
      for (let i = 0; i < retries; i += 1) {
        if (!isActiveSession(sid)) {
          return;
        }
        try {
          await narrateCurrentSlide();
          return;
        } catch {
          if (i === retries - 1 && isActiveSession(sid)) {
            invalidatePlaybackSession();
            setIsPlaying(false);
            onPresentationComplete?.('stopped');
          } else {
            await new Promise((resolve) => setTimeout(resolve, 300 * (i + 1)));
          }
        }
      }
    },
    [invalidatePlaybackSession, isActiveSession, narrateCurrentSlide, onPresentationComplete],
  );
  narrateWithRetryRef.current = narrateWithRetry;

  const clearPlaybackWorkRef = useRef(clearPlaybackWork);
  clearPlaybackWorkRef.current = clearPlaybackWork;

  const tryConsumePendingAutoStart = useCallback(() => {
    if (!pendingAutoStartRef.current || !landscapeReady || isLoading || totalPages <= 0) {
      return;
    }
    pendingAutoStartRef.current = false;
    playbackSessionRef.current += 1;
    isPlayingRef.current = true;
    setAudioPermissionRequired(false);
    setIsPlaying(true);
  }, [isLoading, landscapeReady, totalPages]);

  useEffect(() => {
    tryConsumePendingAutoStart();
  }, [tryConsumePendingAutoStart]);

  useEffect(() => {
    if (!autoStartKey || lastAutoStartKeyRef.current === autoStartKey) {
      return;
    }
    lastAutoStartKeyRef.current = autoStartKey;
    pendingAutoStartRef.current = true;
    tryConsumePendingAutoStart();
  }, [autoStartKey, tryConsumePendingAutoStart]);

  useEffect(() => {
    if (!landscapeReady && isPlayingRef.current) {
      pendingAutoStartRef.current = false;
      playbackSessionRef.current += 1;
      isPlayingRef.current = false;
      setIsPlaying(false);
      clearPlaybackWorkRef.current();
    }
  }, [landscapeReady, onExpressionControl, onVisemeControl]);

  useEffect(() => {
    if (
      landscapeReady &&
      isPlaying &&
      totalPages > 0 &&
      !isNarratingRef.current &&
      !isNarrationInProgressRef.current
    ) {
      void narrateWithRetryRef.current();
    } else if (!isPlaying) {
      invalidatePlaybackSession();
      clearPlaybackWorkRef.current();
    }
    return () => {
      clearPlaybackWorkRef.current();
    };
  }, [invalidatePlaybackSession, isPlaying, language, landscapeReady, totalPages]);

  const stopAutoPlay = useCallback(() => {
    pendingAutoStartRef.current = false;
    invalidatePlaybackSession();
    clearPlaybackWork();
  }, [clearPlaybackWork, invalidatePlaybackSession]);

  const toggleAutoPlay = useCallback(() => {
    if (isPlaying) {
      stopAutoPlay();
      setIsPlaying(false);
      onPresentationComplete?.('stopped');
    } else {
      if (!landscapeReady) {
        return;
      }
      unlockAudioForUserGesture();
      setAudioPermissionRequired(false);
      startPlaybackSession();
      setIsPlaying(true);
    }
  }, [isPlaying, landscapeReady, onPresentationComplete, startPlaybackSession, stopAutoPlay]);

  const enableAudioAndResume = useCallback(async () => {
    unlockAudioForUserGesture();
    try {
      await AudioInteractionManager.getInstance().forceInitialize();
    } catch (error) {
      console.warn('[ReceptionPdfGuide] Failed to initialize audio context:', error);
      setAudioPermissionRequired(true);
      setIsPlaying(false);
      onPresentationComplete?.('stopped');
      return;
    }
    if (!landscapeReady) {
      return;
    }
    setAudioPermissionRequired(false);
    startPlaybackSession();
    setIsPlaying(true);
  }, [landscapeReady, onPresentationComplete, startPlaybackSession]);

  const previousSlide = useCallback(() => {
    if (currentPage > 1) {
      const was = isPlayingRef.current;
      stopAutoPlay();
      if (was) {
        setIsPlaying(false);
        onPresentationComplete?.('stopped');
      }
      setPageState(currentPage - 1);
    }
  }, [currentPage, onPresentationComplete, setPageState, stopAutoPlay]);

  const nextSlide = useCallback(() => {
    if (currentPage < totalPages) {
      const was = isPlayingRef.current;
      stopAutoPlay();
      if (was) {
        setIsPlaying(false);
        onPresentationComplete?.('stopped');
      }
      setPageState(currentPage + 1);
    }
  }, [currentPage, onPresentationComplete, setPageState, stopAutoPlay, totalPages]);

  const gotoSlide = useCallback(
    (n: number) => {
      if (n >= 1 && n <= totalPages) {
        const was = isPlayingRef.current;
        if (was) {
          stopAutoPlay();
          setIsPlaying(false);
          onPresentationComplete?.('stopped');
        }
        setPageState(n);
      }
    },
    [onPresentationComplete, setPageState, stopAutoPlay, totalPages],
  );

  return {
    audioPermissionRequired,
    enableAudioAndResume,
    gotoSlide,
    isPlaying,
    nextSlide,
    previousSlide,
    toggleAutoPlay,
  };
}
