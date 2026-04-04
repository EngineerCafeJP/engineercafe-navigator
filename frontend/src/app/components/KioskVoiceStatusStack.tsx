'use client';

import { overlayLabels } from '@/lib/kiosk-labels';
import type { KioskPhase } from '@/lib/kiosk-constants';
import {
  Camera,
  Loader2,
  MessageSquare,
  TextQuote,
  Volume2,
  XCircle,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import type { VoiceLoadingPhase, VoiceSessionState } from './VoiceInterface';

export function KioskVoiceStatusStack({
  enabled,
  phase,
  labels,
  transcript,
  response,
  error,
  ocrStatus,
  isLoading,
  loadingPhase,
  sessionState,
}: {
  enabled: boolean;
  phase: KioskPhase;
  labels: (typeof overlayLabels)['ja'] | (typeof overlayLabels)['en'];
  transcript: string;
  response: string;
  error: string | null;
  ocrStatus: {
    kind: 'member_card' | 'handwriting' | 'error';
    text: string;
    visibleUntil: number;
  } | null;
  isLoading: boolean;
  loadingPhase: VoiceLoadingPhase;
  sessionState: VoiceSessionState;
}) {
  const [transcriptVisibleUntil, setTranscriptVisibleUntil] = useState<number>(0);
  const [responseVisibleUntil, setResponseVisibleUntil] = useState<number>(0);
  const [defaultPromptVisibleUntil, setDefaultPromptVisibleUntil] = useState<number>(0);
  const [errorVisibleUntil, setErrorVisibleUntil] = useState<number>(0);
  const [now, setNow] = useState<number>(Date.now());
  const previousSessionStateRef = useRef<VoiceSessionState>(sessionState);
  const previousPhaseRef = useRef<KioskPhase>(phase);

  useEffect(() => {
    if (!enabled) {
      setTranscriptVisibleUntil(0);
      setResponseVisibleUntil(0);
      setDefaultPromptVisibleUntil(0);
      setErrorVisibleUntil(0);
      previousPhaseRef.current = phase;
      return;
    }
    if (transcript.length > 0) {
      setTranscriptVisibleUntil(Date.now() + 5000);
    }
  }, [enabled, phase, transcript]);

  useEffect(() => {
    if (!enabled) {
      previousPhaseRef.current = phase;
      return;
    }

    const previousPhase = previousPhaseRef.current;
    if (phase === 'notice' || (previousPhase !== phase && phase === 'idle')) {
      setDefaultPromptVisibleUntil(Date.now() + 5000);
    }
    previousPhaseRef.current = phase;
  }, [enabled, phase]);

  useEffect(() => {
    if (!enabled) {
      previousSessionStateRef.current = sessionState;
      return;
    }

    if (previousSessionStateRef.current === 'speaking' && sessionState === 'idle' && response.length > 0) {
      setResponseVisibleUntil(Date.now() + 5000);
    }
    previousSessionStateRef.current = sessionState;
  }, [enabled, response.length, sessionState]);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    if (error) {
      setErrorVisibleUntil(Date.now() + 5000);
    }
    if (error && transcript.length > 0) {
      setTranscriptVisibleUntil(Date.now() + 5000);
    }
    if (error && response.length > 0) {
      setResponseVisibleUntil(Date.now() + 5000);
    }
  }, [enabled, error, response.length, transcript.length]);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    const timers: number[] = [];
    if (transcriptVisibleUntil > now) {
      timers.push(window.setTimeout(() => setNow(Date.now()), transcriptVisibleUntil - now));
    }
    if (responseVisibleUntil > now) {
      timers.push(window.setTimeout(() => setNow(Date.now()), responseVisibleUntil - now));
    }
    if (defaultPromptVisibleUntil > now) {
      timers.push(window.setTimeout(() => setNow(Date.now()), defaultPromptVisibleUntil - now));
    }
    if (errorVisibleUntil > now) {
      timers.push(window.setTimeout(() => setNow(Date.now()), errorVisibleUntil - now));
    }
    if (ocrStatus && ocrStatus.visibleUntil > now) {
      timers.push(window.setTimeout(() => setNow(Date.now()), ocrStatus.visibleUntil - now));
    }
    return () => {
      timers.forEach((timerId) => window.clearTimeout(timerId));
    };
  }, [
    defaultPromptVisibleUntil,
    enabled,
    errorVisibleUntil,
    now,
    ocrStatus,
    responseVisibleUntil,
    transcriptVisibleUntil,
  ]);

  if (!enabled) {
    return null;
  }

  const isSttLoading = isLoading && loadingPhase === 'stt';
  const isTtsSynthesizing =
    isLoading && response.length > 0 && sessionState !== 'speaking';
  const isErrorVisible = Boolean(error) && errorVisibleUntil > now;
  const isOcrStatusVisible = Boolean(ocrStatus && ocrStatus.visibleUntil > now);
  const isDefaultPromptVisible =
    response.length === 0 &&
    sessionState === 'idle' &&
    defaultPromptVisibleUntil > now;
  const displayResponse = response || (isDefaultPromptVisible ? labels.defaultPrompt : '');
  const isResponseVisible =
    displayResponse.length > 0 &&
    (sessionState === 'speaking' || responseVisibleUntil > now || isDefaultPromptVisible);
  const isTranscriptVisible =
    transcript.length > 0 && !isSttLoading && transcriptVisibleUntil > now;

  if (!isSttLoading && !isTtsSynthesizing && !isTranscriptVisible && !isResponseVisible && !isErrorVisible && !isOcrStatusVisible) {
    return null;
  }

  return (
    <div className="w-full space-y-2">
      {isOcrStatusVisible && ocrStatus ? (
        <div className="flex w-full items-center gap-2 rounded-xl border border-white/30 bg-black/35 px-4 py-2 text-sm font-medium text-white/95 shadow-sm backdrop-blur-sm">
          {ocrStatus.kind === 'error' ? (
            <XCircle className="size-4 shrink-0 text-rose-300" />
          ) : ocrStatus.kind === 'handwriting' ? (
            <MessageSquare className="size-4 shrink-0" />
          ) : (
            <Camera className="size-4 shrink-0" />
          )}
          <span>{ocrStatus.text}</span>
        </div>
      ) : null}
      {isSttLoading ? (
        <div className="flex w-full items-center gap-2 rounded-xl border border-white/30 bg-black/35 px-4 py-2 text-sm font-medium text-white/95 shadow-sm backdrop-blur-sm">
          <Loader2 className="size-4 shrink-0 animate-spin" />
          <span>{labels.sttReading}</span>
        </div>
      ) : null}
      {isTranscriptVisible ? (
        <div className="flex w-full items-center gap-2 rounded-xl border border-white/30 bg-black/35 px-4 py-2 text-sm font-medium text-white/95 shadow-sm backdrop-blur-sm">
          <TextQuote className="size-4 shrink-0" />
          <span>
            {labels.transcriptLabel}: {transcript}
          </span>
        </div>
      ) : null}
      {isErrorVisible ? (
        <div className="flex w-full items-center gap-2 rounded-xl border border-rose-300/45 bg-rose-700/35 px-4 py-2 text-sm font-medium text-rose-50 shadow-sm backdrop-blur-sm">
          <XCircle className="size-4 shrink-0" />
          <span>{error}</span>
        </div>
      ) : null}
      {isTtsSynthesizing ? (
        <div className="flex w-full items-center gap-2 rounded-xl border border-white/30 bg-black/35 px-4 py-2 text-sm font-medium text-white/95 shadow-sm backdrop-blur-sm">
          <Loader2 className="size-4 shrink-0 animate-spin" />
          <span>{labels.ttsSynthesizing}</span>
        </div>
      ) : null}
      {isResponseVisible ? (
        <div
          className="flex w-full items-center gap-2 rounded-xl border border-white/30 bg-black/35 px-4 py-2 text-sm font-medium text-white/95 shadow-sm backdrop-blur-sm"
          data-testid="response-bubble"
        >
          <Volume2 className="size-4 shrink-0" />
          <span data-testid="response-text">
            {response ? `${labels.responseLabel}: ${response}` : displayResponse}
          </span>
        </div>
      ) : null}
    </div>
  );
}
