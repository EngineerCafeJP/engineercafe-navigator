/**
 * useOcrCamera — Issue #314
 *
 * Camera control hook for OCR with:
 * - MediaStream management
 * - Quality-filtered frame capture (200ms scan interval)
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
  maxAttempts: number;
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
const SCAN_LOOP_INTERVAL_MS = 200;
const SELECTED_CAMERA_DEVICE_ID_STORAGE_KEY = 'kiosk-camera-device-id';

export function useOcrCamera(options: UseOcrCameraOptions): UseOcrCameraReturn {
  const {
    mode,
    sessionId = '',
    maxAttempts = DEFAULT_MAX_ATTEMPTS,
    submitIntervalMs = DEFAULT_SUBMIT_INTERVAL_MS,
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
  const scanLoopTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastSubmitTimeRef = useRef<number>(0);
  const isSubmittingRef = useRef(false);
  const attemptsRef = useRef(0);

  // Stable refs for callbacks to avoid stale closures (HIGH-1 fix)
  const onSuccessRef = useRef(options.onSuccess);
  const onFallbackRef = useRef(options.onFallback);
  useEffect(() => {
    onSuccessRef.current = options.onSuccess;
  }, [options.onSuccess]);
  useEffect(() => {
    onFallbackRef.current = options.onFallback;
  }, [options.onFallback]);

  // Reuse a single offscreen canvas to avoid GC pressure (HIGH-4 fix)
  const qualityCanvasRef = useRef<HTMLCanvasElement | null>(null);

  // Cleanup
  const stopCamera = useCallback(() => {
    if (scanLoopTimerRef.current) {
      clearInterval(scanLoopTimerRef.current);
      scanLoopTimerRef.current = null;
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

    // Lazy-create reusable canvas
    if (!qualityCanvasRef.current) {
      qualityCanvasRef.current = document.createElement('canvas');
    }

    // Quality check runs every 200ms regardless of submit cooldown
    const quality = checkFrameQuality(video, qualityCanvasRef.current);
    setQualityInfo({
      laplacianVariance: quality.laplacianVariance,
      brightness: quality.brightness,
    });

    if (!quality.passed) return;

    // Submit cooldown: only send API request every 2 seconds
    const now = Date.now();
    if (now - lastSubmitTimeRef.current < submitIntervalMs) return;

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

      const isSuccess = result.success && result.confidence >= confidenceThreshold;

      if (isSuccess) {
        setState('success');
        stopCamera();
        onSuccessRef.current?.(result);
      } else if (currentAttempt >= maxAttempts) {
        setState('fallback');
        stopCamera();
        onFallbackRef.current?.();
      } else {
        setState('scanning');
      }
    } catch {
      if (currentAttempt >= maxAttempts) {
        setState('fallback');
        stopCamera();
        onFallbackRef.current?.();
      } else {
        setState('scanning');
      }
    } finally {
      isSubmittingRef.current = false;
    }
  }, [mode, sessionId, maxAttempts, submitIntervalMs, confidenceThreshold, stopCamera]);

  // Start camera
  const startCamera = useCallback(async () => {
    setState('starting');
    attemptsRef.current = 0;
    setAttempts(0);
    setLastResult(null);

    try {
      const selectedDeviceId =
        typeof window !== 'undefined'
          ? window.localStorage.getItem(SELECTED_CAMERA_DEVICE_ID_STORAGE_KEY)
          : null;
      const video =
        selectedDeviceId && selectedDeviceId !== 'default'
          ? {
              deviceId: { exact: selectedDeviceId },
              width: { ideal: 1280 },
              height: { ideal: 720 },
            }
          : { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } };
      const stream = await navigator.mediaDevices.getUserMedia({
        video,
        audio: false,
      });
      streamRef.current = stream;

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }

      setState('scanning');

      // Start scan loop (quality check + submit)
      scanLoopTimerRef.current = setInterval(() => {
        void submitFrame();
      }, SCAN_LOOP_INTERVAL_MS);
    } catch {
      setState('error');
    }
  }, [submitFrame]);

  // Skip button
  const skip = useCallback(() => {
    stopCamera();
    setState('fallback');
    onFallbackRef.current?.();
  }, [stopCamera]);

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
    maxAttempts,
    lastResult,
    qualityInfo,
    startCamera,
    stopCamera,
    skip,
  };
}
