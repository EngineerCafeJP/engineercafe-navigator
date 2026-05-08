'use client';

/**
 * Kiosk: reception PDF from public/reception/engineer-cafe-{ja,en}.pdf.
 * Optional per-page audio: public/reception/audio/{lang}/01.mp3 …
 * Falls back to Web Speech API using narration Markdown (no LLM).
 */
import { useKeyboardControls } from '@/app/hooks/useKeyboardControls';
import { audioStateManager } from '@/lib/audio-state-manager';
import {
  AudioInteractionManager,
  unlockAudioForUserGesture,
} from '@/lib/audio/audio-interaction-manager';
import { MobileAudioService } from '@/lib/audio/mobile-audio-service';
import {
  AudioError,
  AudioErrorType,
  type AudioDataInput,
  type AudioOperationResult,
} from '@/lib/audio/audio-interfaces';
import {
  RECEPTION_GUIDE_AUDIO_EXT,
  receptionGuideAudioPrefix,
  receptionGuidePageStem,
  receptionGuidePdfUrl,
} from '@/lib/reception/reception-pdf-constants';
import {
  canUseStaticNarrationAudio,
  shouldFallbackToGeneratedNarration,
  type StaticNarrationAudioState,
} from '@/lib/reception/reception-audio-readiness';
import { getReceptionNarrationAdvanceDelay } from '@/lib/reception/reception-narration-timing';
import { parseReceptionNarrationMarkdown } from '@/lib/reception/parse-reception-narration-md';
import { preprocessTTS } from '@/utils/tts-preprocess';
import { cn } from '@/lib/cn';
import { slideEventManager } from '@/lib/slide-events';
import { ChevronLeft, ChevronRight, Pause, Play, RotateCw, RotateCcw } from 'lucide-react';
import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { PDFDocumentProxy } from 'pdfjs-dist';
import type { PresentationCompleteReason } from './presentation-types';

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
const SWIPE_MIN_DISTANCE_PX = 64;
const SWIPE_HORIZONTAL_DOMINANCE = 1.35;

function toSameOriginUrl(path: string): string {
  if (typeof window === 'undefined') {
    return path;
  }
  return new URL(path, window.location.origin).toString();
}

function useLandscapeReady(): boolean {
  const [landscape, setLandscape] = useState(false);

  useEffect(() => {
    const update = () => {
      const mq = window.matchMedia('(orientation: landscape)');
      const bySize = window.innerWidth > window.innerHeight;
      setLandscape(mq.matches || bySize);
    };
    update();
    const mq = window.matchMedia('(orientation: landscape)');
    mq.addEventListener('change', update);
    window.addEventListener('resize', update);
    window.addEventListener('orientationchange', update);
    return () => {
      mq.removeEventListener('change', update);
      window.removeEventListener('resize', update);
      window.removeEventListener('orientationchange', update);
    };
  }, []);

  return landscape;
}

async function speakNarrationText(
  text: string,
  language: 'ja' | 'en',
  signal: AbortSignal,
): Promise<void> {
  if (typeof window === 'undefined' || !window.speechSynthesis) {
    await new Promise((r) => setTimeout(r, Math.min(15000, 600 + text.length * 45)));
    return;
  }
  return new Promise((resolve) => {
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = language === 'ja' ? 'ja-JP' : 'en-US';
    u.rate = 1;
    const onAbort = () => {
      window.speechSynthesis.cancel();
      resolve();
    };
    signal.addEventListener('abort', onAbort);
    u.onend = () => {
      signal.removeEventListener('abort', onAbort);
      resolve();
    };
    u.onerror = () => {
      signal.removeEventListener('abort', onAbort);
      resolve();
    };
    window.speechSynthesis.speak(u);
  });
}

/** flex 子で contentRect.height が 0 のとき client から内側の描画域を拾う */
function measurePdfWrapContent(
  el: HTMLDivElement,
  entry?: ResizeObserverEntry,
): { width: number; height: number } {
  const cs = getComputedStyle(el);
  const pl = parseFloat(cs.paddingLeft) || 0;
  const pr = parseFloat(cs.paddingRight) || 0;
  const pt = parseFloat(cs.paddingTop) || 0;
  const pb = parseFloat(cs.paddingBottom) || 0;
  const clientInnerW = Math.max(0, el.clientWidth - pl - pr);
  const clientInnerH = Math.max(0, el.clientHeight - pt - pb);

  let width = entry?.contentRect.width ?? 0;
  let height = entry?.contentRect.height ?? 0;

  if (width <= 0 && clientInnerW > 0) {
    width = clientInnerW;
  }
  if (height <= 0 && clientInnerH > 0) {
    height = clientInnerH;
  }
  if (width > 0 && height === 0 && clientInnerH > 0) {
    height = clientInnerH;
  }
  if (height > 0 && width === 0 && clientInnerW > 0) {
    width = clientInnerW;
  }
  return { width, height };
}

interface ReceptionPdfGuideProps {
  language: 'ja' | 'en';
  rotateLandscapeHint: string;
  autoStartKey?: number;
  className?: string;
  /** Passed to PiperPlus `/api/voice` narration (optional Web Speech fallback). */
  sessionId?: string;
  onVisemeControl?: ((viseme: string, intensity: number) => void) | null;
  onExpressionControl?: ((expression: string, weight: number) => void) | null;
  volume?: number;
  onPresentationComplete?: (reason: PresentationCompleteReason) => void;
}

export default function ReceptionPdfGuide({
  language,
  rotateLandscapeHint,
  autoStartKey,
  className,
  sessionId = '',
  onVisemeControl,
  onExpressionControl,
  volume = 80,
  onPresentationComplete,
}: ReceptionPdfGuideProps) {
  const pdfUrl = receptionGuidePdfUrl(language);
  const landscapeReady = useLandscapeReady();

  const [settings, setSettings] = useState(() => ({
    autoAdvance: true,
    enableLipSync: true,
  }));

  const [totalPages, setTotalPages] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isNarrating, setIsNarrating] = useState(false);
  const [isNarrationInProgress, setIsNarrationInProgress] = useState(false);
  const [containerBounds, setContainerBounds] = useState({ width: 800, height: 600 });
  const [narrationTexts, setNarrationTexts] = useState<string[]>([]);
  const [isNarrationTextReady, setIsNarrationTextReady] = useState(false);
  const [audioPermissionRequired, setAudioPermissionRequired] = useState(false);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const pdfDocRef = useRef<PDFDocumentProxy | null>(null);
  const renderTaskRef = useRef<{ cancel: () => void } | null>(null);

  const autoPlayTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const narrationScheduleRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeNarrationRunRef = useRef<NarrationRun | null>(null);
  const narrationRunSeqRef = useRef(0);
  const preloadedAudioRef = useRef<Map<string, HTMLAudioElement>>(new Map());
  const preloadedAudioStateRef = useRef<Map<string, StaticNarrationAudioState>>(new Map());
  const swipeStartRef = useRef<{
    pointerId: number | null;
    x: number;
    y: number;
  } | null>(null);

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
    let cancelled = false;
    setIsNarrationTextReady(false);
    (async () => {
      const mdUrl =
        language === 'ja'
          ? '/reception/engineer-cafe-narration-ja.md'
          : '/reception/engineer-cafe-narration-en.md';
      try {
        const res = await fetch(mdUrl);
        const md = await res.text();
        const slides = parseReceptionNarrationMarkdown(md, language);
        if (!cancelled) {
          setNarrationTexts(slides);
          setIsNarrationTextReady(true);
        }
      } catch {
        if (!cancelled) {
          setNarrationTexts([]);
          setIsNarrationTextReady(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [language]);

  useLayoutEffect(() => {
    if (isLoading || error) {
      return;
    }
    const el = wrapRef.current;
    if (!el) {
      return;
    }
    const m = measurePdfWrapContent(el);
    if (m.width > 0) {
      setContainerBounds({ width: m.width, height: m.height });
    }
  }, [isLoading, error, landscapeReady]);

  useEffect(() => {
    if (isLoading || error) {
      return;
    }
    const el = wrapRef.current;
    if (!el || typeof ResizeObserver === 'undefined') {
      return;
    }
    const apply = (entry?: ResizeObserverEntry) => {
      const m = measurePdfWrapContent(el, entry);
      if (m.width <= 0) {
        return;
      }
      setContainerBounds({ width: m.width, height: m.height });
      if (m.height <= 0) {
        requestAnimationFrame(() => {
          if (wrapRef.current !== el) {
            return;
          }
          const again = measurePdfWrapContent(el);
          if (again.width > 0 && again.height > 0) {
            setContainerBounds(again);
          }
        });
      }
    };
    apply();
    const ro = new ResizeObserver((entries) => {
      apply(entries[0]);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [isLoading, error, landscapeReady]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setIsLoading(true);
        setError(null);
        const pdfjs = await import('pdfjs-dist');
        pdfjs.GlobalWorkerOptions.workerSrc = '/assets/js/pdf.worker.min.mjs';
        const pdf = await pdfjs.getDocument({ url: pdfUrl }).promise;
        if (cancelled) {
          await pdf.destroy().catch(() => {});
          return;
        }
        if (pdfDocRef.current) {
          await pdfDocRef.current.destroy().catch(() => {});
        }
        pdfDocRef.current = pdf;
        setTotalPages(pdf.numPages);
        totalPagesRef.current = pdf.numPages;
        setCurrentPage(1);
        currentPageRef.current = 1;
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'PDF を開けませんでした');
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
      if (pdfDocRef.current) {
        void pdfDocRef.current.destroy();
        pdfDocRef.current = null;
      }
    };
  }, [pdfUrl]);

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

  useEffect(() => {
    const preloadedAudio = preloadedAudioRef.current;
    const preloadedAudioState = preloadedAudioStateRef.current;
    return () => {
      try {
        window.speechSynthesis?.cancel();
      } catch {
        /* ignore */
      }
      for (const audio of Array.from(preloadedAudio.values())) {
        audio.pause();
        audio.removeAttribute('src');
        audio.load();
      }
      preloadedAudio.clear();
      preloadedAudioState.clear();
    };
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined' || totalPages <= 0) {
      return;
    }

    const expected = new Set<string>();
    const audioPrefix = receptionGuideAudioPrefix(language);
    for (let page = 1; page <= totalPages; page += 1) {
      const stem = receptionGuidePageStem(page);
      const audioUrl = toSameOriginUrl(`${audioPrefix}/${stem}.${RECEPTION_GUIDE_AUDIO_EXT}`);
      expected.add(audioUrl);
      if (preloadedAudioRef.current.has(audioUrl)) {
        continue;
      }
      const audio = new Audio(audioUrl);
      audio.preload = 'auto';
      audio.setAttribute('playsinline', 'true');
      audio.setAttribute('webkit-playsinline', 'true');
      const markReady = () => {
        if (preloadedAudioRef.current.get(audioUrl) === audio) {
          preloadedAudioStateRef.current.set(audioUrl, 'ready');
        }
      };
      const markFailed = () => {
        if (preloadedAudioRef.current.get(audioUrl) === audio) {
          preloadedAudioStateRef.current.set(audioUrl, 'failed');
        }
      };
      audio.addEventListener('canplay', markReady, { once: true });
      audio.addEventListener('canplaythrough', markReady, { once: true });
      audio.addEventListener('error', markFailed, { once: true });
      preloadedAudioRef.current.set(audioUrl, audio);
      preloadedAudioStateRef.current.set(audioUrl, audio.readyState >= 3 ? 'ready' : 'pending');
      audio.load();
      if (audio.readyState >= 3) {
        preloadedAudioStateRef.current.set(audioUrl, 'ready');
      }
    }

    for (const [url, audio] of Array.from(preloadedAudioRef.current.entries())) {
      if (!expected.has(url)) {
        audio.pause();
        audio.removeAttribute('src');
        audio.load();
        preloadedAudioRef.current.delete(url);
        preloadedAudioStateRef.current.delete(url);
      }
    }
  }, [language, totalPages]);

  const tryConsumePendingAutoStart = useCallback(() => {
    if (
      !pendingAutoStartRef.current ||
      !landscapeReady ||
      isLoading ||
      totalPages <= 0
    ) {
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
      if (autoPlayTimerRef.current) {
        clearTimeout(autoPlayTimerRef.current);
        autoPlayTimerRef.current = null;
      }
      if (narrationScheduleRef.current) {
        clearTimeout(narrationScheduleRef.current);
        narrationScheduleRef.current = null;
      }
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
      isNarratingRef.current = false;
      isNarrationInProgressRef.current = false;
      setIsNarrating(false);
      setIsNarrationInProgress(false);
      try {
        window.speechSynthesis?.cancel();
      } catch {
        /* ignore */
      }
      audioStateManager.stopAll();
      onVisemeControl?.('Closed', 0);
      onExpressionControl?.('neutral', 1.0);
    }
  }, [landscapeReady, onExpressionControl, onVisemeControl]);

  useEffect(() => {
    const pdf = pdfDocRef.current;
    const canvas = canvasRef.current;
    if (!pdf || !canvas || currentPage < 1 || currentPage > totalPages) {
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        renderTaskRef.current?.cancel();
        const page = await pdf.getPage(currentPage);
        if (cancelled) {
          return;
        }
        const viewport0 = page.getViewport({ scale: 1 });
        const { width: cw, height: ch } = containerBounds;
        const scaleByWidth = cw / viewport0.width;
        const scaleByHeight =
          ch > 0 ? ch / viewport0.height : scaleByWidth;
        const fitScale = Math.min(scaleByWidth, scaleByHeight);
        const scale = Math.min(Math.max(fitScale, 0.2), 3);
        const viewport = page.getViewport({ scale });
        const ctx = canvas.getContext('2d');
        if (!ctx) {
          return;
        }
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        const task = page.render({ canvasContext: ctx, viewport });
        renderTaskRef.current = task;
        await task.promise;
      } catch (e) {
        const name = (e as Error)?.name ?? '';
        if (!cancelled && name !== 'RenderingCancelledException' && name !== 'AbortException') {
          console.warn('[ReceptionPdfGuide] render failed:', e);
        }
      }
    })();
    return () => {
      cancelled = true;
      renderTaskRef.current?.cancel();
    };
  }, [currentPage, totalPages, containerBounds]);

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

  const startPlaybackSession = () => {
    stopActiveNarration();
    playbackSessionRef.current += 1;
    isPlayingRef.current = true;
    return playbackSessionRef.current;
  };

  const invalidatePlaybackSession = () => {
    playbackSessionRef.current += 1;
    isPlayingRef.current = false;
    return playbackSessionRef.current;
  };

  const isActiveSession = (id: number) =>
    playbackSessionRef.current === id && isPlayingRef.current;

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
    async (
      audioData: AudioDataInput,
      run: NarrationRun,
    ): Promise<AudioOperationResult> => {
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
    try {
      window.speechSynthesis?.cancel();
    } catch {
      /* ignore */
    }
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

  const setPageState = useCallback((p: number) => {
    slideEventManager.emitSlideTransitionStart(p, {
      sessionId: String(playbackSessionRef.current),
    });
    currentPageRef.current = p;
    setCurrentPage(p);
    slideEventManager.emitSlideTransitionComplete(p, {
      sessionId: String(playbackSessionRef.current),
    });
  }, []);

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
    [onPresentationComplete, setPageState]
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
    [],
  );

  const narrateCurrentSlide = useCallback(async () => {
    if (
      !isPlayingRef.current ||
      isNarratingRef.current ||
      isNarrationInProgressRef.current
    ) {
      return;
    }
    const sid = playbackSessionRef.current;
    const pageAtStart = currentPageRef.current;
    const run = beginNarrationRun(sid, pageAtStart);
    const stem = receptionGuidePageStem(pageAtStart);
    const audioPrefix = receptionGuideAudioPrefix(language);
    const audioUrl = toSameOriginUrl(`${audioPrefix}/${stem}.${RECEPTION_GUIDE_AUDIO_EXT}`);
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

      const text =
        narrationTexts[pageAtStart - 1]?.trim() ?? '';
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
      const sidTrim = sessionId.trim();
      if (sidTrim.length > 0) {
        try {
          const res = await fetch('/api/voice', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              action: 'text_to_speech',
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
      }
      if (!playedPiper) {
        await speakNarrationText(text, language, signal);
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
    isActiveNarrationRun,
    isNarrationTextReady,
    language,
    narrationTexts,
    onPresentationComplete,
    playNarrationAudio,
    scheduleNarrationRetry,
    sessionId,
    settings.autoAdvance,
  ]);

  const narrateWithRetryRef = useRef<(retries?: number) => Promise<void>>(async () => {});
  const narrateWithRetry = useCallback(
    async (retries = 2) => {
      const sid = playbackSessionRef.current;
      for (let i = 0; i < retries; i++) {
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
            await new Promise((r) => setTimeout(r, 300 * (i + 1)));
          }
        }
      }
    },
    [narrateCurrentSlide, onPresentationComplete]
  );
  narrateWithRetryRef.current = narrateWithRetry;

  const clearPlaybackWorkRef = useRef(clearPlaybackWork);
  clearPlaybackWorkRef.current = clearPlaybackWork;

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
  }, [isPlaying, totalPages, landscapeReady, language]);

  const stopAutoPlay = useCallback(() => {
    pendingAutoStartRef.current = false;
    invalidatePlaybackSession();
    clearPlaybackWork();
  }, [clearPlaybackWork]);

  const toggleAutoPlay = () => {
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
  };

  const enableAudioAndResume = async () => {
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
  };

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

  const gotoSlide = useCallback((n: number) => {
    if (n >= 1 && n <= totalPages) {
      const was = isPlayingRef.current;
      if (was) {
        stopAutoPlay();
        setIsPlaying(false);
        onPresentationComplete?.('stopped');
      }
      setPageState(n);
    }
  }, [onPresentationComplete, setPageState, stopAutoPlay, totalPages]);

  const handleSwipeDelta = useCallback(
    (deltaX: number, deltaY: number) => {
      const absX = Math.abs(deltaX);
      const absY = Math.abs(deltaY);
      if (
        absX < SWIPE_MIN_DISTANCE_PX ||
        absX < absY * SWIPE_HORIZONTAL_DOMINANCE
      ) {
        return;
      }
      if (deltaX < 0) {
        nextSlide();
      } else {
        previousSlide();
      }
    },
    [nextSlide, previousSlide],
  );

  const onSlidePointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!event.isPrimary || event.button !== 0) {
      return;
    }
    swipeStartRef.current = {
      pointerId: event.pointerId,
      x: event.clientX,
      y: event.clientY,
    };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  };

  const onSlidePointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    const start = swipeStartRef.current;
    if (!start || start.pointerId !== event.pointerId) {
      return;
    }
    swipeStartRef.current = null;
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    handleSwipeDelta(event.clientX - start.x, event.clientY - start.y);
  };

  const onSlidePointerCancel = (event: React.PointerEvent<HTMLDivElement>) => {
    if (swipeStartRef.current?.pointerId === event.pointerId) {
      swipeStartRef.current = null;
    }
  };

  useKeyboardControls({
    onPrevious: previousSlide,
    onReset: () => gotoSlide(1),
    onTogglePlay: toggleAutoPlay,
    onNumberKey: (num) => gotoSlide(num),
    enabled: landscapeReady && !isLoading && !error,
  });

  if (isLoading) {
    return (
      <div
        data-testid="reception-pdf-guide"
        className={cn('flex h-full items-center justify-center', className)}
      >
        <p className="text-gray-600">
          {language === 'ja' ? '読み込み中…' : 'Loading…'}
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div
        data-testid="reception-pdf-guide"
        className={cn('flex h-full items-center justify-center p-4', className)}
      >
        <p className="text-center text-red-600">{error}</p>
      </div>
    );
  }

  if (!landscapeReady) {
    return (
      <div
        data-testid="reception-pdf-guide"
        className={cn(
          'fixed inset-0 z-[100] flex min-h-[100dvh] flex-col items-center justify-center gap-6 bg-slate-950 p-8 text-center text-white',
          className,
        )}
      >
        <RotateCw className="h-20 w-20 shrink-0 opacity-90" aria-hidden />
        <p
          data-testid="reception-pdf-rotate-hint"
          className="max-w-md text-lg font-medium leading-relaxed"
        >
          {rotateLandscapeHint}
        </p>
      </div>
    );
  }

  return (
    <div
      data-testid="reception-pdf-guide"
      className={cn('relative flex h-full min-h-0 flex-col', className)}
    >
      <div
        ref={wrapRef}
        data-testid="reception-pdf-landscape-panel"
        onPointerDown={onSlidePointerDown}
        onPointerUp={onSlidePointerUp}
        onPointerCancel={onSlidePointerCancel}
        className="relative flex min-h-0 flex-1 touch-pan-y items-center justify-center overflow-hidden bg-slate-100 p-0.5 sm:p-1"
      >
        <canvas ref={canvasRef} className="max-h-full max-w-full shadow-lg" data-testid="reception-pdf-canvas" />
      </div>
      <div
        data-testid="reception-pdf-controls"
        className="absolute bottom-2 left-1/2 z-20 flex -translate-x-1/2 items-center gap-1.5 rounded-lg border border-white/70 bg-slate-950/75 px-2 py-1.5 text-white shadow-lg backdrop-blur-md sm:bottom-3 sm:gap-2 sm:px-3 sm:py-2"
      >
        <button
          type="button"
          data-testid="reception-pdf-prev"
          onClick={previousSlide}
          disabled={currentPage === 1}
          aria-label={language === 'ja' ? '前のスライド' : 'Previous slide'}
          className="inline-flex size-9 items-center justify-center rounded bg-white/15 text-white transition-colors hover:bg-white/25 disabled:bg-white/5 disabled:text-white/35 sm:size-10"
        >
          <ChevronLeft className="h-4 w-4" aria-hidden />
        </button>
        <button
          type="button"
          data-testid="reception-pdf-play"
          onClick={toggleAutoPlay}
          aria-label={
            isPlaying
              ? language === 'ja'
                ? '一時停止'
                : 'Pause'
              : language === 'ja'
                ? '再生'
                : 'Play'
          }
          aria-pressed={isPlaying}
          data-state={isPlaying ? 'playing' : 'paused'}
          className={cn(
            'inline-flex size-9 items-center justify-center rounded text-white transition-colors sm:size-10',
            isPlaying ? 'bg-red-500 hover:bg-red-600' : 'bg-emerald-600 hover:bg-emerald-700',
          )}
        >
          {isPlaying ? <Pause className="h-4 w-4" aria-hidden /> : <Play className="h-4 w-4" aria-hidden />}
        </button>
        <span
          data-testid="reception-pdf-counter"
          className="min-w-14 text-center text-sm font-semibold tabular-nums text-white"
        >
          {totalPages > 0 ? `${currentPage} / ${totalPages}` : '—'}
        </span>
        <button
          type="button"
          data-testid="reception-pdf-reset"
          onClick={() => gotoSlide(1)}
          aria-label={language === 'ja' ? '最初のスライドへ' : 'Reset to first slide'}
          className="inline-flex size-9 items-center justify-center rounded bg-white/15 text-white transition-colors hover:bg-white/25 sm:size-10"
        >
          <RotateCcw className="h-4 w-4" aria-hidden />
        </button>
        <button
          type="button"
          data-testid="reception-pdf-next"
          onClick={nextSlide}
          disabled={currentPage >= totalPages}
          aria-label={language === 'ja' ? '次のスライド' : 'Next slide'}
          className="inline-flex size-9 items-center justify-center rounded bg-white/15 text-white transition-colors hover:bg-white/25 disabled:bg-white/5 disabled:text-white/35 sm:size-10"
        >
          <ChevronRight className="h-4 w-4" aria-hidden />
        </button>
      </div>
      {audioPermissionRequired ? (
        <div className="absolute inset-0 z-30 flex items-center justify-center bg-black/45 p-4">
          <div className="max-w-sm rounded-lg bg-white p-5 text-center shadow-xl">
            <p className="mb-4 text-sm font-medium text-gray-800">
              {language === 'ja'
                ? '音声再生を有効にしてください。'
                : 'Enable audio playback to continue.'}
            </p>
            <button
              type="button"
              onClick={enableAudioAndResume}
              className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-700"
            >
              {language === 'ja' ? '音声を有効化' : 'Enable audio'}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
