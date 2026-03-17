'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  extractRecognitionTranscript,
  getSpeechRecognitionConstructor,
  normalizeSpeechText,
  type BrowserSpeechRecognition,
  type BrowserSpeechRecognitionErrorEvent,
  type BrowserSpeechRecognitionEvent,
} from './browser-speech';

export interface WakeWordMatch {
  word: string;
  transcript: string;
  detectedAt: number;
}

export interface UseWakeWordOptions {
  wakeWords: string[];
  enabled?: boolean;
  language?: string;
  continuous?: boolean;
  interimResults?: boolean;
  restartDelayMs?: number;
  debounceMs?: number;
  onWakeWord?: (match: WakeWordMatch) => void;
}

export interface UseWakeWordResult {
  isSupported: boolean;
  isListening: boolean;
  error: string | null;
  lastTranscript: string;
  detectedWakeWord: WakeWordMatch | null;
  startListening: () => boolean;
  stopListening: () => void;
  clearDetectedWakeWord: () => void;
}

const DEFAULT_RESTART_DELAY_MS = 400;
const DEFAULT_DEBOUNCE_MS = 1_500;

export function useWakeWord({
  wakeWords,
  enabled = true,
  language = 'ja-JP',
  continuous = true,
  interimResults = true,
  restartDelayMs = DEFAULT_RESTART_DELAY_MS,
  debounceMs = DEFAULT_DEBOUNCE_MS,
  onWakeWord,
}: UseWakeWordOptions): UseWakeWordResult {
  const recognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const restartTimeoutRef = useRef<number | null>(null);
  const shouldRunRef = useRef(enabled);
  const manualStopRef = useRef(false);
  const lastDetectionRef = useRef<WakeWordMatch | null>(null);
  const startListeningRef = useRef<() => boolean>(() => false);

  const [isSupported, setIsSupported] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastTranscript, setLastTranscript] = useState('');
  const [detectedWakeWord, setDetectedWakeWord] = useState<WakeWordMatch | null>(null);

  const normalizedWakeWordsRef = useRef<Array<{ normalized: string; original: string }>>([]);
  normalizedWakeWordsRef.current = wakeWords
    .map((wakeWord) => ({
      normalized: normalizeSpeechText(wakeWord),
      original: wakeWord,
    }))
    .filter((wakeWord) => wakeWord.normalized.length > 0);

  const clearRestartTimer = useCallback(() => {
    if (restartTimeoutRef.current !== null) {
      window.clearTimeout(restartTimeoutRef.current);
      restartTimeoutRef.current = null;
    }
  }, []);

  const clearDetectedWakeWord = useCallback(() => {
    setDetectedWakeWord(null);
  }, []);

  const disposeRecognition = useCallback(() => {
    const recognition = recognitionRef.current;
    if (!recognition) {
      return;
    }

    recognition.onstart = null;
    recognition.onend = null;
    recognition.onerror = null;
    recognition.onresult = null;
    recognition.abort();
    recognitionRef.current = null;
  }, []);

  const handleResult = useCallback(
    (event: BrowserSpeechRecognitionEvent) => {
      const transcript = extractRecognitionTranscript(event);
      if (!transcript) {
        return;
      }

      setLastTranscript(transcript);

      const normalizedTranscript = normalizeSpeechText(transcript);
      const matchedWord = normalizedWakeWordsRef.current.find(({ normalized }) =>
        normalizedTranscript.includes(normalized),
      );

      if (!matchedWord) {
        return;
      }

      const now = Date.now();
      const lastDetection = lastDetectionRef.current;
      if (lastDetection && now - lastDetection.detectedAt < debounceMs) {
        return;
      }

      const match: WakeWordMatch = {
        word: matchedWord.original,
        transcript,
        detectedAt: now,
      };

      lastDetectionRef.current = match;
      setDetectedWakeWord(match);
      onWakeWord?.(match);
    },
    [debounceMs, onWakeWord],
  );

  const createRecognition = useCallback(() => {
    const RecognitionConstructor = getSpeechRecognitionConstructor();
    if (!RecognitionConstructor) {
      setIsSupported(false);
      return null;
    }

    setIsSupported(true);

    const recognition = new RecognitionConstructor();
    recognition.continuous = continuous;
    recognition.interimResults = interimResults;
    recognition.lang = language;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      setIsListening(true);
      setError(null);
    };

    recognition.onresult = (event) => {
      handleResult(event);
    };

    recognition.onerror = (event: BrowserSpeechRecognitionErrorEvent) => {
      if (manualStopRef.current && event.error === 'aborted') {
        return;
      }

      setError(event.message || event.error || 'Wake word recognition failed');
    };

    recognition.onend = () => {
      setIsListening(false);
      recognitionRef.current = null;

      if (!shouldRunRef.current || manualStopRef.current) {
        return;
      }

      clearRestartTimer();
      restartTimeoutRef.current = window.setTimeout(() => {
        startListeningRef.current();
      }, restartDelayMs);
    };

    return recognition;
  }, [
    clearRestartTimer,
    continuous,
    handleResult,
    interimResults,
    language,
    restartDelayMs,
  ]);

  const startListening = useCallback((): boolean => {
    shouldRunRef.current = true;
    manualStopRef.current = false;

    if (!enabled) {
      return false;
    }

    if (recognitionRef.current || isListening) {
      return true;
    }

    const recognition = createRecognition();
    if (!recognition) {
      return false;
    }

    recognitionRef.current = recognition;

    try {
      recognition.start();
      return true;
    } catch (startError) {
      recognitionRef.current = null;
      setError(
        startError instanceof Error
          ? startError.message
          : 'Unable to start wake word recognition',
      );
      return false;
    }
  }, [createRecognition, enabled, isListening]);

  useEffect(() => {
    startListeningRef.current = startListening;
  }, [startListening]);

  const stopListening = useCallback(() => {
    shouldRunRef.current = false;
    manualStopRef.current = true;
    clearRestartTimer();
    recognitionRef.current?.stop();
  }, [clearRestartTimer]);

  useEffect(() => {
    setIsSupported(getSpeechRecognitionConstructor() !== null);
  }, []);

  useEffect(() => {
    shouldRunRef.current = enabled;

    if (!enabled) {
      stopListening();
      return;
    }

    return () => {
      clearRestartTimer();
      disposeRecognition();
    };
  }, [clearRestartTimer, disposeRecognition, enabled, stopListening]);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    if (!isListening && shouldRunRef.current) {
      startListening();
    }
  }, [enabled, isListening, startListening]);

  return {
    isSupported,
    isListening,
    error,
    lastTranscript,
    detectedWakeWord,
    startListening,
    stopListening,
    clearDetectedWakeWord,
  };
}
