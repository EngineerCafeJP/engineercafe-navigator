'use client';

import { AudioQueue } from '@/lib/audio-queue';
import { MobileAudioService } from '@/lib/audio/mobile-audio-service';
import { audioStateManager } from '@/lib/audio-state-manager';
import { cn } from '@/lib/cn';
import { EmotionTagParser } from '@/lib/emotion-tag-parser';
import { formatError } from '@/lib/error-messages';
import { LipSyncAnalyzer } from '@/lib/lip-sync-analyzer';
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

export type VoiceSessionState = 'idle' | 'listening' | 'processing' | 'speaking';

export interface VoiceInterfaceMetadata {
  clarification?: {
    clarification_type?: string;
    [key: string]: unknown;
  };
  clarification_options?: string[];
  requires_followup?: boolean;
   reception_type?: string;
  [key: string]: unknown;
}

export interface VoiceInterfaceRenderProps {
  sessionState: VoiceSessionState;
  characterState: VoiceCharacterState;
  transcript: string;
  response: string;
  metadata: VoiceInterfaceMetadata | null;
  error: string | null;
  isLoading: boolean;
  loadingMessage: string;
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
  startListening: () => void;
  stopListening: () => void;
  cancelSession: () => void;
  clearConversation: () => void;
  sendMessage: (message: string) => Promise<void>;
  setVolume: (value: number) => void;
  setMuted: (value: boolean) => void;
  toggleLanguage: () => void;
}

interface VoiceInterfaceProps {
  onLanguageChange?: (language: 'ja' | 'en') => void;
  layout?: 'vertical' | 'horizontal';
  language?: 'ja' | 'en';
  autoGreeting?: boolean;
  onVisemeControl?: ((viseme: string, intensity: number) => void) | null;
  children?: (props: VoiceInterfaceRenderProps) => ReactNode;
  showDefaultUI?: boolean;
  className?: string;
  onMetadataChange?: (metadata: VoiceInterfaceMetadata | null) => void;
}

const DEFAULT_WAKE_WORDS = ['すみません', 'hello'];

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

  const key = 'engineer_cafe_visitor_id';
  const existing = window.localStorage.getItem(key);
  if (existing) {
    return existing;
  }

  const created = generateUuid();
  window.localStorage.setItem(key, created);
  return created;
};

const createSessionId = (): string =>
  `voice-session-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;

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
  autoGreeting = false,
  onVisemeControl,
  children,
  showDefaultUI,
  className,
  onMetadataChange,
}: VoiceInterfaceProps) {
  const [currentLanguage, setCurrentLanguage] = useState<'ja' | 'en'>(language);
  const [volume, setVolumeState] = useState(0.8);
  const [isMuted, setIsMuted] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [response, setResponse] = useState('');
  const [metadata, setMetadata] = useState<VoiceInterfaceMetadata | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadingMessage, setLoadingMessage] = useState('');
  const [mediaStream, setMediaStream] = useState<MediaStream | null>(null);

  const sessionIdRef = useRef(createSessionId());
  const visitorIdRef = useRef<string>('anonymous');
  const recorderRef = useRef<VoiceRecorder | null>(null);
  const shouldDiscardNextAudioRef = useRef(false);
  const requestAbortRef = useRef<AbortController | null>(null);
  const lipSyncAnalyzerRef = useRef<LipSyncAnalyzer | null>(null);
  const lipSyncTimersRef = useRef<number[]>([]);
  const audioQueueRef = useRef<AudioQueue | null>(null);
  const mobileAudioServiceRef = useRef<MobileAudioService | null>(null);
  const audioUrlRef = useRef<string | null>(null);
  const isRecordingRef = useRef(false);

  useEffect(() => {
    visitorIdRef.current = getOrCreateVisitorId();
  }, []);

  useEffect(() => {
    setCurrentLanguage(language);
  }, [language]);

  useEffect(() => {
    onMetadataChange?.(metadata);
  }, [metadata, onMetadataChange]);

  const clearLipSyncTimers = useCallback(() => {
    lipSyncTimersRef.current.forEach((timerId) => window.clearTimeout(timerId));
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

  const ensureAudioService = useCallback(() => {
    if (!mobileAudioServiceRef.current) {
      mobileAudioServiceRef.current = new MobileAudioService({ volume });
    }

    mobileAudioServiceRef.current.setVolume(volume);
    return mobileAudioServiceRef.current;
  }, [volume]);

  const voiceController = useVoiceSessionController({
    enabled: true,
    stream: mediaStream,
    wakeWords: DEFAULT_WAKE_WORDS,
    language: toLocale(currentLanguage),
    onWakeWord: () => {
      setError(null);
    },
  });

  const sessionState = normalizeSessionState(voiceController.mode);

  const setVolume = useCallback((nextVolume: number) => {
    setVolumeState(nextVolume);
    mobileAudioServiceRef.current?.setVolume(nextVolume);
  }, []);

  const setMuted = useCallback((nextMuted: boolean) => {
    setIsMuted(nextMuted);
  }, []);

  const resetConversation = useCallback(() => {
    setTranscript('');
    setResponse('');
    setMetadata(null);
    setError(null);
    setIsLoading(false);
    setLoadingMessage('');
    sessionIdRef.current = createSessionId();
  }, []);

  const applyLipSync = useCallback(
    async (audioBlob: Blob) => {
      if (!onVisemeControl) {
        return;
      }

      if (!lipSyncAnalyzerRef.current) {
        lipSyncAnalyzerRef.current = new LipSyncAnalyzer();
      }

      const lipSyncData = await lipSyncAnalyzerRef.current.analyzeLipSync(audioBlob);
      clearLipSyncTimers();

      lipSyncData.frames.forEach((frame) => {
        const timerId = window.setTimeout(() => {
          onVisemeControl(frame.mouthShape, frame.mouthOpen);
        }, frame.time * 1000);
        lipSyncTimersRef.current.push(timerId);
      });
    },
    [clearLipSyncTimers, onVisemeControl],
  );

  const stopPlayback = useCallback(
    (completeTurn: boolean) => {
      stopAudioPlayback(audioQueueRef, mobileAudioServiceRef, onVisemeControl);
      cleanupAudioPlayback();

      if (completeTurn) {
        voiceController.notifySpeakingComplete();
      }
    },
    [cleanupAudioPlayback, onVisemeControl, voiceController],
  );

  const playAssistantAudio = useCallback(
    async (audioBase64: string) => {
      if (isMuted) {
        voiceController.notifySpeaking();
        window.setTimeout(() => {
          voiceController.notifySpeakingComplete();
        }, 240);
        return;
      }

      let audioBytes: Uint8Array;
      try {
        audioBytes = Uint8Array.from(atob(audioBase64), (char) => char.charCodeAt(0));
      } catch (decodeError) {
        console.error('Audio decode failed:', decodeError);
        voiceController.notifySpeakingComplete();
        return;
      }
      const audioBlob = new Blob([audioBytes], { type: 'audio/mpeg' });
      const audioUrl = URL.createObjectURL(audioBlob);
      const audioService = ensureAudioService();

      revokeAudioUrl();
      audioUrlRef.current = audioUrl;

      setLoadingMessage(LOADING_LABELS[currentLanguage].speaking);
      voiceController.notifySpeaking();

      await applyLipSync(audioBlob).catch(() => {
        clearLipSyncTimers();
      });

      audioService.updateEventHandlers({
        onEnded: () => {
          cleanupAudioPlayback();
          voiceController.notifySpeakingComplete();
        },
        onError: (playbackError) => {
          cleanupAudioPlayback();
          setError(formatError(playbackError, currentLanguage));
          voiceController.notifySpeakingComplete();
        },
      });

      const result = await audioService.playAudio(audioUrl);
      if (!result.success) {
        cleanupAudioPlayback();
        voiceController.notifySpeakingComplete();
        throw result.error ?? new Error('音声再生に失敗しました');
      }
    },
    [
      applyLipSync,
      cleanupAudioPlayback,
      clearLipSyncTimers,
      currentLanguage,
      ensureAudioService,
      isMuted,
      revokeAudioUrl,
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
      voiceController.notifyProcessing();

      const abortController = new AbortController();
      requestAbortRef.current = abortController;

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
            visitorId: visitorIdRef.current,
          }),
          signal: abortController.signal,
        });

        const qaResult = await qaResponse.json();
        if (!qaResponse.ok || !qaResult.success) {
          throw new Error(qaResult.error || '質問の送信に失敗しました');
        }

        const parsedAnswer = EmotionTagParser.parseEmotionTags(
          typeof qaResult.answer === 'string' ? qaResult.answer : '',
        );
        const cleanAnswer = parsedAnswer.cleanText;

        setResponse(cleanAnswer);
        setMetadata((qaResult.metadata as VoiceInterfaceMetadata | null) ?? null);

        const ttsResponse = await fetch('/api/voice', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            action: 'text_to_speech',
            text: preprocessTTS(cleanAnswer, currentLanguage),
            language: currentLanguage,
            sessionId: sessionIdRef.current,
          }),
          signal: abortController.signal,
        });

        const ttsResult = await ttsResponse.json();
        if (!ttsResponse.ok || !ttsResult.success) {
          throw new Error(ttsResult.error || '音声の生成に失敗しました');
        }

        if (typeof ttsResult.audioResponse === 'string' && ttsResult.audioResponse.length > 0) {
          await playAssistantAudio(ttsResult.audioResponse);
        } else {
          voiceController.notifySpeaking();
          window.setTimeout(() => {
            voiceController.notifySpeakingComplete();
          }, 240);
        }
      } catch (sendError) {
        if (sendError instanceof DOMException && sendError.name === 'AbortError') {
          return;
        }

        setError(formatError(sendError, currentLanguage));
        voiceController.notifySpeakingComplete();
      } finally {
        if (requestAbortRef.current === abortController) {
          requestAbortRef.current = null;
        }
        setIsLoading(false);
        setLoadingMessage('');
      }
    },
    [cancelPendingRequest, currentLanguage, playAssistantAudio, stopPlayback, voiceController],
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
          throw new Error(sttResult.error || '音声認識に失敗しました');
        }

        setTranscript(sttResult.transcript);
        setIsLoading(false);
        setLoadingMessage('');
        await sendMessage(sttResult.transcript);
      } catch (recordingError) {
        if (recordingError instanceof DOMException && recordingError.name === 'AbortError') {
          return;
        }

        setError(formatError(recordingError, currentLanguage));
        voiceController.notifySpeakingComplete();
      } finally {
        if (requestAbortRef.current === abortController) {
          requestAbortRef.current = null;
        }
        setIsLoading(false);
        setLoadingMessage('');
      }
    },
    [cancelPendingRequest, currentLanguage, sendMessage, voiceController],
  );

  const ensureRecorder = useCallback(async () => {
    const existingRecorder = recorderRef.current;
    if (existingRecorder?.isInitialized()) {
      return existingRecorder;
    }

    const recorder = new VoiceRecorder(
      (audioBlob) => {
        void handleRecordedAudio(audioBlob);
      },
      (recorderError) => {
        setError(formatError(recorderError, currentLanguage));
        setIsLoading(false);
        setLoadingMessage('');
        isRecordingRef.current = false;
      },
    );

    setIsLoading(true);
    setLoadingMessage(LOADING_LABELS[currentLanguage].microphone);
    await recorder.initialize();

    if (!recorder.isInitialized()) {
      setIsLoading(false);
      setLoadingMessage('');
      throw new Error(currentLanguage === 'ja' ? 'マイクを初期化できませんでした' : 'Unable to initialize the microphone');
    }

    recorderRef.current = recorder;
    setMediaStream(recorder.getStream());
    setIsLoading(false);
    setLoadingMessage('');

    return recorder;
  }, [currentLanguage, handleRecordedAudio]);

  const startRecorderCapture = useCallback(async () => {
    if (isRecordingRef.current) {
      return;
    }

    try {
      const recorder = await ensureRecorder();
      if (recorder.getState() === 'recording') {
        return;
      }

      recorder.start();
      isRecordingRef.current = true;
      shouldDiscardNextAudioRef.current = false;
    } catch (startError) {
      setError(formatError(startError, currentLanguage));
      voiceController.endManualSession();
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

    if (!isRecordingRef.current) {
      return;
    }

    stopRecorderCapture(sessionState === 'idle');
  }, [sessionState, startRecorderCapture, stopRecorderCapture, voiceController.shouldListen]);

  const startListening = useCallback(() => {
    cancelPendingRequest();
    stopPlayback(false);
    setError(null);
    voiceController.startManualSession();
  }, [cancelPendingRequest, stopPlayback, voiceController]);

  const stopListening = useCallback(() => {
    if (sessionState !== 'listening') {
      return;
    }

    voiceController.notifyProcessing();
  }, [sessionState, voiceController]);

  const cancelSession = useCallback(() => {
    cancelPendingRequest();
    stopPlayback(false);
    shouldDiscardNextAudioRef.current = true;
    stopRecorderCapture(true);
    setIsLoading(false);
    setLoadingMessage('');
    voiceController.endManualSession();
  }, [cancelPendingRequest, stopPlayback, stopRecorderCapture, voiceController]);

  const clearConversation = useCallback(() => {
    cancelSession();
    resetConversation();
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

  useEffect(() => {
    return () => {
      cancelPendingRequest();
      cleanupAudioPlayback();
      recorderRef.current?.cleanup();
      lipSyncAnalyzerRef.current?.dispose();
      mobileAudioServiceRef.current?.dispose();
    };
  }, [cancelPendingRequest, cleanupAudioPlayback]);

  const renderProps = useMemo<VoiceInterfaceRenderProps>(
    () => ({
      sessionState,
      characterState: voiceController.characterState,
      transcript,
      response,
      metadata,
      error,
      isLoading,
      loadingMessage,
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
      sendMessage,
      setVolume,
      setMuted,
      toggleLanguage,
    }),
    [
      cancelSession,
      clearConversation,
      currentLanguage,
      error,
      isLoading,
      isMuted,
      loadingMessage,
      metadata,
      response,
      sendMessage,
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
