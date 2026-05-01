'use client';

/**
 * Kiosk: reception PDF from public/reception/engineer-cafe-{ja,en}.pdf.
 * Optional per-page audio: public/reception/audio/{lang}/01.mp3 …
 * Falls back to Web Speech API using narration Markdown (no LLM).
 */
import { useKeyboardControls } from '@/app/hooks/useKeyboardControls';
import { audioStateManager } from '@/lib/audio-state-manager';
import type { LipSyncData } from '@/lib/audio/audio-playback-service';
import { AudioPlaybackService } from '@/lib/audio/audio-playback-service';
import {
  AudioInteractionManager,
  unlockAudioForUserGesture,
} from '@/lib/audio/audio-interaction-manager';
import {
  RECEPTION_GUIDE_AUDIO_EXT,
  receptionGuideAudioPrefix,
  receptionGuideLipsyncPrefix,
  receptionGuidePageStem,
  receptionGuidePdfUrl,
} from '@/lib/reception/reception-pdf-constants';
import { parseReceptionNarrationMarkdown } from '@/lib/reception/parse-reception-narration-md';
import { preprocessTTS } from '@/utils/tts-preprocess';
import { cn } from '@/lib/cn';
import { ChevronLeft, ChevronRight, Pause, Play, RotateCw, RotateCcw } from 'lucide-react';
import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { PDFDocumentProxy } from 'pdfjs-dist';
import type { PresentationCompleteReason } from './presentation-types';

const SLIDE_DELAY_MS = 500;
const NARRATION_GAP_MS = 300;

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

function parseLipSyncJson(raw: unknown): LipSyncData | null {
  if (!raw || typeof raw !== 'object') {
    return null;
  }
  const o = raw as Record<string, unknown>;
  if (typeof o.duration !== 'number' || !Array.isArray(o.frames)) {
    return null;
  }
  return { duration: o.duration, frames: o.frames as LipSyncData['frames'] };
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
  const [audioPermissionRequired, setAudioPermissionRequired] = useState(false);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const pdfDocRef = useRef<PDFDocumentProxy | null>(null);
  const renderTaskRef = useRef<{ cancel: () => void } | null>(null);

  const autoPlayTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const narrationScheduleRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const narrationAbortRef = useRef<AbortController | null>(null);

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
        }
      } catch {
        if (!cancelled) {
          setNarrationTexts([]);
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
    return () => {
      try {
        window.speechSynthesis?.cancel();
      } catch {
        /* ignore */
      }
    };
  }, []);

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
      narrationAbortRef.current?.abort();
      narrationAbortRef.current = null;
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

  const startPlaybackSession = () => {
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

  const clearPlaybackWork = useCallback(() => {
    narrationAbortRef.current?.abort();
    narrationAbortRef.current = null;
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
    setIsNarrating(false);
    setIsNarrationInProgress(false);
    audioStateManager.stopAll();
    onVisemeControl?.('Closed', 0);
    onExpressionControl?.('neutral', 1.0);
  }, [onExpressionControl, onVisemeControl]);

  const setPageState = (p: number) => {
    currentPageRef.current = p;
    setCurrentPage(p);
  };

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
    [onPresentationComplete]
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
    const stem = receptionGuidePageStem(pageAtStart);
    const audioPrefix = receptionGuideAudioPrefix(language);
    const lipsyncPrefix = receptionGuideLipsyncPrefix(language);
    const audioUrl = `${audioPrefix}/${stem}.${RECEPTION_GUIDE_AUDIO_EXT}`;

    narrationAbortRef.current = new AbortController();
    const { signal } = narrationAbortRef.current;

    try {
      const res = await fetch(audioUrl, { signal });
      if (res.ok) {
        const buf = await res.arrayBuffer();
        if (!isActiveSession(sid) || currentPageRef.current !== pageAtStart) {
          return;
        }

        let precomputed: LipSyncData | null = null;
        try {
          const lipRes = await fetch(`${lipsyncPrefix}/${stem}.json`, {
            signal,
          });
          if (lipRes.ok) {
            precomputed = parseLipSyncJson(await lipRes.json());
          }
        } catch {
          /* optional */
        }

        if (!isActiveSession(sid) || currentPageRef.current !== pageAtStart) {
          return;
        }

        setIsNarrationInProgress(true);
        setIsNarrating(true);
        try {
          await AudioInteractionManager.getInstance().ensureAudioContext();
          const result = await AudioPlaybackService.playAudioWithLipSync(buf, {
            volume: volume / 100,
            enableLipSync: settings.enableLipSync,
            precomputedLipSync: precomputed,
            onVisemeUpdate: onVisemeControl || undefined,
          });
          if (!result.success) {
            throw result.error ?? new Error('Audio playback failed');
          }
          if (!isActiveSession(sid) || currentPageRef.current !== pageAtStart) {
            return;
          }
          if (settings.autoAdvance) {
            advancePresentation(SLIDE_DELAY_MS);
          }
        } catch (err: unknown) {
          const e = err as { name?: string; message?: string; requiresUserInteraction?: boolean };
          if (
            e?.name === 'NotAllowedError' ||
            e?.requiresUserInteraction ||
            e?.message?.includes('interaction')
          ) {
            setAudioPermissionRequired(true);
            setIsPlaying(false);
            onPresentationComplete?.('stopped');
            return;
          }
          if (isActiveSession(sid)) {
            advancePresentation(800);
          }
        } finally {
          setIsNarrating(false);
          setIsNarrationInProgress(false);
        }
        return;
      }

      const text =
        narrationTexts[pageAtStart - 1]?.trim() ?? '';
      if (!text) {
        if (isActiveSession(sid)) {
          advancePresentation(400);
        }
        return;
      }
      if (!isActiveSession(sid) || currentPageRef.current !== pageAtStart) {
        return;
      }
      setIsNarrationInProgress(true);
      setIsNarrating(true);
      try {
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
              await AudioInteractionManager.getInstance().ensureAudioContext();
              const result = await AudioPlaybackService.playAudioWithLipSync(buf, {
                volume: volume / 100,
                enableLipSync: settings.enableLipSync,
                onVisemeUpdate: onVisemeControl || undefined,
              });
              playedPiper = result.success;
            }
          } catch {
            playedPiper = false;
          }
        }
        if (!playedPiper) {
          await speakNarrationText(text, language, signal);
        }
        if (!isActiveSession(sid) || currentPageRef.current !== pageAtStart) {
          return;
        }
        if (settings.autoAdvance) {
          advancePresentation(SLIDE_DELAY_MS);
        }
      } finally {
        setIsNarrating(false);
        setIsNarrationInProgress(false);
      }
    } catch (e) {
      if (e instanceof Error && e.name === 'AbortError') {
        return;
      }
      if (isActiveSession(sid)) {
        advancePresentation(400);
      }
    }
  }, [
    advancePresentation,
    language,
    narrationTexts,
    onPresentationComplete,
    onVisemeControl,
    sessionId,
    settings.autoAdvance,
    settings.enableLipSync,
    volume,
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
            advancePresentation(600);
          } else {
            await new Promise((r) => setTimeout(r, 300 * (i + 1)));
          }
        }
      }
    },
    [advancePresentation, narrateCurrentSlide]
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

  const stopAutoPlay = () => {
    pendingAutoStartRef.current = false;
    invalidatePlaybackSession();
    clearPlaybackWork();
  };

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

  const previousSlide = () => {
    if (currentPage > 1) {
      const was = isPlayingRef.current;
      stopAutoPlay();
      if (was) {
        setIsPlaying(false);
        onPresentationComplete?.('stopped');
      }
      setPageState(currentPage - 1);
    }
  };

  const nextSlide = () => {
    if (currentPage < totalPages) {
      const was = isPlayingRef.current;
      stopAutoPlay();
      if (was) {
        setIsPlaying(false);
        onPresentationComplete?.('stopped');
      }
      setPageState(currentPage + 1);
    }
  };

  const gotoSlide = (n: number) => {
    if (n >= 1 && n <= totalPages) {
      const was = isPlayingRef.current;
      if (was) {
        stopAutoPlay();
        setIsPlaying(false);
        onPresentationComplete?.('stopped');
      }
      setPageState(n);
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
      <div className="absolute left-2 right-12 top-2 z-20 flex flex-wrap items-center justify-between gap-1.5 rounded-xl border border-white/70 bg-white/85 px-2 py-1.5 shadow-lg backdrop-blur-md sm:left-3 sm:right-14 sm:top-3 sm:gap-2 sm:px-3 sm:py-2">
        <div className="flex items-center gap-2">
          <button
            type="button"
            data-testid="reception-pdf-prev"
            onClick={previousSlide}
            disabled={currentPage === 1}
            className="rounded bg-blue-500 p-1.5 text-white disabled:bg-gray-300 sm:p-2"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <button
            type="button"
            data-testid="reception-pdf-next"
            onClick={nextSlide}
            disabled={currentPage >= totalPages}
            className="rounded bg-blue-500 p-1.5 text-white disabled:bg-gray-300 sm:p-2"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
          <span data-testid="reception-pdf-counter" className="text-sm font-medium text-gray-700">
            {totalPages > 0 ? `${currentPage} / ${totalPages}` : '—'}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            data-testid="reception-pdf-play"
            onClick={toggleAutoPlay}
            aria-pressed={isPlaying}
            data-state={isPlaying ? 'playing' : 'paused'}
            className={cn(
              'rounded p-1.5 text-white sm:p-2',
              isPlaying ? 'bg-red-500' : 'bg-green-500'
            )}
          >
            {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
          </button>
          {isNarrating ? (
            <span className="hidden text-xs text-blue-700 sm:inline">
              {language === 'ja' ? 'ナレーション中…' : 'Narrating…'}
            </span>
          ) : null}
          <button
            type="button"
            data-testid="reception-pdf-reset"
            onClick={() => gotoSlide(1)}
            className="rounded bg-gray-500 p-1.5 text-white sm:p-2"
          >
            <RotateCcw className="h-4 w-4" />
          </button>
          <label className="flex items-center gap-1 text-xs text-gray-600">
            <input
              type="checkbox"
              checked={settings.enableLipSync}
              onChange={(e) =>
                setSettings((s) => ({ ...s, enableLipSync: e.target.checked }))
              }
            />
            <span className="hidden sm:inline">{language === 'ja' ? 'リップ' : 'Lip'}</span>
          </label>
          <label className="flex items-center gap-1 text-xs text-gray-600">
            <input
              type="checkbox"
              checked={settings.autoAdvance}
              onChange={(e) =>
                setSettings((s) => ({ ...s, autoAdvance: e.target.checked }))
              }
            />
            <span className="hidden sm:inline">{language === 'ja' ? '自動送り' : 'Auto-advance'}</span>
          </label>
        </div>
      </div>
      <div
        ref={wrapRef}
        data-testid="reception-pdf-landscape-panel"
        className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden bg-slate-100 p-0.5 sm:p-1"
      >
        <canvas ref={canvasRef} className="max-h-full max-w-full shadow-lg" data-testid="reception-pdf-canvas" />
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
