/**
 * OcrCameraView — Issue #314
 *
 * Camera preview with OCR scanning overlay.
 * Shows quality indicators, attempt count, and scanning status.
 */

'use client';

import { useCallback } from 'react';

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

  return (
    <div className="flex flex-col items-center gap-4">
      {/* Status */}
      <div className="text-center">
        <p className="text-lg font-medium">{STATE_LABELS[state]}</p>
        <p className="text-sm text-gray-500">{MODE_LABELS[mode]}</p>
      </div>

      {/* Camera preview */}
      <div className="relative w-full max-w-md overflow-hidden rounded-lg bg-black">
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
            <div className="h-48 w-64 rounded-lg border-2 border-white/60" />
          </div>
        )}

        {/* Submitting indicator */}
        {state === 'submitting' && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/30">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-white/30 border-t-white" />
          </div>
        )}
      </div>

      {/* Attempt counter */}
      {(state === 'scanning' || state === 'submitting') && (
        <div className="flex items-center gap-4 text-sm text-gray-500">
          <span>試行 {attempts} / {maxAttempts}</span>
          {qualityInfo && (
            <span>
              鮮明度: {Math.round(qualityInfo.laplacianVariance)} |
              明るさ: {Math.round(qualityInfo.brightness)}
            </span>
          )}
        </div>
      )}

      {/* Success result */}
      {state === 'success' && lastResult && (
        <div className="w-full max-w-md rounded-lg bg-green-50 p-4">
          {mode === 'member_card' && lastResult.member_number && (
            <p className="text-center text-lg font-bold text-green-800">
              会員番号: {lastResult.member_number}
            </p>
          )}
          {mode === 'handwriting' && lastResult.recognized_text && (
            <p className="text-center text-lg text-green-800">
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
      <div className="flex gap-3">
        {state === 'idle' && (
          <button
            onClick={() => void startCamera()}
            className="rounded-lg bg-blue-600 px-6 py-3 text-white hover:bg-blue-700"
          >
            {mode === 'member_card' ? '会員証読み取り開始' : '筆談読み取り開始'}
          </button>
        )}

        {(state === 'scanning' || state === 'submitting') && (
          <button
            onClick={handleSkip}
            className="rounded-lg border border-gray-300 px-6 py-3 text-gray-600 hover:bg-gray-50"
          >
            スキップ
          </button>
        )}

        {state === 'fallback' && (
          <>
            <button
              onClick={() => void startCamera()}
              className="rounded-lg bg-blue-600 px-6 py-3 text-white hover:bg-blue-700"
            >
              再試行
            </button>
            <button
              onClick={handleSkip}
              className="rounded-lg border border-gray-300 px-6 py-3 text-gray-600 hover:bg-gray-50"
            >
              手動入力へ
            </button>
          </>
        )}

        {state === 'error' && (
          <button
            onClick={() => void startCamera()}
            className="rounded-lg bg-blue-600 px-6 py-3 text-white hover:bg-blue-700"
          >
            再試行
          </button>
        )}
      </div>
    </div>
  );
}
