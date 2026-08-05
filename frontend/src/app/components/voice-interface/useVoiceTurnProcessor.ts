import { AudioQueue } from '@/lib/audio-queue';
import { AudioDataProcessor } from '@/lib/audio/audio-data-processor';
import { requestAutoCharacterControl } from '@/lib/api/character-client';
import { submitQaQuestion } from '@/lib/api/qa-client';
import { getTtsProvider } from '@/lib/env-client';
import {
  requestVoiceFiller,
  textToSpeech,
  type TextToSpeechPayload,
} from '@/lib/api/voice-client';
import { EmotionTagParser } from '@/lib/emotion-tag-parser';
import { formatError } from '@/lib/error-messages';
import type { LipSyncFrame } from '@/lib/lip-sync-analyzer';
import { createVoiceFillerPlaybackGate } from '@/lib/voice-filler-playback';
import { resolveVoiceResponseLanguage } from '@/lib/voice/response-language';
import { isSlideAgentMetadata } from '@/lib/voice/slide-agent-metadata';
import { mergePlaybackMetadataWithTtsVrmControl } from '@/lib/voice/tts-vrm-metadata';
import { preprocessTTS } from '@/utils/tts-preprocess';
import { useCallback, type Dispatch, type MutableRefObject, type SetStateAction } from 'react';
import {
  AUTO_VRM_PLAYBACK_WAIT_MS,
  LOADING_LABELS,
  PARALLEL_VOICE_FILLER_ENABLED,
} from './constants';
import type {
  VoiceInterfaceMetadata,
  VoiceLoadingPhase,
  VoiceTimingTelemetry,
} from './types';
import { elapsedMs } from './utils';

interface VoiceTurnController {
  notifyProcessing: () => void;
  notifySpeaking: () => void;
}

interface VoiceTurnInitialTiming {
  sttMs?: number;
  turnStartedAt?: number;
}

interface UseVoiceTurnProcessorArgs {
  currentLanguage: 'ja' | 'en';
  isMuted: boolean;
  volume: number;
  sessionIdRef: MutableRefObject<string>;
  requestAbortRef: MutableRefObject<AbortController | null>;
  audioQueueRef: MutableRefObject<AudioQueue | null>;
  voiceController: VoiceTurnController;
  ensureVisitorId: () => string;
  cancelPendingRequest: () => void;
  cancelFastFiller: () => void;
  scheduleFastFiller: () => void;
  stopPlayback: (completeTurn: boolean) => void;
  playAssistantAudio: (
    audioBase64: string,
    metadataForPlayback?: VoiceInterfaceMetadata | null,
  ) => Promise<void>;
  playAudioFallbackNotice: () => void;
  deferForIOSAudioUnlock: (
    pendingPlayback?: {
      audioBase64: string;
      metadata: VoiceInterfaceMetadata | null;
    },
  ) => boolean;
  analyzeLipSyncFrames: (audioBlob: Blob) => Promise<LipSyncFrame[] | null>;
  scheduleLipSyncFrames: (frames: LipSyncFrame[]) => void;
  cleanupAudioPlayback: () => void;
  completeAssistantTurn: (forceSkipAutoResume?: boolean) => void;
  emitVoiceTelemetry: (
    event: string,
    phase: string,
    metrics?: VoiceTimingTelemetry,
  ) => void;
  onAssistantPlaybackStart?: (payload: { metadata: VoiceInterfaceMetadata | null }) => void;
  onSlideAgentResponse?: (payload: {
    answer: string;
    metadata: VoiceInterfaceMetadata | null;
  }) => void;
  onVisemeControl?: ((viseme: string, intensity: number) => void) | null;
  onVoiceTurnThinkingVisual?: () => void;
  onVoiceTurnAssistantSpeakingVisual?: () => void;
  setError: Dispatch<SetStateAction<string | null>>;
  setTranscript: Dispatch<SetStateAction<string>>;
  setResponse: Dispatch<SetStateAction<string>>;
  setMetadata: Dispatch<SetStateAction<VoiceInterfaceMetadata | null>>;
  setIsLoading: Dispatch<SetStateAction<boolean>>;
  setLoadingMessage: Dispatch<SetStateAction<string>>;
  setLoadingPhase: Dispatch<SetStateAction<VoiceLoadingPhase>>;
  setExclusiveUiLock: Dispatch<SetStateAction<boolean>>;
}

export function useVoiceTurnProcessor({
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
}: UseVoiceTurnProcessorArgs) {
  const fetchAutoVrmControl = useCallback(
    async (
      cleanText: string,
      emotion: string | null | undefined,
      signal: AbortSignal,
    ): Promise<Record<string, unknown> | null> => {
      try {
        const response = await requestAutoCharacterControl(
          {
            cleanText,
            emotion: emotion?.trim() || 'neutral',
          },
          {
            signal,
          },
        );
        if (!response.ok || !response.data.success) {
          return null;
        }
        return response.data as unknown as Record<string, unknown>;
      } catch {
        return null;
      }
    },
    [],
  );

  const synthesizeAssistantSpeech = useCallback(
    async (
      request: {
        text: string;
        language: 'ja' | 'en';
        sessionId: string;
        emotion?: string | null;
        ttsProvider?: string;
      },
      signal: AbortSignal,
    ): Promise<TextToSpeechPayload & Record<string, unknown>> => {
      const response = await textToSpeech(
        {
          text: request.text,
          language: request.language,
          sessionId: request.sessionId,
          ttsProvider: request.ttsProvider ?? getTtsProvider(),
          ...(typeof request.emotion === 'string' && request.emotion.trim()
            ? { emotion: request.emotion.trim() }
            : {}),
        },
        { signal },
      );
      if (!response.ok || !response.data.success) {
        const ttsError: Error & { status?: number } = new Error(
          response.data.error || '音声の生成に失敗しました',
        );
        ttsError.status = response.status;
        throw ttsError;
      }
      return response.data as TextToSpeechPayload & Record<string, unknown>;
    },
    [],
  );

  const resolveAutoVrmControlForPlayback = useCallback(
    async (vrmTask: Promise<Record<string, unknown> | null>) => {
      return Promise.race([
        vrmTask,
        new Promise<null>((resolve) => {
          window.setTimeout(resolve, AUTO_VRM_PLAYBACK_WAIT_MS, null);
        }),
      ]);
    },
    [],
  );

  const processVoiceTurnWithParallelFiller = useCallback(
    async (
      trimmed: string,
      abortController: AbortController,
      initialTiming: VoiceTurnInitialTiming = {},
    ) => {
      const signal = abortController.signal;
      const visitorId = ensureVisitorId();
      const fillerGate = createVoiceFillerPlaybackGate(signal);
      const turnStartedAt = initialTiming.turnStartedAt ?? performance.now();
      let qaMs: number | undefined;
      let ttsMs: number | undefined;

      cancelFastFiller();
      stopPlayback(false);
      setError(null);
      setIsLoading(true);
      setLoadingMessage(LOADING_LABELS[currentLanguage].answer);
      setLoadingPhase('llm');
      voiceController.notifyProcessing();

      const fillerTask =
        PARALLEL_VOICE_FILLER_ENABLED && trimmed.length > 0
          ? (async () => {
              try {
                const result = await requestVoiceFiller(
                  {
                    query: trimmed,
                    language: currentLanguage,
                    sessionId: sessionIdRef.current,
                  },
                  {
                    signal,
                  },
                );
                if (!result.ok || !result.data.success) {
                  return;
                }
                const data = result.data;
                if (!fillerGate.canEnqueue(data.audioResponse)) {
                  return;
                }
                const q = audioQueueRef.current;
                if (!q) {
                  return;
                }
                q.setVolume(isMuted ? 0 : volume);
                onVoiceTurnThinkingVisual?.();
                q.add({
                  id: `filler-${Date.now()}`,
                  priority: 10,
                  audioData: data.audioResponse,
                });
              } catch {
                /* degrade silently */
              }
            })()
          : Promise.resolve();

      try {
        const qaStartedAt = performance.now();
        const qaResponse = await submitQaQuestion(
          {
            question: trimmed,
            text: trimmed,
            sessionId: sessionIdRef.current,
            language: currentLanguage,
            visitorId,
          },
          {
            signal,
          },
        );
        qaMs = elapsedMs(qaStartedAt);
        emitVoiceTelemetry('voice_turn_timing', 'qa', {
          qaMs,
          requestMode: qaResponse.mode,
          usedProxyFallback: qaResponse.usedProxyFallback,
          status: qaResponse.status,
        });

        const qaResult = qaResponse.data;
        if (!qaResponse.ok || !qaResult.success) {
          const qaError: Error & { status?: number } = new Error(
            qaResult.error || '質問の送信に失敗しました',
          );
          qaError.status = qaResponse.status;
          throw qaError;
        }

        const parsedAnswer = EmotionTagParser.parseEmotionTags(
          typeof qaResult.answer === 'string' ? qaResult.answer : '',
        );
        const cleanAnswer = parsedAnswer.cleanText;

        const qaMeta = (qaResult.metadata as VoiceInterfaceMetadata | null) ?? null;
        const responseLanguage = resolveVoiceResponseLanguage(qaMeta, currentLanguage);
        setResponse(cleanAnswer);
        setMetadata(qaMeta);

        if (onSlideAgentResponse && isSlideAgentMetadata(qaMeta)) {
          fillerGate.close();
          void fillerTask.catch(() => {});
          cancelFastFiller();
          onSlideAgentResponse({ answer: cleanAnswer, metadata: qaMeta });
          completeAssistantTurn(true);
          return;
        }

        const vrmTask = fetchAutoVrmControl(
          cleanAnswer,
          typeof qaResult.emotion === 'string' ? qaResult.emotion : null,
          signal,
        );
        const ttsStartedAt = performance.now();
        const ttsResult = await synthesizeAssistantSpeech(
          {
            text: preprocessTTS(cleanAnswer, responseLanguage),
            language: responseLanguage,
            sessionId: sessionIdRef.current,
            emotion: typeof qaResult.emotion === 'string' ? qaResult.emotion : null,
            ttsProvider: getTtsProvider(),
          },
          signal,
        );
        ttsMs = elapsedMs(ttsStartedAt);
        emitVoiceTelemetry('voice_turn_timing', 'tts', {
          ttsMs,
          status: 200,
          upstreamStatus: ttsResult.upstreamStatus ?? null,
        });
        emitVoiceTelemetry('voice_round_trip', 'complete', {
          sttMs: initialTiming.sttMs,
          qaMs,
          ttsMs,
          turnTotalMs: elapsedMs(turnStartedAt),
          success: true,
          status: 200,
        });

        fillerGate.close();
        // Filler runs in parallel; do not await — slow filler must not delay main TTS enqueue.
        void fillerTask.catch(() => {});

        const vrmResult = await resolveAutoVrmControlForPlayback(vrmTask);
        const playbackMetadata = mergePlaybackMetadataWithTtsVrmControl(
          qaMeta,
          vrmResult ?? ttsResult,
        );

        if (isMuted) {
          cancelFastFiller();
          voiceController.notifySpeaking();
          onAssistantPlaybackStart?.({ metadata: playbackMetadata ?? null });
          window.setTimeout(() => {
            completeAssistantTurn();
          }, 240);
          return;
        }

        if (typeof ttsResult.audioResponse === 'string' && ttsResult.audioResponse.length > 0) {
          cancelFastFiller();
          onVoiceTurnAssistantSpeakingVisual?.();

          let audioBytes: Uint8Array;
          try {
            audioBytes = Uint8Array.from(atob(ttsResult.audioResponse), (char) => char.charCodeAt(0));
          } catch (decodeError) {
            console.error('Audio decode failed:', decodeError);
            playAudioFallbackNotice();
            completeAssistantTurn(true);
            return;
          }
          const detectedFormat = AudioDataProcessor.detectAudioFormat(audioBytes.buffer as ArrayBuffer);
          const responseBlob = new Blob([audioBytes], { type: detectedFormat });

          let lipSyncFrames: LipSyncFrame[] | null = null;
          if (!playbackMetadata?.vrm_control && onVisemeControl) {
            lipSyncFrames = await analyzeLipSyncFrames(responseBlob);
          }

          const q = audioQueueRef.current;
          if (!q) {
            await playAssistantAudio(ttsResult.audioResponse, playbackMetadata);
            return;
          }
          if (deferForIOSAudioUnlock({
            audioBase64: ttsResult.audioResponse,
            metadata: playbackMetadata ?? null,
          })) {
            return;
          }
          q.setVolume(isMuted ? 0 : volume);
          q.add({
            id: `assistant-${Date.now()}`,
            priority: 5,
            audioData: ttsResult.audioResponse,
            onPlaybackStart: () => {
              cancelFastFiller();
              setLoadingMessage(LOADING_LABELS[currentLanguage].speaking);
              setLoadingPhase('tts');
              voiceController.notifySpeaking();
              onAssistantPlaybackStart?.({ metadata: playbackMetadata ?? null });
              if (lipSyncFrames && lipSyncFrames.length > 0) {
                scheduleLipSyncFrames(lipSyncFrames);
              }
            },
            onPlaybackEnd: () => {
              cleanupAudioPlayback();
              completeAssistantTurn();
            },
          });
        } else {
          cancelFastFiller();
          playAudioFallbackNotice();
          voiceController.notifySpeaking();
          window.setTimeout(() => {
            completeAssistantTurn();
          }, 240);
        }
      } catch (voiceError) {
        fillerGate.close();
        if (voiceError instanceof DOMException && voiceError.name === 'AbortError') {
          return;
        }
        cancelFastFiller();
        setError(formatError(voiceError, currentLanguage));
        emitVoiceTelemetry('voice_round_trip', 'error', {
          sttMs: initialTiming.sttMs,
          qaMs,
          ttsMs,
          turnTotalMs: elapsedMs(turnStartedAt),
          success: false,
          errorType: voiceError instanceof Error ? voiceError.name : 'VoiceTurnError',
        });
        playAudioFallbackNotice();
        completeAssistantTurn(true);
      }
    },
    [
      cancelFastFiller,
      analyzeLipSyncFrames,
      cleanupAudioPlayback,
      completeAssistantTurn,
      currentLanguage,
      ensureVisitorId,
      isMuted,
      onAssistantPlaybackStart,
      playAudioFallbackNotice,
      onSlideAgentResponse,
      onVisemeControl,
      onVoiceTurnAssistantSpeakingVisual,
      onVoiceTurnThinkingVisual,
      playAssistantAudio,
      resolveAutoVrmControlForPlayback,
      scheduleLipSyncFrames,
      deferForIOSAudioUnlock,
      fetchAutoVrmControl,
      stopPlayback,
      volume,
      voiceController,
      emitVoiceTelemetry,
      sessionIdRef,
      audioQueueRef,
      setError,
      setIsLoading,
      setLoadingMessage,
      setLoadingPhase,
      setMetadata,
      setResponse,
      synthesizeAssistantSpeech,
    ],
  );

  const sendMessage = useCallback(
    async (message: string) => {
      const trimmed = message.trim();
      if (!trimmed) {
        return;
      }

      cancelPendingRequest();
      stopPlayback(false);
      setError(null);
      setTranscript(trimmed);
      setIsLoading(true);
      setLoadingMessage(LOADING_LABELS[currentLanguage].answer);
      setLoadingPhase('llm');
      voiceController.notifyProcessing();
      scheduleFastFiller();

      const abortController = new AbortController();
      requestAbortRef.current = abortController;
      const visitorId = ensureVisitorId();

      try {
        const qaStartedAt = performance.now();
        const qaResponse = await submitQaQuestion(
          {
            question: trimmed,
            text: trimmed,
            sessionId: sessionIdRef.current,
            language: currentLanguage,
            visitorId,
          },
          {
            signal: abortController.signal,
          },
        );
        emitVoiceTelemetry('voice_turn_timing', 'qa', {
          qaMs: elapsedMs(qaStartedAt),
          requestMode: qaResponse.mode,
          usedProxyFallback: qaResponse.usedProxyFallback,
          status: qaResponse.status,
        });

        const qaResult = qaResponse.data;
        if (!qaResponse.ok || !qaResult.success) {
          const qaError: Error & { status?: number } = new Error(
            qaResult.error || '質問の送信に失敗しました',
          );
          qaError.status = qaResponse.status;
          throw qaError;
        }

        const parsedAnswer = EmotionTagParser.parseEmotionTags(
          typeof qaResult.answer === 'string' ? qaResult.answer : '',
        );
        const cleanAnswer = parsedAnswer.cleanText;

        const qaMeta = (qaResult.metadata as VoiceInterfaceMetadata | null) ?? null;
        const responseLanguage = resolveVoiceResponseLanguage(qaMeta, currentLanguage);
        setResponse(cleanAnswer);
        setMetadata(qaMeta);

        if (onSlideAgentResponse && isSlideAgentMetadata(qaMeta)) {
          cancelFastFiller();
          onSlideAgentResponse({ answer: cleanAnswer, metadata: qaMeta });
          completeAssistantTurn(true);
          return;
        }

        const vrmTask = fetchAutoVrmControl(
          cleanAnswer,
          typeof qaResult.emotion === 'string' ? qaResult.emotion : null,
          abortController.signal,
        );
        const ttsStartedAt = performance.now();
        const ttsResult = await synthesizeAssistantSpeech(
          {
            text: preprocessTTS(cleanAnswer, responseLanguage),
            language: responseLanguage,
            sessionId: sessionIdRef.current,
            emotion: typeof qaResult.emotion === 'string' ? qaResult.emotion : null,
            ttsProvider: getTtsProvider(),
          },
          abortController.signal,
        );
        emitVoiceTelemetry('voice_turn_timing', 'tts', {
          ttsMs: elapsedMs(ttsStartedAt),
          status: 200,
          upstreamStatus: ttsResult.upstreamStatus ?? null,
        });

        const vrmResult = await resolveAutoVrmControlForPlayback(vrmTask);
        const playbackMetadata = mergePlaybackMetadataWithTtsVrmControl(
          qaMeta,
          vrmResult ?? ttsResult,
        );

        if (typeof ttsResult.audioResponse === 'string' && ttsResult.audioResponse.length > 0) {
          await playAssistantAudio(ttsResult.audioResponse, playbackMetadata);
        } else {
          cancelFastFiller();
          playAudioFallbackNotice();
          voiceController.notifySpeaking();
          window.setTimeout(() => {
            completeAssistantTurn();
          }, 240);
        }
      } catch (sendError) {
        if (sendError instanceof DOMException && sendError.name === 'AbortError') {
          return;
        }

        cancelFastFiller();
        setError(formatError(sendError, currentLanguage));
        playAudioFallbackNotice();
        completeAssistantTurn(true);
      } finally {
        if (requestAbortRef.current === abortController) {
          requestAbortRef.current = null;
        }
        setIsLoading(false);
        setLoadingMessage('');
        setLoadingPhase(null);
        setExclusiveUiLock(false);
      }
    },
    [
      cancelPendingRequest,
      cancelFastFiller,
      completeAssistantTurn,
      currentLanguage,
      ensureVisitorId,
      fetchAutoVrmControl,
      onSlideAgentResponse,
      playAssistantAudio,
      playAudioFallbackNotice,
      resolveAutoVrmControlForPlayback,
      scheduleFastFiller,
      stopPlayback,
      voiceController,
      emitVoiceTelemetry,
      requestAbortRef,
      sessionIdRef,
      setError,
      setExclusiveUiLock,
      setIsLoading,
      setLoadingMessage,
      setLoadingPhase,
      setMetadata,
      setResponse,
      setTranscript,
      synthesizeAssistantSpeech,
    ],
  );

  const speakPreparedText = useCallback(
    async (rawText: string, metadataForPlayback?: VoiceInterfaceMetadata | null) => {
      const trimmed = rawText.trim();
      if (!trimmed) {
        return;
      }

      cancelPendingRequest();
      stopPlayback(false);
      setExclusiveUiLock(true);
      setError(null);
      setTranscript('');

      const parsedAnswer = EmotionTagParser.parseEmotionTags(trimmed);
      const cleanAnswer = parsedAnswer.cleanText;

      setResponse(cleanAnswer);
      setMetadata(metadataForPlayback ?? null);

      setIsLoading(true);
      setLoadingMessage(LOADING_LABELS[currentLanguage].speaking);
      setLoadingPhase('tts');
      voiceController.notifyProcessing();

      const abortController = new AbortController();
      requestAbortRef.current = abortController;

      try {
        const responseLanguage = resolveVoiceResponseLanguage(metadataForPlayback, currentLanguage);
        const vrmTask = fetchAutoVrmControl(
          cleanAnswer,
          parsedAnswer.primaryEmotion,
          abortController.signal,
        );
        const ttsStartedAt = performance.now();
        const ttsResult = await synthesizeAssistantSpeech(
          {
            text: preprocessTTS(cleanAnswer, responseLanguage),
            language: responseLanguage,
            sessionId: sessionIdRef.current,
            emotion: parsedAnswer.primaryEmotion,
            ttsProvider: getTtsProvider(),
          },
          abortController.signal,
        );
        emitVoiceTelemetry('voice_turn_timing', 'tts', {
          ttsMs: elapsedMs(ttsStartedAt),
          status: 200,
          upstreamStatus: ttsResult.upstreamStatus ?? null,
        });

        const vrmResult = await resolveAutoVrmControlForPlayback(vrmTask);
        const playbackMetadata = mergePlaybackMetadataWithTtsVrmControl(
          metadataForPlayback ?? null,
          vrmResult ?? ttsResult,
        );

        if (typeof ttsResult.audioResponse === 'string' && ttsResult.audioResponse.length > 0) {
          await playAssistantAudio(ttsResult.audioResponse, playbackMetadata);
        } else {
          playAudioFallbackNotice();
          voiceController.notifySpeaking();
          window.setTimeout(() => {
            completeAssistantTurn();
          }, 240);
        }
      } catch (speakError) {
        if (speakError instanceof DOMException && speakError.name === 'AbortError') {
          return;
        }

        setError(formatError(speakError, currentLanguage));
        playAudioFallbackNotice();
        completeAssistantTurn(true);
      } finally {
        if (requestAbortRef.current === abortController) {
          requestAbortRef.current = null;
        }
        setIsLoading(false);
        setLoadingMessage('');
        setLoadingPhase(null);
        setExclusiveUiLock(false);
      }
    },
    [
      cancelPendingRequest,
      completeAssistantTurn,
      currentLanguage,
      fetchAutoVrmControl,
      playAssistantAudio,
      playAudioFallbackNotice,
      resolveAutoVrmControlForPlayback,
      stopPlayback,
      voiceController,
      emitVoiceTelemetry,
      requestAbortRef,
      sessionIdRef,
      setError,
      setExclusiveUiLock,
      setIsLoading,
      setLoadingMessage,
      setLoadingPhase,
      setMetadata,
      setResponse,
      setTranscript,
      synthesizeAssistantSpeech,
    ],
  );

  return {
    processVoiceTurnWithParallelFiller,
    sendMessage,
    speakPreparedText,
  };
}
