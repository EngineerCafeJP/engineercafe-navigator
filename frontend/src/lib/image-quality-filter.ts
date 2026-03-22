/**
 * Image Quality Filter — Issue #314
 *
 * Lightweight client-side quality filter for OCR frames.
 * - Laplacian variance for blur detection (~5ms/frame)
 * - Brightness check (~2ms/frame)
 *
 * References:
 * - https://pyimagesearch.com/2015/09/07/blur-detection-with-opencv/
 * - https://medium.com/revolut/canvas-based-javascript-blur-detection-b92ab1075acf
 */

export interface QualityCheckResult {
  passed: boolean;
  laplacianVariance: number;
  brightness: number;
  reasons: string[];
}

/** Default thresholds (tunable per Issue #314 spec) */
const BLUR_THRESHOLD = 100;
const BRIGHTNESS_MIN = 40;
const BRIGHTNESS_MAX = 220;

/**
 * Check image quality from a video element frame.
 *
 * 1. Draw video frame to offscreen canvas
 * 2. Get grayscale pixel data
 * 3. Compute Laplacian variance (blur detection)
 * 4. Compute mean brightness
 */
export function checkFrameQuality(
  video: HTMLVideoElement,
  canvas?: HTMLCanvasElement,
): QualityCheckResult {
  const reasons: string[] = [];

  const w = video.videoWidth;
  const h = video.videoHeight;
  if (w === 0 || h === 0) {
    return { passed: false, laplacianVariance: 0, brightness: 0, reasons: ['no_video'] };
  }

  // Use provided canvas or create offscreen
  const cvs = canvas ?? document.createElement('canvas');
  cvs.width = w;
  cvs.height = h;
  const ctx = cvs.getContext('2d', { willReadFrequently: true });
  if (!ctx) {
    return { passed: false, laplacianVariance: 0, brightness: 0, reasons: ['no_canvas_context'] };
  }

  ctx.drawImage(video, 0, 0, w, h);
  const imageData = ctx.getImageData(0, 0, w, h);
  const data = imageData.data; // RGBA

  // Convert to grayscale
  const gray = new Float32Array(w * h);
  let brightnessSum = 0;
  for (let i = 0; i < w * h; i++) {
    const r = data[i * 4];
    const g = data[i * 4 + 1];
    const b = data[i * 4 + 2];
    const val = 0.299 * r + 0.587 * g + 0.114 * b;
    gray[i] = val;
    brightnessSum += val;
  }

  const brightness = brightnessSum / (w * h);

  // Laplacian kernel: [0, 1, 0], [1, -4, 1], [0, 1, 0]
  let lapSum = 0;
  let lapSqSum = 0;
  let lapCount = 0;

  for (let y = 1; y < h - 1; y++) {
    for (let x = 1; x < w - 1; x++) {
      const idx = y * w + x;
      const lap =
        gray[idx - w] +
        gray[idx - 1] +
        gray[idx + 1] +
        gray[idx + w] -
        4 * gray[idx];
      lapSum += lap;
      lapSqSum += lap * lap;
      lapCount++;
    }
  }

  const lapMean = lapSum / lapCount;
  const laplacianVariance = lapSqSum / lapCount - lapMean * lapMean;

  // Check thresholds
  if (laplacianVariance < BLUR_THRESHOLD) {
    reasons.push('too_blurry');
  }
  if (brightness < BRIGHTNESS_MIN) {
    reasons.push('too_dark');
  }
  if (brightness > BRIGHTNESS_MAX) {
    reasons.push('too_bright');
  }

  return {
    passed: reasons.length === 0,
    laplacianVariance,
    brightness,
    reasons,
  };
}

/**
 * Capture a frame from video as JPEG base64 data URI.
 * Resizes to maxWidth maintaining aspect ratio.
 */
export function captureFrame(
  video: HTMLVideoElement,
  maxWidth: number = 640,
  quality: number = 0.85,
): string | null {
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  if (vw === 0 || vh === 0) return null;

  const scale = vw > maxWidth ? maxWidth / vw : 1;
  const w = Math.round(vw * scale);
  const h = Math.round(vh * scale);

  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;

  ctx.drawImage(video, 0, 0, w, h);
  return canvas.toDataURL('image/jpeg', quality);
}
