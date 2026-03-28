/**
 * OcrCameraView — Issue #314
 *
 * Camera preview with OCR scanning overlay.
 * Shows quality indicators, attempt count, and scanning status.
 */

'use client';

import { useCallback, useEffect, useRef } from 'react';

import { cn } from '@/lib/cn';
import {
  type OcrMode,
  type OcrResponse,
} from '@/lib/api/ocr-api';
import {
  type OcrCameraState,
  useOcrCamera,
} from '@/hooks/useOcrCamera';

interface OcrCameraViewProps {
  mode: OcrMode;
  sessionId?: string;
  /** When true, start the camera and scanning as soon as the view mounts (no idle / start button). */
  autoStart?: boolean;
  /** Smaller typography and preview (e.g. welcome sidecar). */
  compact?: boolean;
  /** Hide the in-progress skip button (e.g. welcome flow runs until max attempts). */
  hideSkip?: boolean;
  /** Called when getUserMedia fails (e.g. permission denied). */
  onCameraInitFailed?: () => void;
  onSuccess: (result: OcrResponse) => void;
  onFallback: () => void;
  onSkip: () => void;
}

const STATE_LABELS: Record<OcrCameraState, string> = {
  idle: '待機中',
  starting: 'カメラ起動中...',
  scanning: 'スキャン中...',
  submitting: '読み取り中...',
  success: '読み取り成功！',
  fallback: '読み取りできませんでした',
  error: 'カメラエラー',
};

const MODE_LABELS: Record<OcrMode, string> = {
  member_card: '会員証を読み取り範囲に映してください',
  handwriting: '文字を読み取り範囲に映してください',
};

export function OcrCameraView({
  mode,
  sessionId,
  autoStart = false,
  compact = false,
  hideSkip = false,
  onCameraInitFailed,
  onSuccess,
  onFallback,
  onSkip,
}: OcrCameraViewProps) {
  const handleFallback = useCallback(() => {
    onFallback();
  }, [onFallback]);

  const {
    state,
    videoRef,
    attempts,
    maxAttempts,
    lastResult,
    qualityInfo,
    startCamera,
    skip,
  } = useOcrCamera({
    mode,
    sessionId,
    onSuccess,
    onFallback: handleFallback,
  });

  const handleSkip = useCallback(() => {
    skip();
    onSkip();
  }, [skip, onSkip]);

  const autoStartedRef = useRef(false);
  useEffect(() => {
    if (!autoStart || autoStartedRef.current) {
      return;
    }
    autoStartedRef.current = true;
    void startCamera();
  }, [autoStart, startCamera]);

  const cameraErrorNotifiedRef = useRef(false);
  useEffect(() => {
    if (state !== 'error' || !onCameraInitFailed || cameraErrorNotifiedRef.current) {
      return;
    }
    cameraErrorNotifiedRef.current = true;
    onCameraInitFailed();
  }, [onCameraInitFailed, state]);

  const statusTitleClass = compact ? 'text-sm font-semibold' : 'text-lg font-medium';
  const modeHintClass = compact ? 'text-xs text-gray-500' : 'text-sm text-gray-500';
  const videoWrapClass = compact
    ? 'relative w-full max-w-[200px] overflow-hidden rounded-md bg-black'
    : 'relative w-full max-w-md overflow-hidden rounded-lg bg-black';
  const scanBoxClass = compact
    ? 'h-24 w-36 rounded-md border-2 border-white/60'
    : 'h-48 w-64 rounded-lg border-2 border-white/60';
  const spinnerClass = compact ? 'size-6 border-2' : 'size-8 border-4';

  return (
    <div className={cn('flex flex-col items-center', compact ? 'gap-2' : 'gap-4')}>
      {/* Status */}
      <div className="text-center">
        <p className={statusTitleClass}>{STATE_LABELS[state]}</p>
        <p className={modeHintClass}>{MODE_LABELS[mode]}</p>
      </div>

      {/* Camera preview */}
      <div className={videoWrapClass}>
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className="w-full"
        />

        {/* Scanning overlay */}
        {state === 'scanning' && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
            <div className={scanBoxClass} />
          </div>
        )}

        {/* Submitting indicator */}
        {state === 'submitting' && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/30">
            <div
              className={cn(
                'animate-spin rounded-full border-solid border-white/30 border-t-white',
                spinnerClass,
              )}
            />
          </div>
        )}
      </div>

      {/* Attempt counter */}
      {(state === 'scanning' || state === 'submitting') && (
        <div
          className={cn(
            'flex items-center text-gray-500',
            compact ? 'flex-col gap-0.5 text-xs' : 'gap-4 text-sm',
          )}
        >
          <span>
            試行 {attempts} / {maxAttempts}
          </span>
          {!compact && qualityInfo ? (
            <span>
              鮮明度: {Math.round(qualityInfo.laplacianVariance)} |
              明るさ: {Math.round(qualityInfo.brightness)}
            </span>
          ) : null}
        </div>
      )}

      {/* Success result */}
      {state === 'success' && lastResult && (
        <div
          className={cn(
            'w-full rounded-lg bg-green-50',
            compact ? 'max-w-[200px] p-2' : 'max-w-md p-4',
          )}
        >
          {mode === 'member_card' && lastResult.member_number && (
            <p
              className={cn(
                'text-center font-bold text-green-800',
                compact ? 'text-sm' : 'text-lg',
              )}
            >
              会員番号: {lastResult.member_number}
            </p>
          )}
          {mode === 'handwriting' && lastResult.recognized_text && (
            <p
              className={cn('text-center text-green-800', compact ? 'text-sm' : 'text-lg')}
            >
              {lastResult.recognized_text}
            </p>
          )}
          <p className="mt-1 text-center text-xs text-green-600">
            信頼度: {Math.round(lastResult.confidence * 100)}% |
            処理時間: {lastResult.processing_time_ms}ms
          </p>
        </div>
      )}

      {/* Action buttons */}
      <div className="flex flex-wrap justify-center gap-2">
        {state === 'idle' && !autoStart && (
          <button
            type="button"
            onClick={() => void startCamera()}
            className={cn(
              'rounded-lg bg-blue-600 text-white hover:bg-blue-700',
              compact ? 'px-3 py-2 text-xs' : 'px-6 py-3',
            )}
          >
            {mode === 'member_card' ? '会員証読み取り開始' : '筆談読み取り開始'}
          </button>
        )}

        {(state === 'scanning' || state === 'submitting') && !hideSkip && (
          <button
            type="button"
            onClick={handleSkip}
            className={cn(
              'rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-50',
              compact ? 'px-3 py-2 text-xs' : 'px-6 py-3',
            )}
          >
            スキップ
          </button>
        )}

        {state === 'fallback' && (
          <>
            <button
              type="button"
              onClick={() => void startCamera()}
              className={cn(
                'rounded-lg bg-blue-600 text-white hover:bg-blue-700',
                compact ? 'px-3 py-2 text-xs' : 'px-6 py-3',
              )}
            >
              再試行
            </button>
            <button
              type="button"
              onClick={handleSkip}
              className={cn(
                'rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-50',
                compact ? 'px-3 py-2 text-xs' : 'px-6 py-3',
              )}
            >
              手動入力へ
            </button>
          </>
        )}

        {state === 'error' && (
          <button
            type="button"
            onClick={() => void startCamera()}
            className={cn(
              'rounded-lg bg-blue-600 text-white hover:bg-blue-700',
              compact ? 'px-3 py-2 text-xs' : 'px-6 py-3',
            )}
          >
            再試行
          </button>
        )}
      </div>
    </div>
  );
}
