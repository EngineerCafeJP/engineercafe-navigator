import { cn } from '@/lib/cn';
import { ChevronLeft, ChevronRight, Pause, Play, RotateCcw, RotateCw } from 'lucide-react';
import type React from 'react';

type Language = 'ja' | 'en';

type StatusViewProps = {
  className?: string;
  language: Language;
};

export function ReceptionPdfLoadingView({ className, language }: StatusViewProps) {
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

type ErrorViewProps = {
  className?: string;
  error: string;
};

export function ReceptionPdfErrorView({ className, error }: ErrorViewProps) {
  return (
    <div
      data-testid="reception-pdf-guide"
      className={cn('flex h-full items-center justify-center p-4', className)}
    >
      <p className="text-center text-red-600">{error}</p>
    </div>
  );
}

type RotatePromptProps = {
  className?: string;
  rotateLandscapeHint: string;
};

export function ReceptionPdfRotatePrompt({
  className,
  rotateLandscapeHint,
}: RotatePromptProps) {
  return (
    <div
      data-testid="reception-pdf-guide"
      className={cn(
        'flex h-full min-h-0 flex-col items-center justify-center gap-6 bg-slate-950 p-8 text-center text-white',
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

type LandscapeViewProps = {
  audioPermissionRequired: boolean;
  canvasRef: React.RefObject<HTMLCanvasElement | null>;
  className?: string;
  currentPage: number;
  enableAudioAndResume: () => void;
  gotoSlide: (n: number) => void;
  isPlaying: boolean;
  language: Language;
  nextSlide: () => void;
  onSlidePointerCancel: (event: React.PointerEvent<HTMLDivElement>) => void;
  onSlidePointerDown: (event: React.PointerEvent<HTMLDivElement>) => void;
  onSlidePointerUp: (event: React.PointerEvent<HTMLDivElement>) => void;
  previousSlide: () => void;
  toggleAutoPlay: () => void;
  totalPages: number;
  wrapRef: React.RefObject<HTMLDivElement | null>;
};

export function ReceptionPdfLandscapeView({
  audioPermissionRequired,
  canvasRef,
  className,
  currentPage,
  enableAudioAndResume,
  gotoSlide,
  isPlaying,
  language,
  nextSlide,
  onSlidePointerCancel,
  onSlidePointerDown,
  onSlidePointerUp,
  previousSlide,
  toggleAutoPlay,
  totalPages,
  wrapRef,
}: LandscapeViewProps) {
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
        className="kiosk-slide-surface relative flex min-h-0 flex-1 items-center justify-center overflow-hidden bg-slate-100 p-0.5 sm:p-1"
      >
        <canvas
          ref={canvasRef}
          className="max-h-full max-w-full shadow-lg"
          data-testid="reception-pdf-canvas"
        />
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
          {isPlaying ? (
            <Pause className="h-4 w-4" aria-hidden />
          ) : (
            <Play className="h-4 w-4" aria-hidden />
          )}
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
