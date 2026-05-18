'use client';

import {
  registerAudioContextSuspensionListener,
  unlockAudioForUserGesture,
} from '@/lib/audio/audio-interaction-manager';
import {
  getTapToEnableAudioMessage,
  markAudioUserInteraction,
} from '@/lib/audio/audio-user-interaction-gate';
import { formatError } from '@/lib/error-messages';
import {
  interruptVoiceSession,
  sendVoiceClientTelemetry,
  speechToText,
} from '@/lib/api/voice-client';
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useVoiceSessionController } from '../hooks/useVoiceSessionController';
import { VoiceRecorder } from '@/lib/voice-recorder';
import { cancelSttWarmup, sendSttWarmup } from '@/lib/stt-warmup';
import { VoiceInterfaceDefaultUI } from './voice-interface/VoiceInterfaceDefaultUI';
import {
  DEFAULT_WAKE_WORDS,
  LOADING_LABELS,
} from './voice-interface/constants';
import type {
  VoiceInterfaceMetadata,
  VoiceInterfaceProps,
  VoiceInterfaceRenderProps,
  VoiceLoadingPhase,
  VoiceSessionState,
  VoiceTimingTelemetry,
  VoiceUiLockState,
} from './voice-interface/types';
import {
  clearVisitorId,
  createSessionId,
  elapsedMs,
  getOrCreateVisitorId,
  normalizeSessionState,
  toBase64,
  toLocale,
} from './voice-interface/utils';
import { useVoiceAudioPlayback } from './voice-interface/useVoiceAudioPlayback';
import { useVoiceTurnProcessor } from './voice-interface/useVoiceTurnProcessor';

export type {
  VoiceInterfaceMetadata,
  VoiceInterfaceProps,
  VoiceInterfaceRenderProps,
  VoiceLoadingPhase,
  VoiceSessionState,
  VoiceUiLockState,
} from './voice-interface/types';

export default function VoiceInterface({
  onLanguageChange,
  layout = 'vertical',
  language = 'ja',
  wakeWordEnabled = true,
  autoResumeListeningAfterAssistant = true,
  autoGreeting = false,
  onVisemeControl,
  children,
  showDefaultUI,
  className,
  onMetadataChange,
  onAssistantPlaybackStart,
  onAssistantPlaybackEnd,
  onVoiceTurnThinkingVisual,
  onVoiceTurnAssistantSpeakingVisual,
  onSlideAgentResponse,
}: VoiceInterfaceProps) {
  const skipAssistantTurnAutoResume = !autoResumeListeningAfterAssistant;
  const [currentLanguage, setCurrentLanguage] = useState<'ja' | 'en'>(language);
  const [volume, setVolumeState] = useState(0.8);
  const [isMuted, setIsMuted] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [response, setResponse] = useState('');
  const [metadata, setMetadata] = useState<VoiceInterfaceMetadata | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadingMessage, setLoadingMessage] = useState('');
  const [loadingPhase, setLoadingPhase] = useState<VoiceLoadingPhase>(null);
  const [exclusiveUiLock, setExclusiveUiLock] = useState(false);
  const [mediaStream, setMediaStream] = useState<MediaStream | null>(null);

  const sessionIdRef = useRef(createSessionId());
  const visitorIdRef = useRef<string>('anonymous');
  const recorderRef = useRef<VoiceRecorder | null>(null);
  const lastRecorderInitErrorRef = useRef<Error | null>(null);
  const shouldDiscardNextAudioRef = useRef(false);
  const requestAbortRef = useRef<AbortController | null>(null);
  const isRecordingRef = useRef(false);
  const isStartingRecorderRef = useRef(false);
  const shouldListenRef = useRef(false);
  const isStoppingRecorderRef = useRef(false);
  const voiceTurnInProgressRef = useRef(false);
  const forceSkipAutoResumeRef = useRef(false);
  const fastFillerTimerRef = useRef<number | null>(null);
  const playAudioFallbackNoticeRef = useRef<() => void>(() => {});

  useEffect(() => {
    visitorIdRef.current = getOrCreateVisitorId();
  }, []);

  useEffect(() => {
    setCurrentLanguage(language);
  }, [language]);

  useEffect(() => {
    onMetadataChange?.(metadata);
  }, [metadata, onMetadataChange]);

  const cancelPendingRequest = useCallback(() => {
    requestAbortRef.current?.abort();
    requestAbortRef.current = null;
  }, []);

  const emitVoiceTelemetry = useCallback(
    (event: string, phase: string, metrics: VoiceTimingTelemetry = {}) => {
      const sessionId = sessionIdRef.current;
      void sendVoiceClientTelemetry(
        {
          event,
          phase,
          sessionId,
          userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : undefined,
          timestamp: new Date().toISOString(),
          ...metrics,
        },
        { keepalive: true },
      ).catch(() => {
        /* telemetry must not affect the voice turn */
      });
    },
    [],
  );

  const requestBackendInterrupt = useCallback(() => {
    const sessionId = sessionIdRef.current;
    if (!sessionId) {
      return;
    }

    void interruptVoiceSession(
      {
        sessionId,
        language: currentLanguage,
      },
      { keepalive: true },
    ).catch(() => {
      /* best-effort interrupt */
    });
  }, [currentLanguage]);

  const cancelFastFiller = useCallback(() => {
    if (fastFillerTimerRef.current !== null) {
      window.clearTimeout(fastFillerTimerRef.current);
      fastFillerTimerRef.current = null;
    }
  }, []);

  const scheduleFastFiller = useCallback(() => {
    cancelFastFiller();
  }, [cancelFastFiller]);

  const handleVoiceControllerTransition = useCallback(
    (transition: {
      from: string;
      to: string;
      characterState: string;
      isConversationActive: boolean;
      shouldListen: boolean;
    }) => {
      emitVoiceTelemetry('voice_controller_state_transition', 'state', transition);
    },
    [emitVoiceTelemetry],
  );

  const voiceController = useVoiceSessionController({
    enabled: true,
    wakeWordEnabled,
    stream: mediaStream,
    wakeWords: DEFAULT_WAKE_WORDS,
    language: toLocale(currentLanguage),
    onWakeWord: () => {
      markAudioUserInteraction();
      setError(null);
    },
    onThinkingWatchdogExpire: () => playAudioFallbackNoticeRef.current(),
    onStateTransition: handleVoiceControllerTransition,
  });

  const sessionState = normalizeSessionState(voiceController.mode);

  const completeAssistantTurn = useCallback(
    (forceSkipAutoResume = false) => {
      const skipAutoResume =
        forceSkipAutoResume ||
        skipAssistantTurnAutoResume ||
        forceSkipAutoResumeRef.current;
      forceSkipAutoResumeRef.current = false;
      voiceController.notifySpeakingComplete(skipAutoResume);
    },
    [skipAssistantTurnAutoResume, voiceController],
  );

  const {
    audioQueueRef,
    mobileAudioServiceRef,
    cleanupAudioPlayback,
    analyzeLipSyncFrames,
    scheduleLipSyncFrames,
    stopPlayback,
    playAssistantAudio,
    playAudioFallbackNotice,
    deferForIOSAudioUnlock,
    unlockAudioPlayback,
    cancelPendingIOSPlaybackReplay,
    resetFallbackNoticeCount,
  } = useVoiceAudioPlayback({
    currentLanguage,
    isMuted,
    volume,
    sessionState,
    onVisemeControl,
    onAssistantPlaybackStart,
    voiceController,
    cancelFastFiller,
    completeAssistantTurn,
    setError,
    setIsLoading,
    setLoadingMessage,
    setLoadingPhase,
    setExclusiveUiLock,
  });
  playAudioFallbackNoticeRef.current = playAudioFallbackNotice;

  useEffect(() => {
    if (isStoppingRecorderRef.current && voiceController.shouldListen) {
      return;
    }
    shouldListenRef.current = voiceController.shouldListen;
  }, [voiceController.shouldListen]);

  const setVolume = useCallback((nextVolume: number) => {
    setVolumeState(nextVolume);
    const effectiveVolume = isMuted ? 0 : nextVolume;
    mobileAudioServiceRef.current?.setVolume(effectiveVolume);
    audioQueueRef.current?.setVolume(effectiveVolume);
  }, [audioQueueRef, isMuted, mobileAudioServiceRef]);

  const setMuted = useCallback((nextMuted: boolean) => {
    setIsMuted(nextMuted);
    const effectiveVolume = nextMuted ? 0 : volume;
    mobileAudioServiceRef.current?.setVolume(effectiveVolume);
    audioQueueRef.current?.setVolume(effectiveVolume);
  }, [audioQueueRef, mobileAudioServiceRef, volume]);

  const resetConversation = useCallback(() => {
    setTranscript('');
    setResponse('');
    setMetadata(null);
    setError(null);
    setIsLoading(false);
    setLoadingMessage('');
    setLoadingPhase(null);
    setExclusiveUiLock(false);
    resetFallbackNoticeCount();
    sessionIdRef.current = createSessionId();
  }, [resetFallbackNoticeCount]);

  const ensureVisitorId = useCallback((): string => {
    if (visitorIdRef.current !== 'anonymous') {
      return visitorIdRef.current;
    }

    const nextVisitorId = getOrCreateVisitorId();
    visitorIdRef.current = nextVisitorId;
    return nextVisitorId;
  }, []);

  const {
    processVoiceTurnWithParallelFiller,
    sendMessage,
    speakPreparedText,
  } = useVoiceTurnProcessor({
    currentLanguage,
    isMuted,
    volume,
    sessionIdRef,
    requestAbortRef,
    audioQueueRef,
    voiceController,
    ensureVisitorId,
    cancelPendingRequest,
    cancelFastFiller,
    scheduleFastFiller,
    stopPlayback,
    playAssistantAudio,
    playAudioFallbackNotice,
    deferForIOSAudioUnlock,
    analyzeLipSyncFrames,
    scheduleLipSyncFrames,
    cleanupAudioPlayback,
    completeAssistantTurn,
    emitVoiceTelemetry,
    onAssistantPlaybackStart,
    onSlideAgentResponse,
    onVisemeControl,
    onVoiceTurnThinkingVisual,
    onVoiceTurnAssistantSpeakingVisual,
    setError,
    setTranscript,
    setResponse,
    setMetadata,
    setIsLoading,
    setLoadingMessage,
    setLoadingPhase,
    setExclusiveUiLock,
  });

  const handleRecordedAudio = useCallback(
    async (audioBlob: Blob) => {
      if (shouldDiscardNextAudioRef.current) {
        shouldDiscardNextAudioRef.current = false;
        return;
      }
      if (voiceTurnInProgressRef.current) {
        return;
      }

      voiceTurnInProgressRef.current = true;
      cancelPendingRequest();
      setError(null);
      setIsLoading(true);
      setLoadingMessage(LOADING_LABELS[currentLanguage].recognize);
      setLoadingPhase('stt');
      voiceController.notifyProcessing();
      scheduleFastFiller();

      const abortController = new AbortController();
      requestAbortRef.current = abortController;

      try {
        const sttStartedAt = performance.now();
        const sttResponse = await speechToText(
          {
            audioData: await toBase64(audioBlob),
            language: currentLanguage,
            sessionId: sessionIdRef.current,
          },
          {
            signal: abortController.signal,
          },
        );
        emitVoiceTelemetry('voice_turn_timing', 'stt', {
          sttMs: elapsedMs(sttStartedAt),
          status: sttResponse.status,
        });

        const sttResult = sttResponse.data;
        if (!sttResponse.ok || !sttResult.success || typeof sttResult.transcript !== 'string') {
          const sttError: Error & { status?: number } = new Error(
            sttResult.error || '音声認識に失敗しました',
          );
          sttError.status = sttResponse.status;
          throw sttError;
        }

        setTranscript(sttResult.transcript);
        await processVoiceTurnWithParallelFiller(sttResult.transcript.trim(), abortController);
      } catch (recordingError) {
        if (recordingError instanceof DOMException && recordingError.name === 'AbortError') {
          return;
        }

        cancelFastFiller();
        setError(formatError(recordingError, currentLanguage));
        completeAssistantTurn(true);
      } finally {
        if (requestAbortRef.current === abortController) {
          requestAbortRef.current = null;
        }
        setIsLoading(false);
        setLoadingMessage('');
        setLoadingPhase(null);
        isStoppingRecorderRef.current = false;
        voiceTurnInProgressRef.current = false;
      }
    },
    [
      cancelPendingRequest,
      cancelFastFiller,
      completeAssistantTurn,
      currentLanguage,
      emitVoiceTelemetry,
      processVoiceTurnWithParallelFiller,
      scheduleFastFiller,
      voiceController,
    ],
  );

  const ensureRecorder = useCallback(async () => {
    const existingRecorder = recorderRef.current;
    if (existingRecorder?.isInitialized()) {
      return existingRecorder;
    }

    lastRecorderInitErrorRef.current = null;
    const recorder = new VoiceRecorder(
      (audioBlob) => {
        void handleRecordedAudio(audioBlob);
      },
      (recorderError) => {
        lastRecorderInitErrorRef.current = recorderError;
        setError(formatError(recorderError, currentLanguage));
        setIsLoading(false);
        setLoadingMessage('');
        setLoadingPhase(null);
        isRecordingRef.current = false;
        shouldListenRef.current = false;
        voiceController.endManualSession();
      },
      () => {
        if (recorderRef.current !== recorder) {
          return;
        }
        recorderRef.current = null;
        setMediaStream(null);
        isRecordingRef.current = false;
      },
      {
        getSessionId: () => sessionIdRef.current,
      },
    );

    setIsLoading(true);
    setLoadingMessage(LOADING_LABELS[currentLanguage].microphone);
    setLoadingPhase('mic');
    await recorder.initialize();

    if (!recorder.isInitialized()) {
      setIsLoading(false);
      setLoadingMessage('');
      setLoadingPhase(null);
      throw (
        lastRecorderInitErrorRef.current ??
        new Error(currentLanguage === 'ja' ? 'マイクを初期化できませんでした' : 'Unable to initialize the microphone')
      );
    }

    recorderRef.current = recorder;
    setMediaStream(recorder.getStream());
    setIsLoading(false);
    setLoadingMessage('');
    setLoadingPhase(null);

    return recorder;
  }, [currentLanguage, handleRecordedAudio, voiceController]);

  const startRecorderCapture = useCallback(async (): Promise<boolean> => {
    if (isRecordingRef.current) {
      return true;
    }
    if (isStartingRecorderRef.current) {
      return false;
    }

    isStartingRecorderRef.current = true;
    try {
      const recorder = await ensureRecorder();
      if (!shouldListenRef.current) {
        recorder.cleanup();
        if (recorderRef.current === recorder) {
          recorderRef.current = null;
          setMediaStream(null);
        }
        return false;
      }
      if (recorder.getState() === 'recording') {
        isRecordingRef.current = true;
        return true;
      }

      recorder.start();
      if (!recorder.isCurrentlyRecording()) {
        shouldListenRef.current = false;
        isRecordingRef.current = false;
        voiceController.endManualSession();
        return false;
      }
      isRecordingRef.current = true;
      shouldDiscardNextAudioRef.current = false;
      return true;
    } catch (startError) {
      shouldListenRef.current = false;
      isRecordingRef.current = false;
      setIsLoading(false);
      setLoadingMessage('');
      setLoadingPhase(null);
      setError(formatError(startError, currentLanguage));
      voiceController.endManualSession();
      return false;
    } finally {
      isStartingRecorderRef.current = false;
    }
  }, [currentLanguage, ensureRecorder, voiceController]);

  const stopRecorderCapture = useCallback((discard: boolean) => {
    if (!recorderRef.current || !isRecordingRef.current) {
      shouldDiscardNextAudioRef.current = false;
      return;
    }

    shouldDiscardNextAudioRef.current = discard;
    recorderRef.current.stop();
    isRecordingRef.current = false;
  }, []);

  useEffect(() => {
    if (voiceController.shouldListen) {
      if (!shouldListenRef.current) {
        return;
      }
      void startRecorderCapture();
      return;
    }

    if (isRecordingRef.current) {
      stopRecorderCapture(sessionState === 'idle');
    }
  }, [sessionState, startRecorderCapture, stopRecorderCapture, voiceController.shouldListen]);

  const startListening = useCallback(async (): Promise<boolean> => {
    unlockAudioForUserGesture();
    cancelPendingIOSPlaybackReplay();
    shouldListenRef.current = true;
    isStoppingRecorderRef.current = false;
    forceSkipAutoResumeRef.current = false;
    resetFallbackNoticeCount();
    cancelPendingRequest();
    stopPlayback(false);
    setError(null);
    const started = await startRecorderCapture();
    if (!started) {
      shouldListenRef.current = false;
      return false;
    }
    voiceController.startManualSession();
    sendSttWarmup({ language: currentLanguage, sessionId: sessionIdRef.current });
    return true;
  }, [
    cancelPendingRequest,
    cancelPendingIOSPlaybackReplay,
    currentLanguage,
    resetFallbackNoticeCount,
    startRecorderCapture,
    stopPlayback,
    voiceController,
  ]);

  const stopListening = useCallback(() => {
    shouldListenRef.current = false;
    isStoppingRecorderRef.current = true;
    forceSkipAutoResumeRef.current = true;
    stopRecorderCapture(false);
    voiceController.notifyProcessing();
  }, [stopRecorderCapture, voiceController]);

  const cancelSession = useCallback(() => {
    cancelPendingIOSPlaybackReplay();
    cancelSttWarmup();
    cancelFastFiller();
    requestBackendInterrupt();
    cancelPendingRequest();
    stopPlayback(false);
    shouldDiscardNextAudioRef.current = true;
    isStoppingRecorderRef.current = false;
    voiceTurnInProgressRef.current = false;
    forceSkipAutoResumeRef.current = false;
    stopRecorderCapture(true);
    setIsLoading(false);
    setLoadingMessage('');
    setLoadingPhase(null);
    setExclusiveUiLock(false);
    voiceController.endManualSession();
  }, [
    cancelFastFiller,
    cancelPendingRequest,
    cancelPendingIOSPlaybackReplay,
    requestBackendInterrupt,
    stopPlayback,
    stopRecorderCapture,
    voiceController,
  ]);

  const clearConversation = useCallback(() => {
    cancelSession();
    resetConversation();
  }, [cancelSession, resetConversation]);

  const clearVisitState = useCallback(() => {
    cancelSession();
    resetConversation();
    clearVisitorId();
    visitorIdRef.current = 'anonymous';
  }, [cancelSession, resetConversation]);

  const toggleLanguage = useCallback(() => {
    const nextLanguage = currentLanguage === 'ja' ? 'en' : 'ja';
    setCurrentLanguage(nextLanguage);
    onLanguageChange?.(nextLanguage);
  }, [currentLanguage, onLanguageChange]);

  useEffect(() => {
    if (!autoGreeting) {
      return;
    }

    const greeting =
      currentLanguage === 'ja'
        ? 'こんにちは。エンジニアカフェで知りたいことを話しかけてください。'
        : 'Hello. Ask me anything about Engineer Cafe.';

    setResponse(greeting);
  }, [autoGreeting, currentLanguage]);

  const prevSessionStateRef = useRef<VoiceSessionState>(sessionState);
  useEffect(() => {
    if (prevSessionStateRef.current === 'speaking' && sessionState === 'idle') {
      onAssistantPlaybackEnd?.();
    }
    prevSessionStateRef.current = sessionState;
  }, [sessionState, onAssistantPlaybackEnd]);

  useEffect(() => {
    return registerAudioContextSuspensionListener(() => {
      setError(getTapToEnableAudioMessage(currentLanguage));
    });
  }, [currentLanguage]);

  const uiLockState = useMemo<VoiceUiLockState>(() => {
    if (exclusiveUiLock) {
      return 'locked';
    }
    if (loadingPhase === 'mic' || loadingPhase === 'stt') {
      return 'locked';
    }
    if (
      sessionState === 'processing' ||
      sessionState === 'speaking' ||
      loadingPhase === 'llm' ||
      loadingPhase === 'tts'
    ) {
      return 'interruptible';
    }
    if (sessionState === 'listening') {
      return 'locked';
    }
    return 'normal';
  }, [exclusiveUiLock, loadingPhase, sessionState]);

  useEffect(() => {
    return () => {
      cancelFastFiller();
      cancelPendingRequest();
      recorderRef.current?.cleanup();
    };
  }, [cancelFastFiller, cancelPendingRequest]);

  const renderProps = useMemo<VoiceInterfaceRenderProps>(
    () => ({
      sessionId: sessionIdRef.current,
      sessionState,
      characterState: voiceController.characterState,
      transcript,
      response,
      metadata,
      error,
      isLoading,
      loadingMessage,
      loadingPhase,
      uiLockState,
      currentLanguage,
      volume,
      isMuted,
      waveformBars: voiceController.waveformBars,
      wakeWord: {
        isSupported: voiceController.isWakeWordSupported,
        isListening: voiceController.isWakeWordListening,
        error: voiceController.wakeWordError,
        lastMatch: voiceController.lastWakeWordMatch,
      },
      startListening,
      stopListening,
      cancelSession,
      clearConversation,
      clearVisitState,
      unlockAudioPlayback,
      sendMessage,
      speakPreparedText,
      setVolume,
      setMuted,
      toggleLanguage,
    }),
    [
      cancelSession,
      clearConversation,
      clearVisitState,
      currentLanguage,
      error,
      isLoading,
      isMuted,
      loadingMessage,
      loadingPhase,
      uiLockState,
      metadata,
      response,
      sendMessage,
      speakPreparedText,
      sessionState,
      setMuted,
      setVolume,
      startListening,
      stopListening,
      toggleLanguage,
      transcript,
      unlockAudioPlayback,
      voiceController.characterState,
      voiceController.isWakeWordListening,
      voiceController.isWakeWordSupported,
      voiceController.lastWakeWordMatch,
      voiceController.wakeWordError,
      voiceController.waveformBars,
      volume,
    ],
  );

  const shouldRenderDefaultUi = showDefaultUI ?? !children;

  if (children && !shouldRenderDefaultUi) {
    return <>{children(renderProps)}</>;
  }

  return (
    <VoiceInterfaceDefaultUI
      renderProps={renderProps}
      layout={layout}
      className={className}
    />
  );
}
