/**
 * useOcrCamera — Issue #314
 *
 * Camera control hook for OCR with:
 * - MediaStream management
 * - Quality-filtered frame capture (200ms analysis interval)
 * - API submission at 2-second intervals (quality-passing frames only)
 * - Max 8 attempts → fallback
 * - State management for OCR flow
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { type OcrMode, type OcrResponse, submitOcrImage } from '@/lib/api/ocr-api';
import { captureFrame, checkFrameQuality } from '@/lib/image-quality-filter';

export type OcrCameraState =
  | 'idle'
  | 'starting'
  | 'scanning'
  | 'submitting'
  | 'success'
  | 'fallback'
  | 'error';

export interface UseOcrCameraOptions {
  mode: OcrMode;
  sessionId?: string;
  maxAttempts?: number;
  submitIntervalMs?: number;
  confidenceThreshold?: number;
  onSuccess?: (result: OcrResponse) => void;
  onFallback?: () => void;
}

export interface UseOcrCameraReturn {
  state: OcrCameraState;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  attempts: number;
  lastResult: OcrResponse | null;
  qualityInfo: { laplacianVariance: number; brightness: number } | null;
  startCamera: () => Promise<void>;
  stopCamera: () => void;
  skip: () => void;
}

const DEFAULT_MAX_ATTEMPTS = 8;
const DEFAULT_SUBMIT_INTERVAL_MS = 2000;
const DEFAULT_CONFIDENCE_THRESHOLD_MEMBER = 0.8;
const DEFAULT_CONFIDENCE_THRESHOLD_HANDWRITING = 0.7;
const QUALITY_CHECK_INTERVAL_MS = 200;

export function useOcrCamera(options: UseOcrCameraOptions): UseOcrCameraReturn {
  const {
    mode,
    sessionId = '',
    maxAttempts = DEFAULT_MAX_ATTEMPTS,
    submitIntervalMs = DEFAULT_SUBMIT_INTERVAL_MS,
    onSuccess,
    onFallback,
  } = options;

  const confidenceThreshold =
    options.confidenceThreshold ??
    (mode === 'member_card'
      ? DEFAULT_CONFIDENCE_THRESHOLD_MEMBER
      : DEFAULT_CONFIDENCE_THRESHOLD_HANDWRITING);

  const [state, setState] = useState<OcrCameraState>('idle');
  const [attempts, setAttempts] = useState(0);
  const [lastResult, setLastResult] = useState<OcrResponse | null>(null);
  const [qualityInfo, setQualityInfo] = useState<{
    laplacianVariance: number;
    brightness: number;
  } | null>(null);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const qualityTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const submitTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastSubmitTimeRef = useRef<number>(0);
  const isSubmittingRef = useRef(false);
  const attemptsRef = useRef(0);

  // Cleanup
  const stopCamera = useCallback(() => {
    if (qualityTimerRef.current) {
      clearInterval(qualityTimerRef.current);
      qualityTimerRef.current = null;
    }
    if (submitTimerRef.current) {
      clearInterval(submitTimerRef.current);
      submitTimerRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
  }, []);

  // Submit a quality-passing frame
  const submitFrame = useCallback(async () => {
    if (isSubmittingRef.current) return;
    if (attemptsRef.current >= maxAttempts) return;

    const video = videoRef.current;
    if (!video) return;

    const now = Date.now();
    if (now - lastSubmitTimeRef.current < submitIntervalMs) return;

    // Quality check
    const quality = checkFrameQuality(video);
    setQualityInfo({
      laplacianVariance: quality.laplacianVariance,
      brightness: quality.brightness,
    });

    if (!quality.passed) return;

    // Capture frame
    const frameData = captureFrame(video);
    if (!frameData) return;

    isSubmittingRef.current = true;
    lastSubmitTimeRef.current = now;
    setState('submitting');
    const currentAttempt = attemptsRef.current + 1;
    attemptsRef.current = currentAttempt;
    setAttempts(currentAttempt);

    try {
      const result = await submitOcrImage({
        image_data: frameData,
        mode,
        session_id: sessionId,
      });
      setLastResult(result);

      const isSuccess =
        result.success && result.confidence >= confidenceThreshold;

      if (isSuccess) {
        setState('success');
        stopCamera();
        onSuccess?.(result);
      } else if (currentAttempt >= maxAttempts) {
        setState('fallback');
        stopCamera();
        onFallback?.();
      } else {
        setState('scanning');
      }
    } catch {
      if (currentAttempt >= maxAttempts) {
        setState('fallback');
        stopCamera();
        onFallback?.();
      } else {
        setState('scanning');
      }
    } finally {
      isSubmittingRef.current = false;
    }
  }, [
    mode,
    sessionId,
    maxAttempts,
    submitIntervalMs,
    confidenceThreshold,
    stopCamera,
    onSuccess,
    onFallback,
  ]);

  // Start camera
  const startCamera = useCallback(async () => {
    setState('starting');
    attemptsRef.current = 0;
    setAttempts(0);
    setLastResult(null);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      streamRef.current = stream;

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }

      setState('scanning');

      // Start quality check + submit loop
      submitTimerRef.current = setInterval(() => {
        void submitFrame();
      }, QUALITY_CHECK_INTERVAL_MS);
    } catch {
      setState('error');
    }
  }, [submitFrame]);

  // Skip button
  const skip = useCallback(() => {
    stopCamera();
    setState('fallback');
    onFallback?.();
  }, [stopCamera, onFallback]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopCamera();
    };
  }, [stopCamera]);

  return {
    state,
    videoRef,
    attempts,
    lastResult,
    qualityInfo,
    startCamera,
    stopCamera,
    skip,
  };
}
