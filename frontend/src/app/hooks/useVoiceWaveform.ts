'use client';

import { useEffect, useMemo, useState } from 'react';

export interface UseVoiceWaveformOptions {
  stream: MediaStream | null;
  enabled?: boolean;
  barCount?: number;
  fftSize?: number;
  smoothingTimeConstant?: number;
}

export interface UseVoiceWaveformResult {
  levels: number[];
  averageLevel: number;
  isAnalyzing: boolean;
  isSupported: boolean;
  error: string | null;
}

const DEFAULT_BAR_COUNT = 12;
const DEFAULT_FFT_SIZE = 512;
const DEFAULT_SMOOTHING = 0.7;

const createLevels = (barCount: number): number[] =>
  Array.from({ length: barCount }, () => 0);

const getAudioContextConstructor = (): typeof AudioContext | null => {
  if (typeof window === 'undefined') {
    return null;
  }

  const audioWindow = window as Window &
    typeof globalThis & {
      webkitAudioContext?: typeof AudioContext;
    };

  return audioWindow.AudioContext ?? audioWindow.webkitAudioContext ?? null;
};

export function useVoiceWaveform({
  stream,
  enabled = true,
  barCount = DEFAULT_BAR_COUNT,
  fftSize = DEFAULT_FFT_SIZE,
  smoothingTimeConstant = DEFAULT_SMOOTHING,
}: UseVoiceWaveformOptions): UseVoiceWaveformResult {
  const [levels, setLevels] = useState<number[]>(() => createLevels(barCount));
  const [averageLevel, setAverageLevel] = useState(0);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isSupported = useMemo(() => getAudioContextConstructor() !== null, []);

  useEffect(() => {
    setLevels(createLevels(barCount));
  }, [barCount]);

  useEffect(() => {
    if (!enabled || !stream) {
      setIsAnalyzing(false);
      setAverageLevel(0);
      setLevels(createLevels(barCount));
      return;
    }

    const AudioContextConstructor = getAudioContextConstructor();
    if (!AudioContextConstructor) {
      setError('AudioContext is not supported in this browser');
      setIsAnalyzing(false);
      return;
    }

    let isDisposed = false;
    let animationFrameId: number | null = null;

    const audioContext = new AudioContextConstructor();
    const source = audioContext.createMediaStreamSource(stream);
    const analyser = audioContext.createAnalyser();
    const data = new Uint8Array(analyser.frequencyBinCount);

    analyser.fftSize = fftSize;
    analyser.smoothingTimeConstant = smoothingTimeConstant;
    source.connect(analyser);

    setIsAnalyzing(true);
    setError(null);

    const analyze = () => {
      if (isDisposed) {
        return;
      }

      analyser.getByteFrequencyData(data);

      const bucketSize = Math.max(Math.floor(data.length / barCount), 1);
      const nextLevels = Array.from({ length: barCount }, (_, bucketIndex) => {
        const start = bucketIndex * bucketSize;
        const end = Math.min(start + bucketSize, data.length);
        let sum = 0;

        for (let index = start; index < end; index += 1) {
          sum += data[index];
        }

        const size = Math.max(end - start, 1);
        return sum / size / 255;
      });

      const nextAverageLevel =
        nextLevels.reduce((total, level) => total + level, 0) / nextLevels.length;

      setLevels(nextLevels);
      setAverageLevel(nextAverageLevel);
      animationFrameId = window.requestAnimationFrame(analyze);
    };

    if (audioContext.state === 'suspended') {
      void audioContext.resume();
    }

    animationFrameId = window.requestAnimationFrame(analyze);

    return () => {
      isDisposed = true;
      setIsAnalyzing(false);

      if (animationFrameId !== null) {
        window.cancelAnimationFrame(animationFrameId);
      }

      source.disconnect();
      analyser.disconnect();
      void audioContext.close();
    };
  }, [barCount, enabled, fftSize, smoothingTimeConstant, stream]);

  return {
    levels,
    averageLevel,
    isAnalyzing,
    isSupported,
    error,
  };
}
