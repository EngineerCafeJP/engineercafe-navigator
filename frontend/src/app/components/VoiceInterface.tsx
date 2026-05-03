'use client';

import { AudioQueue } from '@/lib/audio-queue';
import { AudioDataProcessor } from '@/lib/audio/audio-data-processor';
import {
  AudioInteractionManager,
  registerAudioContextSuspensionListener,
  unlockAudioForUserGesture,
} from '@/lib/audio/audio-interaction-manager';
import {
  getTapToEnableAudioMessage,
  isIOSWebKitAudio,
  markAudioUserInteraction,
} from '@/lib/audio/audio-user-interaction-gate';
import { MobileAudioService } from '@/lib/audio/mobile-audio-service';
import { audioStateManager } from '@/lib/audio-state-manager';
import { cn } from '@/lib/cn';
import { EmotionTagParser } from '@/lib/emotion-tag-parser';
import { formatError } from '@/lib/error-messages';
import { LipSyncAnalyzer, type LipSyncFrame } from '@/lib/lip-sync-analyzer';
import { createVoiceFillerPlaybackGate } from '@/lib/voice-filler-playback';
import { mergePlaybackMetadataWithTtsVrmControl } from '@/lib/voice/tts-vrm-metadata';
import { preprocessTTS } from '@/utils/tts-preprocess';
import { AlertCircle, Loader2, Mic, MicOff, Volume2, VolumeX, XCircle } from 'lucide-react';
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MutableRefObject,
  type ReactNode,
} from 'react';
import {
  useVoiceSessionController,
  type VoiceCharacterState,
} from '../hooks/useVoiceSessionController';
import type { WakeWordMatch } from '../hooks/useWakeWord';
import { VoiceRecorder } from '@/lib/voice-recorder';
import { cancelSttWarmup, sendSttWarmup } from '@/lib/stt-warmup';
import type { CharacterAnimationData } from '../utils/character-animation-utils';

export type VoiceSessionState = 'idle' | 'listening' | 'processing' | 'speaking';

/** Semantic loading stage for kiosk UI; avoids coupling to localized loadingMessage strings. */
export type VoiceLoadingPhase = 'mic' | 'stt' | 'llm' | 'tts' | null;

export interface VoiceInterfaceMetadata {
  clarification?: {
    clarification_type?: string;
    [key: string]: unknown;
  };
  clarification_options?: string[];
  requires_followup?: boolean;
   reception_type?: string;
  vrm_control?: CharacterAnimationData | null;
  [key: string]: unknown;
}

export interface VoiceInterfaceRenderProps {
  sessionId: string;
  sessionState: VoiceSessionState;
  characterState: VoiceCharacterState;
  transcript: string;
  response: string;
  metadata: VoiceInterfaceMetadata | null;
  error: string | null;
  isLoading: boolean;
  loadingMessage: string;
  loadingPhase: VoiceLoadingPhase;
  currentLanguage: 'ja' | 'en';
  volume: number;
  isMuted: boolean;
  waveformBars: number[];
  wakeWord: {
    isSupported: boolean;
    isListening: boolean;
    error: string | null;
    lastMatch: WakeWordMatch | null;
  };
  startListening: () => Promise<boolean>;
  stopListening: () => void;
  cancelSession: () => void;
  clearConversation: () => void;
  clearVisitState: () => void;
  sendMessage: (message: string) => Promise<void>;
  /** Speak fixed text (e.g. reception greeting) without running QA. */
  speakPreparedText: (
    text: string,
    metadataForPlayback?: VoiceInterfaceMetadata | null,
  ) => Promise<void>;
  setVolume: (value: number) => void;
  setMuted: (value: boolean) => void;
  toggleLanguage: () => void;
}

interface VoiceInterfaceProps {
  onLanguageChange?: (language: 'ja' | 'en') => void;
  layout?: 'vertical' | 'horizontal';
  language?: 'ja' | 'en';
  /** When false, idle wake-word listening is off (no mic via Web Speech API). Default true. */
  wakeWordEnabled?: boolean;
  /**
   * When false, after assistant TTS the session does not auto-return to listening (mic stays off until the user starts again).
   * Use for kiosk push-to-talk. Default true (continuous toggle conversations).
   */
  autoResumeListeningAfterAssistant?: boolean;
  autoGreeting?: boolean;
  onVisemeControl?: ((viseme: string, intensity: number) => void) | null;
  children?: (props: VoiceInterfaceRenderProps) => ReactNode;
  showDefaultUI?: boolean;
  className?: string;
  onMetadataChange?: (metadata: VoiceInterfaceMetadata | null) => void;
  onAssistantPlaybackStart?: (payload: { metadata: VoiceInterfaceMetadata | null }) => void;
  /** Fired when assistant TTS finishes (session goes from speaking to idle). */
  onAssistantPlaybackEnd?: () => void;
  /** Optional VRM hook while parallel filler / QA runs after STT. */
  onVoiceTurnThinkingVisual?: () => void;
  /** Optional VRM hook when assistant audio is about to play (after filler). */
  onVoiceTurnAssistantSpeakingVisual?: () => void;
}

const DEFAULT_WAKE_WORDS = ['すみません', 'hello'];
const VISITOR_ID_STORAGE_KEY = 'engineer_cafe_visitor_id';

const STATUS_LABELS: Record<'ja' | 'en', Record<VoiceSessionState, string>> = {
  ja: {
    idle: '待機中',
    listening: '聞いています',
    processing: '考えています',
    speaking: '話しています',
  },
  en: {
    idle: 'Ready',
    listening: 'Listening',
    processing: 'Thinking',
    speaking: 'Speaking',
  },
};

const LOADING_LABELS = {
  ja: {
    microphone: 'マイクに接続しています...',
    recognize: '音声を文字にしています...',
    answer: '回答を準備しています...',
    speaking: '音声を再生しています...',
  },
  en: {
    microphone: 'Connecting to the microphone...',
    recognize: 'Transcribing your speech...',
    answer: 'Preparing the answer...',
    speaking: 'Playing the response...',
  },
} as const;

const FAST_FILLER_ENABLED =
  process.env.NEXT_PUBLIC_FAST_FILLER_ENABLED !== 'false';
const PARALLEL_VOICE_FILLER_ENABLED =
  process.env.NEXT_PUBLIC_PARALLEL_VOICE_FILLER !== 'false';
const FAST_FILLER_DELAY_MS = 350;
const FAST_FILLER_TEXT = {
  ja: '確認しています。',
  en: 'Let me check.',
} as const;

/** UUID v4 を生成する。crypto.randomUUID が無い環境（HTTP や古いブラウザ）用のフォールバック付き。 */
const generateUuid = (): string => {
  if (typeof window !== 'undefined' && typeof window.crypto?.randomUUID === 'function') {
    return window.crypto.randomUUID();
  }
  if (typeof window !== 'undefined' && window.crypto?.getRandomValues) {
    const bytes = new Uint8Array(16);
    window.crypto.getRandomValues(bytes);
    bytes[6] = (bytes[6]! & 0x0f) | 0x40;
    bytes[8] = (bytes[8]! & 0x3f) | 0x80;
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }
  return `fallback-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
};

const getOrCreateVisitorId = (): string => {
  if (typeof window === 'undefined') {
    return 'anonymous';
  }

  const existing = window.localStorage.getItem(VISITOR_ID_STORAGE_KEY);
  if (existing) {
    return existing;
  }

  const created = generateUuid();
  window.localStorage.setItem(VISITOR_ID_STORAGE_KEY, created);
  return created;
};

const clearVisitorId = (): void => {
  if (typeof window === 'undefined') {
    return;
  }

  window.localStorage.removeItem(VISITOR_ID_STORAGE_KEY);
};

const createSessionId = (): string => generateUuid();

const toLocale = (language: 'ja' | 'en'): string => (language === 'ja' ? 'ja-JP' : 'en-US');

const normalizeSessionState = (mode: string): VoiceSessionState =>
  mode === 'listening' || mode === 'processing' || mode === 'speaking' ? mode : 'idle';

const toBase64 = async (blob: Blob): Promise<string> => {
  const arrayBuffer = await blob.arrayBuffer();
  return VoiceRecorder.arrayBufferToBase64(arrayBuffer);
};

const stopAudioPlayback = (
  audioQueueRef: MutableRefObject<AudioQueue | null>,
  mobileAudioServiceRef: MutableRefObject<MobileAudioService | null>,
  onVisemeControl?: ((viseme: string, intensity: number) => void) | null,
) => {
  audioStateManager.stopAll();
  audioQueueRef.current?.clear();
  mobileAudioServiceRef.current?.stop();
  onVisemeControl?.('Closed', 0);
};

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
  const [mediaStream, setMediaStream] = useState<MediaStream | null>(null);

  const sessionIdRef = useRef(createSessionId());
  const visitorIdRef = useRef<string>('anonymous');
  const recorderRef = useRef<VoiceRecorder | null>(null);
  const lastRecorderInitErrorRef = useRef<Error | null>(null);
  const shouldDiscardNextAudioRef = useRef(false);
  const requestAbortRef = useRef<AbortController | null>(null);
  const lipSyncAnalyzerRef = useRef<LipSyncAnalyzer | null>(null);
  const lipSyncTimersRef = useRef<number[]>([]);
  const audioQueueRef = useRef<AudioQueue | null>(null);
  const mobileAudioServiceRef = useRef<MobileAudioService | null>(null);
  const audioUrlRef = useRef<string | null>(null);
  const isRecordingRef = useRef(false);
  const isStartingRecorderRef = useRef(false);
  const shouldListenRef = useRef(false);
  const fastFillerTimerRef = useRef<number | null>(null);
  const fastFillerUtteranceRef = useRef<SpeechSynthesisUtterance | null>(null);

  useEffect(() => {
    visitorIdRef.current = getOrCreateVisitorId();
  }, []);

  useEffect(() => {
    const q = new AudioQueue();
    audioQueueRef.current = q;
    q.setVolume(isMuted ? 0 : volume);
    return () => {
      q.clear();
      audioQueueRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount bootstrap only
  }, []);

  useEffect(() => {
    setCurrentLanguage(language);
  }, [language]);

  useEffect(() => {
    onMetadataChange?.(metadata);
  }, [metadata, onMetadataChange]);

  const clearLipSyncTimers = useCallback(() => {
    lipSyncTimersRef.current.forEach((id) => cancelAnimationFrame(id));
    lipSyncTimersRef.current = [];
    onVisemeControl?.('Closed', 0);
  }, [onVisemeControl]);

  const revokeAudioUrl = useCallback(() => {
    if (!audioUrlRef.current) {
      return;
    }

    URL.revokeObjectURL(audioUrlRef.current);
    audioUrlRef.current = null;
  }, []);

  const cleanupAudioPlayback = useCallback(() => {
    clearLipSyncTimers();
    revokeAudioUrl();
  }, [clearLipSyncTimers, revokeAudioUrl]);

  const cancelPendingRequest = useCallback(() => {
    requestAbortRef.current?.abort();
    requestAbortRef.current = null;
  }, []);

  const cancelFastFiller = useCallback(() => {
    if (fastFillerTimerRef.current !== null) {
      window.clearTimeout(fastFillerTimerRef.current);
      fastFillerTimerRef.current = null;
    }
    fastFillerUtteranceRef.current = null;
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
  }, []);

  const scheduleFastFiller = useCallback(() => {
    if (
      !FAST_FILLER_ENABLED ||
      isMuted ||
      typeof window === 'undefined' ||
      !('speechSynthesis' in window) ||
      typeof SpeechSynthesisUtterance === 'undefined'
    ) {
      return;
    }

    if (fastFillerTimerRef.current !== null) {
      window.clearTimeout(fastFillerTimerRef.current);
    }

    fastFillerTimerRef.current = window.setTimeout(() => {
      fastFillerTimerRef.current = null;
      const utterance = new SpeechSynthesisUtterance(
        FAST_FILLER_TEXT[currentLanguage],
      );
      utterance.lang = toLocale(currentLanguage);
      utterance.volume = Math.max(0, Math.min(1, volume));
      utterance.rate = currentLanguage === 'ja' ? 1.08 : 1.0;
      utterance.pitch = 1.0;
      utterance.onend = () => {
        if (fastFillerUtteranceRef.current === utterance) {
          fastFillerUtteranceRef.current = null;
        }
      };
      utterance.onerror = utterance.onend;
      fastFillerUtteranceRef.current = utterance;
      window.speechSynthesis.speak(utterance);
    }, FAST_FILLER_DELAY_MS);
  }, [currentLanguage, isMuted, volume]);

  const ensureAudioService = useCallback(() => {
    if (!mobileAudioServiceRef.current) {
      mobileAudioServiceRef.current = new MobileAudioService({ volume });
    }

    mobileAudioServiceRef.current.setVolume(volume);
    return mobileAudioServiceRef.current;
  }, [volume]);

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
  });

  const sessionState = normalizeSessionState(voiceController.mode);

  useEffect(() => {
    shouldListenRef.current = voiceController.shouldListen;
  }, [voiceController.shouldListen]);

  const setVolume = useCallback((nextVolume: number) => {
    setVolumeState(nextVolume);
    const effectiveVolume = isMuted ? 0 : nextVolume;
    mobileAudioServiceRef.current?.setVolume(effectiveVolume);
    audioQueueRef.current?.setVolume(effectiveVolume);
  }, [isMuted]);

  const setMuted = useCallback((nextMuted: boolean) => {
    setIsMuted(nextMuted);
    const effectiveVolume = nextMuted ? 0 : volume;
    mobileAudioServiceRef.current?.setVolume(effectiveVolume);
    audioQueueRef.current?.setVolume(effectiveVolume);
  }, [volume]);

  const handleAudioUnlockGesture = useCallback(() => {
    if (sessionState === 'listening') {
      return;
    }

    unlockAudioForUserGesture();
  }, [sessionState]);

  const stopForIOSAudioUnlock = useCallback((): boolean => {
    if (!isIOSWebKitAudio()) {
      return false;
    }

    let state: AudioContextState | null = null;
    let isReady = false;
    try {
      const manager = AudioInteractionManager.getInstance();
      state = manager.getAudioContextState();
      isReady = manager.isAudioContextReady() && state === 'running';
    } catch {
      isReady = false;
    }

    if (isReady) {
      return false;
    }

    const message = getTapToEnableAudioMessage(currentLanguage);
    console.warn('[VoiceInterface] iOS AudioContext is not ready; waiting for a tap-to-enable gesture', {
      state,
    });
    cleanupAudioPlayback();
    setError(message);
    setIsLoading(false);
    setLoadingMessage('');
    setLoadingPhase(null);
    voiceController.notifySpeakingComplete(true);
    return true;
  }, [cleanupAudioPlayback, currentLanguage, voiceController]);

  const resetConversation = useCallback(() => {
    setTranscript('');
    setResponse('');
    setMetadata(null);
    setError(null);
    setIsLoading(false);
    setLoadingMessage('');
    setLoadingPhase(null);
    sessionIdRef.current = createSessionId();
  }, []);

  const ensureVisitorId = useCallback((): string => {
    if (visitorIdRef.current !== 'anonymous') {
      return visitorIdRef.current;
    }

    const nextVisitorId = getOrCreateVisitorId();
    visitorIdRef.current = nextVisitorId;
    return nextVisitorId;
  }, []);

  const scheduleLipSyncFrames = useCallback(
    (frames: LipSyncFrame[]) => {
      if (!onVisemeControl || frames.length === 0) {
        return;
      }
      clearLipSyncTimers();
      const startTime = performance.now();
      const lastFrameTime = frames[frames.length - 1].time;

      let frameIndex = 0;

      const update = () => {
        const elapsed = (performance.now() - startTime) / 1000;
        while (
          frameIndex < frames.length - 1 &&
          frames[frameIndex + 1].time <= elapsed
        ) {
          frameIndex++;
        }
        if (frameIndex < frames.length && frames[frameIndex].time <= elapsed) {
          onVisemeControl(frames[frameIndex].mouthShape, frames[frameIndex].mouthOpen);
        }
        if (elapsed < lastFrameTime + 0.5) {
          const rafId = requestAnimationFrame(update);
          lipSyncTimersRef.current = [rafId];
        } else {
          onVisemeControl('Closed', 0);
        }
      };

      const rafId = requestAnimationFrame(update);
      lipSyncTimersRef.current = [rafId];
    },
    [clearLipSyncTimers, onVisemeControl],
  );

  const stopPlayback = useCallback(
    (completeTurn: boolean) => {
      cancelFastFiller();
      stopAudioPlayback(audioQueueRef, mobileAudioServiceRef, onVisemeControl);
      cleanupAudioPlayback();

      if (completeTurn) {
        voiceController.notifySpeakingComplete(skipAssistantTurnAutoResume);
      }
    },
    [
      cancelFastFiller,
      cleanupAudioPlayback,
      onVisemeControl,
      skipAssistantTurnAutoResume,
      voiceController,
    ],
  );

  const playAssistantAudio = useCallback(
    async (audioBase64: string, metadataForPlayback?: VoiceInterfaceMetadata | null) => {
      cancelFastFiller();
      if (isMuted) {
        voiceController.notifySpeaking();
        onAssistantPlaybackStart?.({ metadata: metadataForPlayback ?? null });
        window.setTimeout(() => {
          voiceController.notifySpeakingComplete(skipAssistantTurnAutoResume);
        }, 240);
        return;
      }

      if (stopForIOSAudioUnlock()) {
        return;
      }

      let audioBytes: Uint8Array;
      try {
        audioBytes = Uint8Array.from(atob(audioBase64), (char) => char.charCodeAt(0));
      } catch (decodeError) {
        console.error('Audio decode failed:', decodeError);
        voiceController.notifySpeakingComplete(true);
        return;
      }
      const detectedFormat = AudioDataProcessor.detectAudioFormat(audioBytes.buffer as ArrayBuffer);
      const audioBlob = new Blob([audioBytes], { type: detectedFormat });
      const audioUrl = URL.createObjectURL(audioBlob);
      const audioService = ensureAudioService();

      revokeAudioUrl();
      audioUrlRef.current = audioUrl;

      let lipSyncFrames: LipSyncFrame[] | null = null;
      if (!metadataForPlayback?.vrm_control && onVisemeControl) {
        try {
          if (!lipSyncAnalyzerRef.current) {
            lipSyncAnalyzerRef.current = new LipSyncAnalyzer();
          }
          const lipSyncData = await lipSyncAnalyzerRef.current.analyzeLipSync(audioBlob);
          lipSyncFrames = lipSyncData.frames;
        } catch {
          clearLipSyncTimers();
          lipSyncFrames = null;
        }
      }

      setLoadingMessage(LOADING_LABELS[currentLanguage].speaking);
      setLoadingPhase('tts');
      voiceController.notifySpeaking();

      audioService.updateEventHandlers({
        onPlay: () => {
          onAssistantPlaybackStart?.({ metadata: metadataForPlayback ?? null });
          if (lipSyncFrames && lipSyncFrames.length > 0) {
            scheduleLipSyncFrames(lipSyncFrames);
          }
        },
        onEnded: () => {
          cleanupAudioPlayback();
          voiceController.notifySpeakingComplete(skipAssistantTurnAutoResume);
        },
        onError: (playbackError) => {
          cleanupAudioPlayback();
          setError(formatError(playbackError, currentLanguage));
          voiceController.notifySpeakingComplete(true);
        },
      });

      const result = await audioService.playAudio(audioBlob);
      if (!result.success) {
        cleanupAudioPlayback();
        voiceController.notifySpeakingComplete(true);
        throw result.error ?? new Error('音声再生に失敗しました');
      }
    },
    [
      cleanupAudioPlayback,
      cancelFastFiller,
      clearLipSyncTimers,
      currentLanguage,
      ensureAudioService,
      isMuted,
      onAssistantPlaybackStart,
      onVisemeControl,
      revokeAudioUrl,
      scheduleLipSyncFrames,
      skipAssistantTurnAutoResume,
      stopForIOSAudioUnlock,
      voiceController,
    ],
  );

  const processVoiceTurnWithParallelFiller = useCallback(
    async (trimmed: string, abortController: AbortController) => {
      const signal = abortController.signal;
      const visitorId = ensureVisitorId();
      const fillerGate = createVoiceFillerPlaybackGate(signal);

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
                const res = await fetch('/api/voice/filler', {
                  method: 'POST',
                  headers: {
                    'Content-Type': 'application/json',
                  },
                  body: JSON.stringify({
                    query: trimmed,
                    language: currentLanguage,
                    sessionId: sessionIdRef.current,
                  }),
                  signal,
                });
                if (!res.ok) {
                  return;
                }
                const data = (await res.json()) as Record<string, unknown>;
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
        const qaResponse = await fetch('/api/qa', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            action: 'ask',
            question: trimmed,
            text: trimmed,
            sessionId: sessionIdRef.current,
            language: currentLanguage,
            visitorId,
          }),
          signal,
        });

        const qaResult = await qaResponse.json();
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

        setResponse(cleanAnswer);
        setMetadata((qaResult.metadata as VoiceInterfaceMetadata | null) ?? null);

        const ttsBody: Record<string, unknown> = {
          action: 'text_to_speech',
          text: preprocessTTS(cleanAnswer, currentLanguage),
          language: currentLanguage,
          sessionId: sessionIdRef.current,
          includeVrmControl: true,
        };
        if (typeof qaResult.emotion === 'string' && qaResult.emotion.trim()) {
          ttsBody.emotion = qaResult.emotion.trim();
        }

        const ttsResponse = await fetch('/api/voice', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(ttsBody),
          signal,
        });

        const ttsResult = (await ttsResponse.json()) as Record<string, unknown>;
        if (!ttsResponse.ok || !ttsResult.success) {
          const ttsError: Error & { status?: number } = new Error(
            (typeof ttsResult.error === 'string' ? ttsResult.error : null) ||
              '音声の生成に失敗しました',
          );
          ttsError.status = ttsResponse.status;
          throw ttsError;
        }

        fillerGate.close();
        // Filler runs in parallel; do not await — slow filler must not delay main TTS enqueue.
        void fillerTask.catch(() => {});

        const qaMeta = (qaResult.metadata as VoiceInterfaceMetadata | null) ?? null;
        const playbackMetadata = mergePlaybackMetadataWithTtsVrmControl(qaMeta, ttsResult);

        if (isMuted) {
          cancelFastFiller();
          voiceController.notifySpeaking();
          onAssistantPlaybackStart?.({ metadata: playbackMetadata ?? null });
          window.setTimeout(() => {
            voiceController.notifySpeakingComplete(skipAssistantTurnAutoResume);
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
            voiceController.notifySpeakingComplete(true);
            return;
          }
          const detectedFormat = AudioDataProcessor.detectAudioFormat(audioBytes.buffer as ArrayBuffer);
          const responseBlob = new Blob([audioBytes], { type: detectedFormat });

          let lipSyncFrames: LipSyncFrame[] | null = null;
          if (!playbackMetadata?.vrm_control && onVisemeControl) {
            try {
              if (!lipSyncAnalyzerRef.current) {
                lipSyncAnalyzerRef.current = new LipSyncAnalyzer();
              }
              const lipSyncData = await lipSyncAnalyzerRef.current.analyzeLipSync(responseBlob);
              lipSyncFrames = lipSyncData.frames;
            } catch {
              clearLipSyncTimers();
              lipSyncFrames = null;
            }
          }

          const q = audioQueueRef.current;
          if (!q) {
            await playAssistantAudio(ttsResult.audioResponse, playbackMetadata);
            return;
          }
          if (stopForIOSAudioUnlock()) {
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
              voiceController.notifySpeakingComplete(skipAssistantTurnAutoResume);
            },
          });
        } else {
          cancelFastFiller();
          voiceController.notifySpeaking();
          window.setTimeout(() => {
            voiceController.notifySpeakingComplete(skipAssistantTurnAutoResume);
          }, 240);
        }
      } catch (voiceError) {
        fillerGate.close();
        if (voiceError instanceof DOMException && voiceError.name === 'AbortError') {
          return;
        }
        cancelFastFiller();
        setError(formatError(voiceError, currentLanguage));
        voiceController.notifySpeakingComplete(true);
      }
    },
    [
      cancelFastFiller,
      cleanupAudioPlayback,
      clearLipSyncTimers,
      currentLanguage,
      ensureVisitorId,
      isMuted,
      onAssistantPlaybackStart,
      onVisemeControl,
      onVoiceTurnAssistantSpeakingVisual,
      onVoiceTurnThinkingVisual,
      playAssistantAudio,
      scheduleLipSyncFrames,
      skipAssistantTurnAutoResume,
      stopForIOSAudioUnlock,
      stopPlayback,
      volume,
      voiceController,
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
        const qaResponse = await fetch('/api/qa', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            action: 'ask',
            question: trimmed,
            text: trimmed,
            sessionId: sessionIdRef.current,
            language: currentLanguage,
            visitorId,
          }),
          signal: abortController.signal,
        });

        const qaResult = await qaResponse.json();
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

        setResponse(cleanAnswer);
        setMetadata((qaResult.metadata as VoiceInterfaceMetadata | null) ?? null);

        const ttsBody: Record<string, unknown> = {
          action: 'text_to_speech',
          text: preprocessTTS(cleanAnswer, currentLanguage),
          language: currentLanguage,
          sessionId: sessionIdRef.current,
          includeVrmControl: true,
        };
        if (typeof qaResult.emotion === 'string' && qaResult.emotion.trim()) {
          ttsBody.emotion = qaResult.emotion.trim();
        }

        const ttsResponse = await fetch('/api/voice', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(ttsBody),
          signal: abortController.signal,
        });

        const ttsResult = (await ttsResponse.json()) as Record<string, unknown>;
        if (!ttsResponse.ok || !ttsResult.success) {
          const ttsError: Error & { status?: number } = new Error(
            (typeof ttsResult.error === 'string' ? ttsResult.error : null) ||
              '音声の生成に失敗しました',
          );
          ttsError.status = ttsResponse.status;
          throw ttsError;
        }

        const qaMeta = (qaResult.metadata as VoiceInterfaceMetadata | null) ?? null;
        const playbackMetadata = mergePlaybackMetadataWithTtsVrmControl(qaMeta, ttsResult);

        if (typeof ttsResult.audioResponse === 'string' && ttsResult.audioResponse.length > 0) {
          await playAssistantAudio(ttsResult.audioResponse, playbackMetadata);
        } else {
          cancelFastFiller();
          voiceController.notifySpeaking();
          window.setTimeout(() => {
            voiceController.notifySpeakingComplete(skipAssistantTurnAutoResume);
          }, 240);
        }
      } catch (sendError) {
        if (sendError instanceof DOMException && sendError.name === 'AbortError') {
          return;
        }

        cancelFastFiller();
        setError(formatError(sendError, currentLanguage));
        voiceController.notifySpeakingComplete(true);
      } finally {
        if (requestAbortRef.current === abortController) {
          requestAbortRef.current = null;
        }
        setIsLoading(false);
        setLoadingMessage('');
        setLoadingPhase(null);
      }
    },
    [
      cancelPendingRequest,
      cancelFastFiller,
      currentLanguage,
      ensureVisitorId,
      playAssistantAudio,
      scheduleFastFiller,
      skipAssistantTurnAutoResume,
      stopPlayback,
      voiceController,
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
        const ttsBody: Record<string, unknown> = {
          action: 'text_to_speech',
          text: preprocessTTS(cleanAnswer, currentLanguage),
          language: currentLanguage,
          sessionId: sessionIdRef.current,
          includeVrmControl: true,
        };
        if (parsedAnswer.primaryEmotion) {
          ttsBody.emotion = parsedAnswer.primaryEmotion;
        }

        const ttsResponse = await fetch('/api/voice', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(ttsBody),
          signal: abortController.signal,
        });

        const ttsResult = (await ttsResponse.json()) as Record<string, unknown>;
        if (!ttsResponse.ok || !ttsResult.success) {
          throw new Error(
            (typeof ttsResult.error === 'string' ? ttsResult.error : null) ||
              '音声の生成に失敗しました',
          );
        }

        const playbackMetadata = mergePlaybackMetadataWithTtsVrmControl(
          metadataForPlayback ?? null,
          ttsResult,
        );

        if (typeof ttsResult.audioResponse === 'string' && ttsResult.audioResponse.length > 0) {
          await playAssistantAudio(ttsResult.audioResponse, playbackMetadata);
        } else {
          voiceController.notifySpeaking();
          window.setTimeout(() => {
            voiceController.notifySpeakingComplete(skipAssistantTurnAutoResume);
          }, 240);
        }
      } catch (speakError) {
        if (speakError instanceof DOMException && speakError.name === 'AbortError') {
          return;
        }

        setError(formatError(speakError, currentLanguage));
        voiceController.notifySpeakingComplete(true);
      } finally {
        if (requestAbortRef.current === abortController) {
          requestAbortRef.current = null;
        }
        setIsLoading(false);
        setLoadingMessage('');
        setLoadingPhase(null);
      }
    },
    [
      cancelPendingRequest,
      currentLanguage,
      playAssistantAudio,
      skipAssistantTurnAutoResume,
      stopPlayback,
      voiceController,
    ],
  );

  const handleRecordedAudio = useCallback(
    async (audioBlob: Blob) => {
      if (shouldDiscardNextAudioRef.current) {
        shouldDiscardNextAudioRef.current = false;
        return;
      }

      cancelPendingRequest();
      setError(null);
      setIsLoading(true);
      setLoadingMessage(LOADING_LABELS[currentLanguage].recognize);
      setLoadingPhase('stt');

      const abortController = new AbortController();
      requestAbortRef.current = abortController;

      try {
        const sttResponse = await fetch('/api/voice', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            action: 'speech_to_text',
            audioData: await toBase64(audioBlob),
            language: currentLanguage,
          }),
          signal: abortController.signal,
        });

        const sttResult = await sttResponse.json();
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

        setError(formatError(recordingError, currentLanguage));
        voiceController.notifySpeakingComplete(true);
      } finally {
        if (requestAbortRef.current === abortController) {
          requestAbortRef.current = null;
        }
        setIsLoading(false);
        setLoadingMessage('');
        setLoadingPhase(null);
      }
    },
    [cancelPendingRequest, currentLanguage, processVoiceTurnWithParallelFiller, voiceController],
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
      void startRecorderCapture();
      return;
    }

    if (isRecordingRef.current) {
      stopRecorderCapture(sessionState === 'idle');
    }
  }, [sessionState, startRecorderCapture, stopRecorderCapture, voiceController.shouldListen]);

  const startListening = useCallback(async (): Promise<boolean> => {
    unlockAudioForUserGesture();
    shouldListenRef.current = true;
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
  }, [cancelPendingRequest, currentLanguage, startRecorderCapture, stopPlayback, voiceController]);

  const stopListening = useCallback(() => {
    shouldListenRef.current = false;
    voiceController.notifyProcessing();
  }, [voiceController]);

  const cancelSession = useCallback(() => {
    cancelSttWarmup();
    cancelFastFiller();
    cancelPendingRequest();
    stopPlayback(false);
    shouldDiscardNextAudioRef.current = true;
    stopRecorderCapture(true);
    setIsLoading(false);
    setLoadingMessage('');
    setLoadingPhase(null);
    voiceController.endManualSession();
  }, [
    cancelFastFiller,
    cancelPendingRequest,
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

  useEffect(() => {
    return () => {
      cancelFastFiller();
      cancelPendingRequest();
      cleanupAudioPlayback();
      recorderRef.current?.cleanup();
      lipSyncAnalyzerRef.current?.dispose();
      mobileAudioServiceRef.current?.dispose();
    };
  }, [cancelFastFiller, cancelPendingRequest, cleanupAudioPlayback]);

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

  const statusText = isLoading && loadingMessage ? loadingMessage : STATUS_LABELS[currentLanguage][sessionState];
  const isListening = sessionState === 'listening';
  const isSpeaking = sessionState === 'speaking';
  const isBusy = sessionState === 'processing' || isLoading;
  const waveformActive = isListening || isSpeaking;

  return (
    <div
      className={cn(
        'rounded-3xl border border-slate-200 bg-white/90 p-6 shadow-sm backdrop-blur-sm',
        layout === 'horizontal' ? 'w-full' : 'max-w-md',
        className,
      )}
    >
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <p className="text-sm font-medium text-slate-500">{currentLanguage.toUpperCase()}</p>
          <h2 className="text-balance text-lg font-semibold text-slate-900">{statusText}</h2>
        </div>
        <div
          className={cn(
            'size-3 rounded-full',
            sessionState === 'idle' && 'bg-slate-300',
            sessionState === 'listening' && 'bg-emerald-500 motion-safe:animate-pulse',
            sessionState === 'processing' && 'bg-amber-500 motion-safe:animate-pulse',
            sessionState === 'speaking' && 'bg-sky-500 motion-safe:animate-pulse',
          )}
        />
      </div>

      <div className="mt-6 flex items-center justify-center gap-3">
        <button
          type="button"
          onPointerDown={handleAudioUnlockGesture}
          onTouchEnd={handleAudioUnlockGesture}
          onClick={isListening ? stopListening : startListening}
          disabled={isBusy && !isListening}
          aria-label={isListening ? '録音を停止' : '録音を開始'}
          className={cn(
            'flex size-20 items-center justify-center rounded-full text-white shadow-sm transition-transform duration-200',
            isListening ? 'bg-rose-500 motion-safe:scale-105' : 'bg-slate-900',
            isBusy && !isListening && 'cursor-not-allowed bg-slate-400',
          )}
        >
          {isBusy && !isListening ? (
            <Loader2 className="size-8 animate-spin" />
          ) : isListening ? (
            <MicOff className="size-8" />
          ) : (
            <Mic className="size-8" />
          )}
        </button>

        <button
          type="button"
          onClick={cancelSession}
          aria-label="セッションをキャンセル"
          className="flex size-12 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-700 shadow-sm transition-colors duration-200 hover:bg-slate-50"
        >
          <XCircle className="size-5" />
        </button>

        <button
          type="button"
          onPointerDown={handleAudioUnlockGesture}
          onTouchEnd={handleAudioUnlockGesture}
          onClick={() => setMuted(!isMuted)}
          aria-label={isMuted ? 'ミュートを解除' : 'ミュートにする'}
          className="flex size-12 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-700 shadow-sm transition-colors duration-200 hover:bg-slate-50"
        >
          {isMuted ? <VolumeX className="size-5" /> : <Volume2 className="size-5" />}
        </button>
      </div>

      <div className="mt-5 flex items-center justify-center gap-1.5">
        {(waveformActive ? renderProps.waveformBars : [0.2, 0.24, 0.2, 0.18, 0.22]).map((bar, index) => (
          <span
            key={`${index}-${bar}`}
            className={cn(
              'w-1 rounded-full bg-slate-900 transition-transform duration-150',
              waveformActive ? 'motion-safe:animate-pulse' : 'bg-slate-300',
            )}
            style={{ height: '40px', transform: `scaleY(${Math.max(bar, 0.18)})` }}
          />
        ))}
      </div>

      {!isMuted && (
        <div className="mt-5">
          <div className="mb-2 flex items-center justify-between text-sm text-slate-600">
            <span>音量</span>
            <span>{Math.round(volume * 100)}%</span>
          </div>
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={volume}
            onChange={(event) => setVolume(Number(event.target.value))}
            className="w-full accent-slate-900"
          />
        </div>
      )}

      {(transcript || response) && (
        <div className="mt-5 rounded-2xl bg-slate-50 p-4">
          {transcript && (
            <p className="text-pretty text-sm text-slate-600">
              <span className="mr-2 font-medium text-slate-900">
                {currentLanguage === 'ja' ? 'あなた' : 'You'}
              </span>
              {transcript}
            </p>
          )}
          {response && (
            <p className="mt-3 text-pretty text-sm leading-6 text-slate-800">{response}</p>
          )}
        </div>
      )}

      {error && (
        <div className="mt-5 flex items-start gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-rose-700">
          <AlertCircle className="mt-0.5 size-4 shrink-0" />
          <p className="text-pretty text-sm">{error}</p>
        </div>
      )}
    </div>
  );
}
