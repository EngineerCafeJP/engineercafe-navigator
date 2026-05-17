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
import { submitQaQuestion } from '@/lib/api/qa-client';
import { requestAutoCharacterControl } from '@/lib/api/character-client';
import {
  interruptVoiceSession,
  requestVoiceFiller,
  sendVoiceClientTelemetry,
  speechToText,
  textToSpeech,
  type TextToSpeechPayload,
} from '@/lib/api/voice-client';
import { LipSyncAnalyzer, type LipSyncFrame } from '@/lib/lip-sync-analyzer';
import { createVoiceFillerPlaybackGate } from '@/lib/voice-filler-playback';
import { resolveVoiceResponseLanguage } from '@/lib/voice/response-language';
import { isSlideAgentMetadata } from '@/lib/voice/slide-agent-metadata';
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
export type VoiceUiLockState = 'normal' | 'locked' | 'interruptible';

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
  uiLockState: VoiceUiLockState;
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
  unlockAudioPlayback: () => boolean;
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
  /** Consumes SlideAgent responses so the kiosk can open the PDF guide instead of speaking slide text. */
  onSlideAgentResponse?: (payload: {
    answer: string;
    metadata: VoiceInterfaceMetadata | null;
  }) => void;
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

const PARALLEL_VOICE_FILLER_ENABLED =
  process.env.NEXT_PUBLIC_PARALLEL_VOICE_FILLER !== 'false';
const AUTO_VRM_PLAYBACK_WAIT_MS = 180;
const FALLBACK_NOTICE_LIMIT_PER_SESSION = 2;
const FALLBACK_NOTICE_TEXT: Record<'ja' | 'en', string> = {
  ja: '音声の再生に失敗しました。もう一度お試しください。',
  en: 'Audio playback failed. Please try again.',
};

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

type VoiceTimingTelemetry = {
  durationMs?: number;
  sttMs?: number;
  qaMs?: number;
  ttsMs?: number;
  playbackStartMs?: number;
  turnTotalMs?: number;
  requestMode?: string;
  usedProxyFallback?: boolean;
  status?: number;
  upstreamStatus?: Record<string, unknown> | null;
  from?: string;
  to?: string;
  characterState?: string;
  isConversationActive?: boolean;
  shouldListen?: boolean;
};

const elapsedMs = (startedAt: number): number => Math.max(0, Math.round(performance.now() - startedAt));

const isAudioGestureRequiredError = (error: unknown): boolean => {
  if (
    typeof error === 'object' &&
    error !== null &&
    'requiresUserInteraction' in error &&
    error.requiresUserInteraction === true
  ) {
    return true;
  }

  if (
    typeof error === 'object' &&
    error !== null &&
    'type' in error &&
    error.type === 'user_interaction_required'
  ) {
    return true;
  }

  if (error instanceof Error) {
    const message = error.message.toLowerCase();
    return (
      error.name === 'NotAllowedError' ||
      message.includes('user interaction') ||
      message.includes('user gesture') ||
      message.includes('autoplay')
    );
  }

  return false;
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
  const lipSyncAnalyzerRef = useRef<LipSyncAnalyzer | null>(null);
  const lipSyncTimersRef = useRef<number[]>([]);
  const audioQueueRef = useRef<AudioQueue | null>(null);
  const mobileAudioServiceRef = useRef<MobileAudioService | null>(null);
  const audioUrlRef = useRef<string | null>(null);
  const isRecordingRef = useRef(false);
  const isStartingRecorderRef = useRef(false);
  const shouldListenRef = useRef(false);
  const isStoppingRecorderRef = useRef(false);
  const voiceTurnInProgressRef = useRef(false);
  const forceSkipAutoResumeRef = useRef(false);
  const fastFillerTimerRef = useRef<number | null>(null);
  const pendingIOSPlaybackRef = useRef<{
    audioBase64: string;
    metadata: VoiceInterfaceMetadata | null;
  } | null>(null);
  const isReplayingPendingIOSAudioRef = useRef(false);
  const pendingIOSPlaybackReplayTokenRef = useRef(0);
  const fallbackNoticeCountRef = useRef(0);

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

  const ensureAudioService = useCallback(() => {
    if (!mobileAudioServiceRef.current) {
      mobileAudioServiceRef.current = new MobileAudioService({ volume });
    }

    mobileAudioServiceRef.current.setVolume(volume);
    return mobileAudioServiceRef.current;
  }, [volume]);

  const playAudioFallbackNotice = useCallback(() => {
    const message = FALLBACK_NOTICE_TEXT[currentLanguage];
    setError(message);

    if (isMuted || typeof window === 'undefined') {
      return;
    }
    if (fallbackNoticeCountRef.current >= FALLBACK_NOTICE_LIMIT_PER_SESSION) {
      return;
    }
    fallbackNoticeCountRef.current += 1;

    try {
      const AudioContextCtor =
        window.AudioContext ||
        (window as typeof window & { webkitAudioContext?: typeof AudioContext })
          .webkitAudioContext;
      if (AudioContextCtor) {
        const ctx = new AudioContextCtor();
        const oscillator = ctx.createOscillator();
        const gain = ctx.createGain();
        oscillator.type = 'sine';
        oscillator.frequency.value = 880;
        gain.gain.value = 0.08;
        oscillator.connect(gain);
        gain.connect(ctx.destination);
        oscillator.start();
        window.setTimeout(() => {
          oscillator.stop();
          void ctx.close().catch(() => {});
        }, 120);
      }
    } catch {
      // Best-effort fallback cue.
    }

    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(message);
      utterance.lang = toLocale(currentLanguage);
      utterance.volume = Math.max(0.2, Math.min(1, volume));
      window.speechSynthesis.speak(utterance);
    }
  }, [currentLanguage, isMuted, volume]);

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
    onThinkingWatchdogExpire: playAudioFallbackNotice,
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
  }, [isMuted]);

  const setMuted = useCallback((nextMuted: boolean) => {
    setIsMuted(nextMuted);
    const effectiveVolume = nextMuted ? 0 : volume;
    mobileAudioServiceRef.current?.setVolume(effectiveVolume);
    audioQueueRef.current?.setVolume(effectiveVolume);
  }, [volume]);

  const deferForIOSAudioUnlock = useCallback((
    pendingPlayback?: {
      audioBase64: string;
      metadata: VoiceInterfaceMetadata | null;
    },
  ): boolean => {
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

    if (pendingPlayback) {
      pendingIOSPlaybackRef.current = pendingPlayback;
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
    setExclusiveUiLock(false);
    completeAssistantTurn(true);
    return true;
  }, [cleanupAudioPlayback, completeAssistantTurn, currentLanguage]);

  const resetConversation = useCallback(() => {
    setTranscript('');
    setResponse('');
    setMetadata(null);
    setError(null);
    setIsLoading(false);
    setLoadingMessage('');
    setLoadingPhase(null);
    setExclusiveUiLock(false);
    fallbackNoticeCountRef.current = 0;
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
        completeAssistantTurn();
      }
    },
    [
      cancelFastFiller,
      cleanupAudioPlayback,
      completeAssistantTurn,
      onVisemeControl,
    ],
  );

  const playAssistantAudio = useCallback(
    async (audioBase64: string, metadataForPlayback?: VoiceInterfaceMetadata | null) => {
      cancelFastFiller();
      if (isMuted) {
        voiceController.notifySpeaking();
        onAssistantPlaybackStart?.({ metadata: metadataForPlayback ?? null });
        window.setTimeout(() => {
          completeAssistantTurn();
        }, 240);
        return;
      }

      if (deferForIOSAudioUnlock({
        audioBase64,
        metadata: metadataForPlayback ?? null,
      })) {
        return;
      }

      let audioBytes: Uint8Array;
      try {
        audioBytes = Uint8Array.from(atob(audioBase64), (char) => char.charCodeAt(0));
      } catch (decodeError) {
        console.error('Audio decode failed:', decodeError);
        playAudioFallbackNotice();
        completeAssistantTurn(true);
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
          completeAssistantTurn();
        },
        onError: (playbackError) => {
          cleanupAudioPlayback();
          setError(formatError(playbackError, currentLanguage));
          playAudioFallbackNotice();
          completeAssistantTurn(true);
        },
      });

      const result = await audioService.playAudio(audioBlob);
      if (!result.success) {
        cleanupAudioPlayback();
        playAudioFallbackNotice();
        completeAssistantTurn(true);
        throw result.error ?? new Error('音声再生に失敗しました');
      }
    },
    [
      cleanupAudioPlayback,
      cancelFastFiller,
      clearLipSyncTimers,
      completeAssistantTurn,
      currentLanguage,
      ensureAudioService,
      isMuted,
      onAssistantPlaybackStart,
      playAudioFallbackNotice,
      onVisemeControl,
      revokeAudioUrl,
      scheduleLipSyncFrames,
      deferForIOSAudioUnlock,
      voiceController,
    ],
  );

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
          ttsProvider: request.ttsProvider ?? 'piper',
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

  const unlockAudioPlayback = useCallback((): boolean => {
    if (sessionState === 'listening') {
      return false;
    }

    unlockAudioForUserGesture();

    const pendingPlayback = pendingIOSPlaybackRef.current;
    if (!pendingPlayback || isReplayingPendingIOSAudioRef.current) {
      return false;
    }

    pendingIOSPlaybackRef.current = null;
    isReplayingPendingIOSAudioRef.current = true;
    const replayToken = pendingIOSPlaybackReplayTokenRef.current + 1;
    pendingIOSPlaybackReplayTokenRef.current = replayToken;
    setError(null);

    void (async () => {
      try {
        await AudioInteractionManager.getInstance().forceInitialize();
        if (pendingIOSPlaybackReplayTokenRef.current !== replayToken) {
          return;
        }
        await playAssistantAudio(pendingPlayback.audioBase64, pendingPlayback.metadata);
      } catch (error) {
        if (pendingIOSPlaybackReplayTokenRef.current !== replayToken) {
          return;
        }
        if (isAudioGestureRequiredError(error)) {
          pendingIOSPlaybackRef.current = pendingPlayback;
          setError(getTapToEnableAudioMessage(currentLanguage));
        } else {
          setError(formatError(error, currentLanguage));
        }
      } finally {
        if (pendingIOSPlaybackReplayTokenRef.current === replayToken) {
          isReplayingPendingIOSAudioRef.current = false;
        }
      }
    })();

    return true;
  }, [currentLanguage, playAssistantAudio, sessionState]);

  const cancelPendingIOSPlaybackReplay = useCallback(() => {
    if (!pendingIOSPlaybackRef.current && !isReplayingPendingIOSAudioRef.current) {
      return;
    }

    pendingIOSPlaybackRef.current = null;
    isReplayingPendingIOSAudioRef.current = false;
    pendingIOSPlaybackReplayTokenRef.current += 1;
  }, []);

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
            ttsProvider: 'piper',
          },
          signal,
        );
        emitVoiceTelemetry('voice_turn_timing', 'tts', {
          ttsMs: elapsedMs(ttsStartedAt),
          status: 200,
          upstreamStatus: ttsResult.upstreamStatus ?? null,
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
        playAudioFallbackNotice();
        completeAssistantTurn(true);
      }
    },
    [
      cancelFastFiller,
      cleanupAudioPlayback,
      clearLipSyncTimers,
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
            ttsProvider: 'piper',
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
            ttsProvider: 'piper',
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
    ],
  );

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
    fallbackNoticeCountRef.current = 0;
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
      pendingIOSPlaybackRef.current = null;
      isReplayingPendingIOSAudioRef.current = false;
      pendingIOSPlaybackReplayTokenRef.current += 1;
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
          onPointerDown={unlockAudioForUserGesture}
          onTouchEnd={unlockAudioForUserGesture}
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
          onPointerDown={unlockAudioPlayback}
          onTouchEnd={unlockAudioPlayback}
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
