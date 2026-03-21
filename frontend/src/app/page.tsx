'use client';

import { cn } from '@/lib/cn';
import { ClarificationUtils } from '@/lib/clarification-utils';
import {
  ChevronDown,
  Loader2,
  MessageSquare,
  Mic,
  MicOff,
  SendHorizontal,
  Settings,
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
  type KeyboardEvent,
  type MutableRefObject,
  type SetStateAction,
} from 'react';
import type { CharacterAnimationData } from './utils/character-animation-utils';
import type { BackgroundOption } from './components/BackgroundSelector';
import CharacterAvatar from './components/CharacterAvatar';
import ClarificationButtons from './components/ClarificationButtons';
import SettingsPanel, {
  type SettingsPanelPropsFromSource,
} from './components/SettingsPanel';
import MarpViewer from './components/MarpViewer';
import VoiceInterface, {
  type VoiceInterfaceMetadata,
  type VoiceSessionState,
} from './components/VoiceInterface';

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

const clarificationOptionMap = {
  ja: {
    'cafe-clarification-needed': ['エンジニアカフェ', 'サイノカフェ'],
    'meeting-room-clarification-needed': ['2階の有料会議室', '地下1階の無料ミーティングスペース'],
    'event-clarification-needed': ['イベント情報', 'コミュニティ情報'],
    'space-clarification-needed': ['作業スペース', '会議スペース'],
  },
  en: {
    'cafe-clarification-needed': ['Engineer Cafe', 'Saino Cafe'],
    'meeting-room-clarification-needed': ['Paid meeting room on 2F', 'Free meeting space on B1'],
    'event-clarification-needed': ['Event information', 'Community information'],
    'space-clarification-needed': ['Workspace', 'Meeting space'],
  },
} as const;

const responseClampStyle: CSSProperties = {
  display: '-webkit-box',
  WebkitBoxOrient: 'vertical',
  WebkitLineClamp: 4,
  overflow: 'hidden',
};

const transcriptClampStyle: CSSProperties = {
  display: '-webkit-box',
  WebkitBoxOrient: 'vertical',
  WebkitLineClamp: 2,
  overflow: 'hidden',
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

const getClarificationOptions = (
  currentLanguage: 'ja' | 'en',
  response: string,
  metadata: Record<string, unknown> | null,
): string[] => {
  const metadataOptions = Array.isArray(metadata?.clarification_options)
    ? metadata.clarification_options.filter((value): value is string => typeof value === 'string')
    : [];
  if (metadataOptions.length > 0) {
    return metadataOptions;
  }

  const clarification = metadata?.clarification;
  const clarificationType =
    clarification &&
    typeof clarification === 'object' &&
    typeof (clarification as { clarification_type?: unknown }).clarification_type === 'string'
      ? (clarification as { clarification_type: keyof typeof clarificationOptionMap.ja }).clarification_type
      : null;

  if (clarificationType && clarificationType in clarificationOptionMap[currentLanguage]) {
    return [...clarificationOptionMap[currentLanguage][clarificationType]];
  }

  return ClarificationUtils.extractClarificationOptions(response);
};

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
  const [currentLanguage, setCurrentLanguage] = useState<'ja' | 'en'>('ja');
  const [showSlideMode, setShowSlideMode] = useState(false);
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
  const [latestMetadata, setLatestMetadata] = useState<VoiceInterfaceMetadata | null>(null);
  const [conversationHistory, setConversationHistory] = useState<ConversationHistoryItem[]>([]);
  const [showSettingsPanel, setShowSettingsPanel] = useState(false);
  const settingsPanelPropsRef = useRef<SettingsPanelPropsFromSource | null>(null);
  const playKeyframeAnimationRef = useRef<((data: CharacterAnimationData) => void) | null>(null);
  const lastVrmControlPlayedRef = useRef<unknown>(null);
  const lastTranscriptRef = useRef<string>('');
  const lastResponseRef = useRef<string>('');

  const showAvatarControls = process.env.NEXT_PUBLIC_SHOW_AVATAR_SETTINGS === 'true';

  const startPresentation = useCallback((language: 'ja' | 'en') => {
    setCurrentLanguage(language);
    setShowSlideMode(true);

    window.setTimeout(() => {
      window.dispatchEvent(
        new CustomEvent('autoStartPresentation', {
          detail: { autoPlay: true, language },
        }),
      );
    }, 150);
  }, []);

  useEffect(() => {
    if (!showSlideMode && latestMetadata?.reception_type === 'first_time') {
      startPresentation(currentLanguage);
    }
  }, [currentLanguage, latestMetadata, showSlideMode, startPresentation]);

  // Fallback: play vrm_control when metadata arrives (in case onAssistantPlaybackStart ran before ref was set)
  useEffect(() => {
    const vc = latestMetadata?.vrm_control;
    if (!vc || !playKeyframeAnimationRef.current || lastVrmControlPlayedRef.current === vc) return;
    lastVrmControlPlayedRef.current = vc;
    playKeyframeAnimationRef.current(vc);
  }, [latestMetadata?.vrm_control]);

  return (
    <VoiceInterface
      language={currentLanguage}
      onLanguageChange={setCurrentLanguage}
      onVisemeControl={setVisemeFunction}
      showDefaultUI={false}
      onMetadataChange={setLatestMetadata}
      onAssistantPlaybackStart={({ metadata: playbackMetadata }) => {
        const vc = playbackMetadata?.vrm_control;
        if (vc && playKeyframeAnimationRef.current && lastVrmControlPlayedRef.current !== vc) {
          lastVrmControlPlayedRef.current = vc;
          playKeyframeAnimationRef.current(vc);
        }
      }}
    >
      {(voice) => {
        const labels = overlayLabels[voice.currentLanguage];
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
        const clarificationOptions = getClarificationOptions(
          voice.currentLanguage,
          voice.response,
          voice.metadata,
        );
        const bubbleHeading =
          voice.response.length > 0
            ? labels.responseLabel
            : voice.isLoading
              ? labels.loadingLabel
              : labels.guideLabel;
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
          const trimmed = textDraft.trim();
          if (!trimmed) {
            return;
          }

          await voice.sendMessage(trimmed);
          setTextDraft('');
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
                  showControls={showAvatarControls && !showSlideMode}
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
                  }}
                  onBackgroundChange={setCharacterBackground}
                  onLightingChange={setLightingIntensity}
                  settingsPanelPropsRef={settingsPanelPropsRef}
                />
              </div>

              {!showSlideMode && (
                <>
                  <div
                    className="pointer-events-none absolute inset-0 z-20"
                    style={screenPadding}
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
                          <p
                            className="text-base leading-7 text-pretty text-white/90 md:text-lg md:leading-8"
                            data-testid="response-text"
                          >
                            {voice.response || bubbleBody}
                          </p>
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
                                  onClick={isListening ? voice.stopListening : voice.startListening}
                                  disabled={isProcessing}
                                  aria-label={micButtonLabel}
                                  className={cn(
                                    'inline-flex size-16 items-center justify-center rounded-full shadow-xl transition-transform duration-200 ease-out md:size-20',
                                    'hover:scale-105 disabled:cursor-not-allowed disabled:hover:scale-100',
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

                {showSettingsPanel && settingsPanelPropsRef.current ? (
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
                        {...settingsPanelPropsRef.current}
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
                        on_close_slides={() => setShowSlideMode(false)}
                        open_slides_label={labels.openSlides}
                        close_slides_label={labels.closeSlides}
                      />
                    </div>
                  </div>
                ) : null}
                </>
              )}
              {showSlideMode ? (
                <div
                  className="pointer-events-none absolute inset-y-0 right-0 z-30 flex w-full justify-end"
                  style={screenPadding}
                >
                  <div className="pointer-events-auto flex h-full w-full max-w-6xl transform-gpu rounded-[32px] bg-white/95 shadow-2xl transition-all duration-300 ease-out">
                    <div className="relative flex h-full w-full flex-col overflow-hidden rounded-[32px]">
                      <button
                        type="button"
                        onClick={() => setShowSlideMode(false)}
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
  );
}
