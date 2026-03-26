'use client';

import { markAudioUserInteraction } from '@/lib/audio/audio-user-interaction-gate';
import {
  KIOSK_IDLE_MS,
  type KioskMicMode,
  type KioskPhase,
  readKioskMicMode,
  readKioskTriggerMode,
} from '@/lib/kiosk-constants';
import ReactMarkdown from 'react-markdown';

import { cn } from '@/lib/cn';
import {
  Camera,
  Loader2,
  MessageSquare,
  Mic,
  MicOff,
  Presentation,
  SendHorizontal,
  Settings,
  Sparkles,
  Volume2,
  X,
  XCircle,
} from 'lucide-react';
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type Dispatch,
  type MutableRefObject,
  type PointerEvent as ReactPointerEvent,
  type SetStateAction,
} from 'react';
import type { CharacterAnimationData } from './utils/character-animation-utils';
import type { BackgroundOption } from './components/BackgroundSelector';
import CharacterAvatar from './components/CharacterAvatar';
import SettingsPanel, {
  type SettingsPanelPropsFromSource,
} from './components/SettingsPanel';
import MarpViewer from './components/MarpViewer';
import InitialSettingsModal from './components/InitialSettingsModal';
import VoiceInterface, {
  type VoiceInterfaceMetadata,
  type VoiceSessionState,
} from './components/VoiceInterface';
import { OcrCameraView } from '@/components/reception/OcrCameraView';
import { ReceptionPanel } from '@/components/reception/ReceptionPanel';

const overlayLabels = {
  ja: {
    guideLabel: '音声ガイド',
    responseLabel: '応答',
    transcriptLabel: '聞き取り結果',
    loadingLabel: '応答を準備しています',
    wakeWordReady: 'ウェイクワード待機中',
    wakeWordOff: 'マイクボタンで開始',
    idleAction: '話しかける',
    listeningAction: '録音を止める',
    processingAction: '処理中',
    speakingAction: '応答を再生中',
    defaultPrompt: 'マイクを押して、エンジニアカフェについて聞いてください。',
    helperPrompt: '音声が中心です。必要なときだけテキスト入力を開けます。',
    switchTextInput: '文字入力',
    switchVoiceInput: '音声入力',
    textPlaceholder: 'ここに質問を入力します',
    send: '送信',
    openSlides: 'スライド案内',
    closeSlides: 'スライドを閉じる',
    clearConversation: '会話をクリア',
    cancelSession: '応答を止める',
    languageJa: '日本語',
    languageEn: 'English',
    currentLocale: '現在: 日本語',
    kioskWelcome: '受付（Welcome）',
    kioskVoice: '音声応対',
    kioskOcr: '会員証・筆談（OCR）',
    kioskSlides: 'スライド案内',
    kioskBackIdle: 'メニューに戻る',
    ocrModeMember: '会員証',
    ocrModeHandwriting: '筆談',
  },
  en: {
    guideLabel: 'Voice Guide',
    responseLabel: 'Answer',
    transcriptLabel: 'Transcript',
    loadingLabel: 'Preparing an answer',
    wakeWordReady: 'Wake word is armed',
    wakeWordOff: 'Use the mic button to start',
    idleAction: 'Start talking',
    listeningAction: 'Stop recording',
    processingAction: 'Processing',
    speakingAction: 'Speaking',
    defaultPrompt: 'Tap the mic and ask anything about Engineer Cafe.',
    helperPrompt: 'Voice comes first. Open text input only when you need a backup.',
    switchTextInput: 'Text input',
    switchVoiceInput: 'Voice input',
    textPlaceholder: 'Type your question here',
    send: 'Send',
    openSlides: 'Open slides',
    closeSlides: 'Close slides',
    clearConversation: 'Clear conversation',
    cancelSession: 'Cancel current turn',
    languageJa: '日本語',
    languageEn: 'English',
    currentLocale: 'Current: English',
    kioskWelcome: 'Reception (Welcome)',
    kioskVoice: 'Voice chat',
    kioskOcr: 'Member card & OCR',
    kioskSlides: 'Slide guide',
    kioskBackIdle: 'Back to menu',
    ocrModeMember: 'Member card',
    ocrModeHandwriting: 'Handwriting',
  },
} as const;

const buttonCopy: Record<
  VoiceSessionState,
  'idleAction' | 'listeningAction' | 'processingAction' | 'speakingAction'
> = {
  idle: 'idleAction',
  listening: 'listeningAction',
  processing: 'processingAction',
  speaking: 'speakingAction',
};

type ConversationHistoryItem = {
  id: string;
  role: 'user' | 'assistant';
  text: string;
};

function ConversationHistoryEffects({
  transcript,
  response,
  lastTranscriptRef,
  lastResponseRef,
  setConversationHistory,
}: {
  transcript: string;
  response: string;
  lastTranscriptRef: MutableRefObject<string>;
  lastResponseRef: MutableRefObject<string>;
  setConversationHistory: Dispatch<SetStateAction<ConversationHistoryItem[]>>;
}) {
  useEffect(() => {
    if (transcript && transcript !== lastTranscriptRef.current) {
      lastTranscriptRef.current = transcript;
      setConversationHistory((prev) => [
        ...prev,
        {
          id: `u-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          role: 'user',
          text: transcript,
        },
      ]);
    }
  }, [lastTranscriptRef, setConversationHistory, transcript]);

  useEffect(() => {
    if (response && response !== lastResponseRef.current) {
      lastResponseRef.current = response;
      setConversationHistory((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          role: 'assistant',
          text: response,
        },
      ]);
    }
  }, [lastResponseRef, response, setConversationHistory]);

  return null;
}

const getStageBackgroundStyle = (background: BackgroundOption): CSSProperties => {
  if (background.type === 'image') {
    return {
      backgroundImage: `url(${background.value})`,
      backgroundPosition: 'center',
      backgroundRepeat: 'no-repeat',
      backgroundSize: 'cover',
    };
  }

  if (background.type === 'gradient') {
    return { background: background.value };
  }

  return background.value ? { backgroundColor: background.value } : {};
};

export default function Home() {
  const [kioskPhase, setKioskPhase] = useState<KioskPhase>('notice');
  const kioskPhaseRef = useRef<KioskPhase>('notice');
  const [currentLanguage, setCurrentLanguage] = useState<'ja' | 'en'>('ja');
  const [micInputMode, setMicInputMode] = useState<KioskMicMode>(() => readKioskMicMode());
  const [ocrMode, setOcrMode] = useState<'member_card' | 'handwriting'>('member_card');
  const [characterBackground, setCharacterBackground] = useState<BackgroundOption>({
    id: 'engineer-cafe-bg',
    name: 'Engineer Cafe',
    type: 'image',
    value: '/backgrounds/IMG_5573.JPG',
  });
  const [lightingIntensity, setLightingIntensity] = useState(1);
  const [setVisemeFunction, setSetVisemeFunction] = useState<((viseme: string, intensity: number) => void) | null>(null);
  const [setExpressionFunction, setSetExpressionFunction] = useState<((expression: string, weight: number) => void) | null>(null);
  const [textDraft, setTextDraft] = useState('');
  const [showTextInput, setShowTextInput] = useState(false);
  const [, setLatestMetadata] = useState<VoiceInterfaceMetadata | null>(null);
  const [conversationHistory, setConversationHistory] = useState<ConversationHistoryItem[]>([]);
  const [showSettingsPanel, setShowSettingsPanel] = useState(false);
  const settingsPanelPropsRef = useRef<SettingsPanelPropsFromSource | null>(null);
  const [settingsPanelProps, setSettingsPanelProps] =
    useState<SettingsPanelPropsFromSource | null>(null);
  const playKeyframeAnimationRef = useRef<((data: CharacterAnimationData) => void) | null>(null);
  const lastVrmControlPlayedRef = useRef<unknown>(null);
  /** Set when vrm_control playback runs before keyframe control ref is ready; flushed in onKeyframeAnimationControl. */
  const pendingVrmPlaybackRef = useRef<CharacterAnimationData | null>(null);
  const lastTranscriptRef = useRef<string>('');
  const lastResponseRef = useRef<string>('');
  const returnToIdleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const kioskVoiceCleanupRef = useRef<(() => void) | null>(null);

  const showAvatarControls = process.env.NEXT_PUBLIC_SHOW_AVATAR_SETTINGS === 'true';

  useEffect(() => {
    kioskPhaseRef.current = kioskPhase;
  }, [kioskPhase]);

  const clearReturnToIdleTimer = useCallback(() => {
    if (returnToIdleTimerRef.current !== null) {
      clearTimeout(returnToIdleTimerRef.current);
      returnToIdleTimerRef.current = null;
    }
  }, []);

  const scheduleReturnToIdle = useCallback(() => {
    clearReturnToIdleTimer();
    returnToIdleTimerRef.current = setTimeout(() => {
      returnToIdleTimerRef.current = null;
      const phase = kioskPhaseRef.current;
      if (phase === 'voice' || phase === 'welcome') {
        kioskVoiceCleanupRef.current?.();
      }
      setKioskPhase('idle');
    }, KIOSK_IDLE_MS);
  }, [clearReturnToIdleTimer]);

  const bumpUserActivity = useCallback(() => {
    if (kioskPhaseRef.current === 'notice' || kioskPhaseRef.current === 'idle') {
      return;
    }
    clearReturnToIdleTimer();
  }, [clearReturnToIdleTimer]);

  useEffect(() => {
    return () => {
      clearReturnToIdleTimer();
    };
  }, [clearReturnToIdleTimer]);

  useEffect(() => {
    if (kioskPhase === 'ocr') {
      scheduleReturnToIdle();
    }
  }, [kioskPhase, scheduleReturnToIdle]);

  const handleSettingsPanelPropsChange = useCallback(
    (props: SettingsPanelPropsFromSource) => {
      settingsPanelPropsRef.current = props;
      // Avoid re-rendering the whole page when settings panel is closed.
      if (showSettingsPanel) {
        setSettingsPanelProps(props);
      }
    },
    [showSettingsPanel],
  );

  useEffect(() => {
    if (showSettingsPanel) {
      setSettingsPanelProps(settingsPanelPropsRef.current);
    } else {
      setSettingsPanelProps(null);
    }
  }, [showSettingsPanel]);

  const startPresentation = useCallback((language: 'ja' | 'en') => {
    setCurrentLanguage(language);
    setKioskPhase('slides');

    window.setTimeout(() => {
      window.dispatchEvent(
        new CustomEvent('autoStartPresentation', {
          detail: { autoPlay: true, language },
        }),
      );
    }, 150);
  }, []);

  const handleCloseSlides = useCallback(() => {
    clearReturnToIdleTimer();
    setKioskPhase('idle');
  }, [clearReturnToIdleTimer]);

  return (
    <>
      <InitialSettingsModal
        language={currentLanguage}
        open={kioskPhase === 'notice'}
        onClose={() => setKioskPhase('idle')}
        onPreferencesSaved={(prefs) => {
          setCurrentLanguage(prefs.language);
          setMicInputMode(prefs.micMode);
        }}
      />
      <VoiceInterface
      language={currentLanguage}
      onLanguageChange={setCurrentLanguage}
      onVisemeControl={setVisemeFunction}
      showDefaultUI={false}
      onMetadataChange={setLatestMetadata}
      onAssistantPlaybackEnd={() => {
        if (kioskPhaseRef.current === 'voice') {
          scheduleReturnToIdle();
        }
      }}
      onAssistantPlaybackStart={({ metadata: playbackMetadata }) => {
        const vc = playbackMetadata?.vrm_control;
        if (!vc) {
          return;
        }
        if (playKeyframeAnimationRef.current) {
          if (lastVrmControlPlayedRef.current !== vc) {
            lastVrmControlPlayedRef.current = vc;
            playKeyframeAnimationRef.current(vc);
          }
          pendingVrmPlaybackRef.current = null;
        } else {
          pendingVrmPlaybackRef.current = vc;
        }
      }}
    >
      {(voice) => {
        kioskVoiceCleanupRef.current = () => {
          voice.cancelSession();
          voice.clearConversation();
        };
        const labels = overlayLabels[voice.currentLanguage];
        const receptionTriggerType =
          readKioskTriggerMode() === 'device' ? 'sensor_trigger' : 'button_press';
        const showSlideMode = kioskPhase === 'slides';
        const stageBackgroundStyle = getStageBackgroundStyle(characterBackground);
        const isListening = voice.sessionState === 'listening';
        const isSpeaking = voice.sessionState === 'speaking';
        const visualState: VoiceSessionState =
          voice.sessionState === 'speaking'
            ? 'speaking'
            : voice.sessionState === 'listening'
              ? 'listening'
              : voice.sessionState === 'processing' || voice.isLoading
                ? 'processing'
                : 'idle';
        const isProcessing = visualState === 'processing';
        const showConversationReset =
          Boolean(voice.transcript) || Boolean(voice.response) || Boolean(voice.metadata);
        const canCancelTurn = voice.sessionState !== 'idle' || voice.isLoading;
        const waveformBars = (
          isListening || isSpeaking ? voice.waveformBars : [0.2, 0.28, 0.18, 0.26, 0.2]
        ).map((value) => Math.max(value, 0.16));
        const bubbleBody =
          voice.response || (voice.isLoading && voice.loadingMessage) || labels.defaultPrompt;
        const micButtonLabel = labels[buttonCopy[visualState]];
        const isInputDisabled = isListening || isProcessing;

        const screenPadding = {
          paddingTop: 'max(1.5rem, env(safe-area-inset-top))',
          paddingBottom: 'max(1.5rem, env(safe-area-inset-bottom))',
          paddingLeft: 'max(1.5rem, env(safe-area-inset-left))',
          paddingRight: 'max(1.5rem, env(safe-area-inset-right))',
        } satisfies CSSProperties;

        const characterCameraOffset = showSlideMode
          ? { x: 0.2, y: 0, z: 0.0 }
          : { x: 0, y: 0, z: 0 };
        const characterModelOffset = showSlideMode
          ? { x: -0.7, y: 0, z: 0 }
          : { x: 0, y: 0, z: 0 };
        const characterRotationOffset = showSlideMode
          ? { x: 0, y: 0.35, z: 0 }
          : { x: 0, y: -0.2, z: 0 };

        const submitTextDraft = async () => {
          markAudioUserInteraction();
          const trimmed = textDraft.trim();
          if (!trimmed) {
            return;
          }

          await voice.sendMessage(trimmed);
          setTextDraft('');
        };

        const pushToTalk = micInputMode === 'push_to_talk';

        const handleMicPointerDown = (e: ReactPointerEvent<HTMLButtonElement>) => {
          if (!pushToTalk || isProcessing || isSpeaking) {
            return;
          }
          e.preventDefault();
          e.currentTarget.setPointerCapture(e.pointerId);
          markAudioUserInteraction();
          if (!isListening) {
            void voice.startListening();
          }
        };

        const handleMicPointerUp = (e: ReactPointerEvent<HTMLButtonElement>) => {
          if (!pushToTalk) {
            return;
          }
          e.preventDefault();
          if (e.currentTarget.hasPointerCapture(e.pointerId)) {
            e.currentTarget.releasePointerCapture(e.pointerId);
          }
          if (isListening) {
            voice.stopListening();
          }
        };

        const handleMicPointerCancel = (e: ReactPointerEvent<HTMLButtonElement>) => {
          if (!pushToTalk) {
            return;
          }
          if (e.currentTarget.hasPointerCapture(e.pointerId)) {
            e.currentTarget.releasePointerCapture(e.pointerId);
          }
          if (isListening) {
            voice.stopListening();
          }
        };

        return (
          <>
            <ConversationHistoryEffects
              transcript={voice.transcript}
              response={voice.response}
              lastTranscriptRef={lastTranscriptRef}
              lastResponseRef={lastResponseRef}
              setConversationHistory={setConversationHistory}
            />
            <main className="relative h-[100svh] w-screen overflow-hidden">
              <div className="absolute inset-0 -z-10" style={stageBackgroundStyle}>
                <CharacterAvatar
                  modelPath="/characters/models/sakura.vrm"
                  sessionState={voice.sessionState}
                  background={characterBackground}
                  lightingIntensity={lightingIntensity}
                  cameraPositionOffset={characterCameraOffset}
                  modelPositionOffset={characterModelOffset}
                  modelRotationOffset={characterRotationOffset}
                  enableClickAnimation={!showSlideMode}
                  showControls={showAvatarControls && !showSlideMode && kioskPhase === 'voice'}
                  volume={Math.round(voice.volume * 100)}
                  isMuted={voice.isMuted}
                  onVolumeChange={(value) => voice.setVolume(value / 100)}
                  onMuteToggle={() => voice.setMuted(!voice.isMuted)}
                  onVisemeControl={(setViseme) => {
                    setSetVisemeFunction(() => setViseme);
                  }}
                  onExpressionControl={(setExpression) => {
                    setSetExpressionFunction(() => setExpression);
                  }}
                  onKeyframeAnimationControl={(play) => {
                    playKeyframeAnimationRef.current = play;
                    const pending = pendingVrmPlaybackRef.current;
                    if (pending && lastVrmControlPlayedRef.current !== pending) {
                      lastVrmControlPlayedRef.current = pending;
                      play(pending);
                      pendingVrmPlaybackRef.current = null;
                    }
                  }}
                  onBackgroundChange={setCharacterBackground}
                  onLightingChange={setLightingIntensity}
                  settingsPanelPropsRef={settingsPanelPropsRef}
                  onSettingsPanelPropsChange={handleSettingsPanelPropsChange}
                />
              </div>

              {kioskPhase === 'idle' && (
                <div
                  className="pointer-events-auto absolute inset-x-0 bottom-0 z-[25] flex justify-center pb-[max(0.75rem,env(safe-area-inset-bottom))] pl-[max(1rem,env(safe-area-inset-left))] pr-[max(1rem,env(safe-area-inset-right))] pt-2"
                >
                  <div className="flex w-full max-w-5xl flex-row flex-wrap items-stretch justify-center gap-2 sm:gap-3">
                    <button
                      type="button"
                      onClick={() => {
                        markAudioUserInteraction();
                        setKioskPhase('welcome');
                      }}
                      className="flex min-h-[72px] min-w-[min(100%,7rem)] flex-1 flex-col items-center justify-center gap-1 rounded-2xl border border-white/35 bg-white/15 px-3 py-3 text-white shadow-md backdrop-blur-sm transition-transform hover:scale-[1.02] sm:min-h-[80px] sm:flex-initial sm:px-5"
                    >
                      <Sparkles className="size-6 shrink-0 sm:size-7" aria-hidden />
                      <span className="text-center text-xs font-semibold leading-tight sm:text-sm">
                        {labels.kioskWelcome}
                      </span>
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        markAudioUserInteraction();
                        setKioskPhase('voice');
                      }}
                      className="flex min-h-[72px] min-w-[min(100%,7rem)] flex-1 flex-col items-center justify-center gap-1 rounded-2xl border border-white/35 bg-white/15 px-3 py-3 text-white shadow-md backdrop-blur-sm transition-transform hover:scale-[1.02] sm:min-h-[80px] sm:flex-initial sm:px-5"
                    >
                      <Mic className="size-6 shrink-0 sm:size-7" aria-hidden />
                      <span className="text-center text-xs font-semibold leading-tight sm:text-sm">
                        {labels.kioskVoice}
                      </span>
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        markAudioUserInteraction();
                        setKioskPhase('ocr');
                      }}
                      className="flex min-h-[72px] min-w-[min(100%,7rem)] flex-1 flex-col items-center justify-center gap-1 rounded-2xl border border-white/35 bg-white/15 px-3 py-3 text-white shadow-md backdrop-blur-sm transition-transform hover:scale-[1.02] sm:min-h-[80px] sm:flex-initial sm:px-5"
                    >
                      <Camera className="size-6 shrink-0 sm:size-7" aria-hidden />
                      <span className="text-center text-xs font-semibold leading-tight sm:text-sm">
                        {labels.kioskOcr}
                      </span>
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        markAudioUserInteraction();
                        startPresentation(voice.currentLanguage);
                      }}
                      className="flex min-h-[72px] min-w-[min(100%,7rem)] flex-1 flex-col items-center justify-center gap-1 rounded-2xl border border-white/35 bg-white/15 px-3 py-3 text-white shadow-md backdrop-blur-sm transition-transform hover:scale-[1.02] sm:min-h-[80px] sm:flex-initial sm:px-5"
                    >
                      <Presentation className="size-6 shrink-0 sm:size-7" aria-hidden />
                      <span className="text-center text-xs font-semibold leading-tight sm:text-sm">
                        {labels.kioskSlides}
                      </span>
                    </button>
                  </div>
                </div>
              )}

              {kioskPhase === 'voice' && (
                <>
                  <div
                    className="pointer-events-none absolute inset-0 z-20"
                    style={screenPadding}
                    onPointerDownCapture={bumpUserActivity}
                  >
                    <div
                      className={
                        showTextInput
                          ? 'pointer-events-auto grid h-full w-full grid-cols-[1fr_1fr] grid-rows-[3fr_1fr] gap-4'
                          : 'pointer-events-auto grid h-full w-full grid-cols-[3fr_1fr] grid-rows-[3fr_1fr] gap-4'
                      }
                    >
                    <div className="row-start-2 col-start-1 h-full">
                      <div
                        className="h-full rounded-[28px] bg-black/55 p-4 text-white shadow-xl backdrop-blur-md"
                        data-testid="response-bubble"
                      >
                        <div className="h-full overflow-y-auto pr-1">
                          <div
                            className="text-base leading-7 text-pretty text-white/90 md:text-lg md:leading-8"
                            data-testid="response-text"
                          >
                            <ReactMarkdown
                              components={{
                                p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                                strong: ({ children }) => <strong className="font-bold text-white">{children}</strong>,
                                ul: ({ children }) => <ul className="mb-2 ml-4 list-disc">{children}</ul>,
                                ol: ({ children }) => <ol className="mb-2 ml-4 list-decimal">{children}</ol>,
                                li: ({ children }) => <li className="mb-1">{children}</li>,
                                h1: ({ children }) => <h2 className="mb-2 text-lg font-bold text-white">{children}</h2>,
                                h2: ({ children }) => <h3 className="mb-2 text-base font-bold text-white">{children}</h3>,
                                h3: ({ children }) => <h4 className="mb-1 text-sm font-bold text-white">{children}</h4>,
                                code: ({ children }) => (
                                  <code className="rounded bg-white/10 px-1 py-0.5 text-sm">{children}</code>
                                ),
                                pre: ({ children }) => (
                                  <pre className="mb-2 overflow-x-auto rounded bg-white/10 p-2 text-sm">{children}</pre>
                                ),
                                blockquote: ({ children }) => (
                                  <blockquote className="mb-2 border-l-4 border-white/30 pl-4 italic text-white/70">{children}</blockquote>
                                ),
                                a: ({ href, children }) => (
                                  <a href={href} className="text-blue-300 underline" target="_blank" rel="noopener noreferrer">{children}</a>
                                ),
                              }}
                            >
                              {voice.response || bubbleBody}
                            </ReactMarkdown>
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="row-start-1 col-start-2 flex h-full flex-col items-end justify-start gap-2">
                      {voice.error ? (
                        <div className="w-full rounded-2xl border border-rose-400/30 bg-rose-500/20 px-3 py-2 text-xs text-white shadow-lg">
                          {voice.error}
                        </div>
                      ) : null}
                      <button
                        type="button"
                        onClick={() => setShowSettingsPanel(true)}
                        aria-label={voice.currentLanguage === 'ja' ? '設定' : 'Settings'}
                        className="inline-flex size-11 shrink-0 items-center justify-center rounded-full border border-white/15 bg-black/45 text-white shadow-lg backdrop-blur-md transition-transform duration-200 ease-out hover:scale-105"
                      >
                        <Settings className="size-5" />
                      </button>
                    </div>

                    <div className="row-start-2 col-start-2 h-full">
                      <div className="flex h-full flex-col rounded-[32px] border border-white/15 bg-black/35 px-4 py-3 text-white shadow-xl backdrop-blur-md md:px-5">
                        <div className="flex items-center justify-between gap-3">
                          <p className="text-sm font-medium text-white/70">
                            {visualState === 'idle' ? ' ' : labels[buttonCopy[visualState]]}
                          </p>
                          {canCancelTurn || showConversationReset ? (
                            <button
                              type="button"
                              onClick={canCancelTurn ? voice.cancelSession : voice.clearConversation}
                              aria-label={canCancelTurn ? labels.cancelSession : labels.clearConversation}
                              className="inline-flex size-9 items-center justify-center rounded-full bg-white/10 text-white transition-transform duration-200 ease-out hover:scale-105"
                            >
                              {canCancelTurn ? <XCircle className="size-4" /> : <X className="size-4" />}
                            </button>
                          ) : (
                            <div className="size-9" aria-hidden="true" />
                          )}
                        </div>

                        <div className="mt-3 flex min-h-0 flex-1 items-stretch gap-3">
                          <div className="flex min-h-0 min-w-0 flex-[2] flex-col">
                            {showTextInput ? (
                              <div className="flex min-h-0 flex-1 flex-col">
                                <label className="sr-only" htmlFor="voice-text-draft">
                                  {labels.textPlaceholder}
                                </label>
                                <textarea
                                  id="voice-text-draft"
                                  value={textDraft}
                                  onChange={(event) => setTextDraft(event.target.value)}
                                  placeholder={labels.textPlaceholder}
                                  aria-label={labels.textPlaceholder}
                                  className="min-h-20 flex-1 resize-none overflow-auto rounded-2xl border border-white/15 bg-black/20 px-4 py-2 text-sm text-white placeholder:text-white/45 focus:outline-none focus:ring-2 focus:ring-white/30"
                                />
                                <div className="mt-2 flex shrink-0 justify-end">
                                  <button
                                    type="button"
                                    onClick={() => void submitTextDraft()}
                                    disabled={!textDraft.trim() || isInputDisabled}
                                    aria-label={labels.send}
                                    className={cn(
                                      'inline-flex size-10 items-center justify-center rounded-full shadow-lg transition-transform duration-200 ease-out disabled:cursor-not-allowed',
                                      !textDraft.trim() || isInputDisabled
                                        ? 'bg-black/40 text-white/70 hover:scale-100'
                                        : 'bg-white/90 text-slate-900 hover:scale-105',
                                    )}
                                  >
                                    <SendHorizontal className="size-5" />
                                  </button>
                                </div>
                              </div>
                            ) : (
                              <div className="flex h-full items-center justify-center">
                                <button
                                  type="button"
                                  onPointerDown={handleMicPointerDown}
                                  onPointerUp={handleMicPointerUp}
                                  onPointerCancel={handleMicPointerCancel}
                                  onClick={(e) => {
                                    if (pushToTalk) {
                                      e.preventDefault();
                                      return;
                                    }
                                    markAudioUserInteraction();
                                    if (isListening) {
                                      voice.stopListening();
                                    } else {
                                      void voice.startListening();
                                    }
                                  }}
                                  disabled={isProcessing}
                                  aria-label={micButtonLabel}
                                  aria-pressed={pushToTalk ? isListening : undefined}
                                  className={cn(
                                    'inline-flex size-16 items-center justify-center rounded-full shadow-xl transition-transform duration-200 ease-out md:size-20',
                                    'hover:scale-105 disabled:cursor-not-allowed disabled:hover:scale-100',
                                    pushToTalk && 'touch-none select-none',
                                    visualState === 'idle' && 'bg-white text-slate-900',
                                    visualState === 'listening' && 'bg-rose-500 text-white motion-safe:animate-pulse',
                                    visualState === 'processing' && 'bg-amber-500 text-white',
                                    visualState === 'speaking' && 'bg-sky-500 text-white',
                                  )}
                                >
                                  {visualState === 'processing' ? (
                                    <Loader2 className="size-7 animate-spin md:size-8" />
                                  ) : visualState === 'listening' ? (
                                    <MicOff className="size-7 md:size-8" />
                                  ) : visualState === 'speaking' ? (
                                    <Volume2 className="size-7 md:size-8" />
                                  ) : (
                                    <Mic className="size-7 md:size-8" />
                                  )}
                                </button>
                              </div>
                            )}
                          </div>

                          <div className="flex w-[150px] shrink-0 flex-col justify-between">
                            <div className="flex flex-col items-center justify-start gap-2">
                              <button
                                type="button"
                                onClick={() => setCurrentLanguage('ja')}
                                className={cn(
                                  'rounded-full px-3 py-1 text-xs font-medium text-xl transition-colors',
                                  voice.currentLanguage === 'ja'
                                    ? 'bg-white/90 text-slate-900'
                                    : 'bg-white/20 text-white/70',
                                )}
                              >
                                {labels.languageJa}
                              </button>
                              <button
                                type="button"
                                onClick={() => setCurrentLanguage('en')}
                                className={cn(
                                  'rounded-full px-3 py-1 text-xs font-medium text-xl transition-colors',
                                  voice.currentLanguage === 'en'
                                    ? 'bg-white/90 text-slate-900'
                                    : 'bg-white/20 text-white/70',
                                )}
                              >
                                {labels.languageEn}
                              </button>
                            </div>

                            <div className="flex items-center justify-end">
                              <button
                                type="button"
                                onClick={() => setShowTextInput((current) => !current)}
                                aria-label={
                                  showTextInput ? labels.switchVoiceInput : labels.switchTextInput
                                }
                                aria-pressed={showTextInput}
                                data-testid="text-input-toggle"
                                className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1.5 text-xs font-medium text-white transition-transform duration-200 ease-out hover:scale-105"
                              >
                                {showTextInput ? (
                                  <Mic className="size-6" />
                                ) : (
                                  <MessageSquare className="size-6" />
                                )}
                              </button>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {showSettingsPanel && settingsPanelProps ? (
                  <div
                    className="absolute inset-0 z-30 pointer-events-none"
                    aria-hidden={!showSettingsPanel}
                  >
                    <div
                      className="pointer-events-auto absolute top-0 flex max-h-full justify-end"
                      style={{
                        top: screenPadding.paddingTop,
                        right: screenPadding.paddingRight,
                      }}
                    >
                      <SettingsPanel
                        {...settingsPanelProps}
                        show_close_button
                        on_close={() => setShowSettingsPanel(false)}
                        extra_tab={{
                          label: voice.currentLanguage === 'ja' ? '会話履歴' : 'Conversation',
                          content: (
                            <div className="space-y-2 overflow-y-auto pr-1">
                              {conversationHistory.length === 0 ? (
                                <p className="text-sm text-gray-600">{labels.helperPrompt}</p>
                              ) : (
                                conversationHistory.map((item) => (
                                  <div
                                    key={item.id}
                                    className={cn(
                                      'rounded-2xl px-3 py-2 text-sm leading-6',
                                      item.role === 'user'
                                        ? 'bg-gray-100 text-gray-800'
                                        : 'bg-blue-50 text-gray-800',
                                    )}
                                  >
                                    <p className="text-xs font-medium text-gray-500">
                                      {item.role === 'user'
                                        ? voice.currentLanguage === 'ja'
                                          ? 'あなた'
                                          : 'You'
                                        : 'Navigator'}
                                    </p>
                                    <p className="mt-1 whitespace-pre-wrap">{item.text}</p>
                                  </div>
                                ))
                              )}
                            </div>
                          ),
                        }}
                        slide_mode_open={showSlideMode}
                        on_open_slides={() => startPresentation(voice.currentLanguage)}
                        on_close_slides={handleCloseSlides}
                        open_slides_label={labels.openSlides}
                        close_slides_label={labels.closeSlides}
                      />
                    </div>
                  </div>
                ) : null}
                </>
              )}

              {kioskPhase === 'welcome' && (
                <div
                  className="absolute inset-0 z-40 overflow-y-auto bg-black/55 p-4"
                  onPointerDownCapture={bumpUserActivity}
                >
                  <div className="mx-auto max-w-3xl pb-24 pt-8">
                    <ReceptionPanel
                      sessionId={voice.sessionId}
                      language={voice.currentLanguage}
                      triggerType={receptionTriggerType}
                      autoEnterWelcome
                      onAssistantMessageAdded={() => {
                        if (kioskPhaseRef.current === 'welcome') {
                          scheduleReturnToIdle();
                        }
                      }}
                      onReceptionComplete={() => {
                        clearReturnToIdleTimer();
                        setKioskPhase('voice');
                      }}
                      className="border-white/20 bg-white/95 shadow-xl"
                    />
                    <div className="mt-6 flex justify-center">
                      <button
                        type="button"
                        onClick={() => {
                          clearReturnToIdleTimer();
                          setKioskPhase('idle');
                        }}
                        className="inline-flex min-h-11 items-center justify-center rounded-full border border-white/30 bg-black/40 px-6 py-3 text-sm font-medium text-white backdrop-blur-md transition-colors hover:bg-black/55"
                      >
                        {labels.kioskBackIdle}
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {kioskPhase === 'ocr' && (
                <div
                  className="absolute inset-0 z-40 overflow-y-auto bg-black/60 p-4"
                  onPointerDownCapture={bumpUserActivity}
                >
                  <div className="mx-auto max-w-lg rounded-[28px] border border-white/15 bg-white/95 p-5 shadow-xl md:p-8">
                    <div className="mb-4 flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => setOcrMode('member_card')}
                        className={cn(
                          'rounded-full px-4 py-2 text-sm font-medium transition-colors',
                          ocrMode === 'member_card'
                            ? 'bg-slate-900 text-white'
                            : 'bg-slate-100 text-slate-700',
                        )}
                      >
                        {labels.ocrModeMember}
                      </button>
                      <button
                        type="button"
                        onClick={() => setOcrMode('handwriting')}
                        className={cn(
                          'rounded-full px-4 py-2 text-sm font-medium transition-colors',
                          ocrMode === 'handwriting'
                            ? 'bg-slate-900 text-white'
                            : 'bg-slate-100 text-slate-700',
                        )}
                      >
                        {labels.ocrModeHandwriting}
                      </button>
                    </div>
                    <OcrCameraView
                      key={ocrMode}
                      mode={ocrMode}
                      sessionId={voice.sessionId}
                      onSuccess={() => {
                        clearReturnToIdleTimer();
                        setKioskPhase('idle');
                      }}
                      onFallback={() => {
                        clearReturnToIdleTimer();
                        setKioskPhase('idle');
                      }}
                      onSkip={() => {
                        clearReturnToIdleTimer();
                        setKioskPhase('idle');
                      }}
                    />
                    <div className="mt-6 flex justify-center">
                      <button
                        type="button"
                        onClick={() => {
                          clearReturnToIdleTimer();
                          setKioskPhase('idle');
                        }}
                        className="inline-flex min-h-11 items-center justify-center rounded-full bg-slate-900 px-6 py-3 text-sm font-medium text-white transition-colors hover:bg-slate-800"
                      >
                        {labels.kioskBackIdle}
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {showSlideMode ? (
                <div
                  className="pointer-events-none absolute inset-y-0 right-0 z-30 flex w-full justify-end"
                  style={screenPadding}
                >
                  <div
                    className="pointer-events-auto flex h-full w-full max-w-6xl transform-gpu rounded-[32px] bg-white/95 shadow-2xl transition-all duration-300 ease-out"
                    onPointerDownCapture={bumpUserActivity}
                  >
                    <div className="relative flex h-full w-full flex-col overflow-hidden rounded-[32px]">
                      <button
                        type="button"
                        onClick={handleCloseSlides}
                        aria-label={labels.closeSlides}
                        className="absolute right-4 top-4 z-10 inline-flex size-11 items-center justify-center rounded-full bg-black/70 text-white shadow-lg transition-transform duration-200 ease-out hover:scale-105"
                      >
                        <X className="size-5" />
                      </button>
                      <div className="h-full w-full pt-4">
                        <MarpViewer
                          language={voice.currentLanguage}
                          onVisemeControl={setVisemeFunction}
                          onExpressionControl={setExpressionFunction}
                          volume={Math.round(voice.volume * 100)}
                          onPresentationComplete={() => {
                            if (kioskPhaseRef.current === 'slides') {
                              scheduleReturnToIdle();
                            }
                          }}
                        />
                      </div>
                    </div>
                  </div>
                </div>
              ) : null}


            </main>
          </>
        );
      }}
    </VoiceInterface>
    </>
  );
}
