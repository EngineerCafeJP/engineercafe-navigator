'use client';

import { Dialog, DialogPanel, DialogTitle } from '@headlessui/react';
import { cn } from '@/lib/cn';
import { ClarificationUtils } from '@/lib/clarification-utils';
import {
  ChevronDown,
  Loader2,
  MessageSquare,
  Mic,
  MicOff,
  Presentation,
  SendHorizontal,
  Volume2,
  X,
  XCircle,
} from 'lucide-react';
import { useCallback, useState, type CSSProperties, type KeyboardEvent } from 'react';
import type { BackgroundOption } from './components/BackgroundSelector';
import CharacterAvatar from './components/CharacterAvatar';
import ClarificationButtons from './components/ClarificationButtons';
import MarpViewer from './components/MarpViewer';
import VoiceInterface, { type VoiceSessionState } from './components/VoiceInterface';

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
    textToggleOpen: 'テキスト入力',
    textToggleClose: '入力を閉じる',
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
    textToggleOpen: 'Text input',
    textToggleClose: 'Hide text input',
    textPlaceholder: 'Type your question here',
    send: 'Send',
    openSlides: 'Open slides',
    closeSlides: 'Close slides',
    clearConversation: 'Clear conversation',
    cancelSession: 'Cancel current turn',
    languageJa: 'Japanese',
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

  return (
    <VoiceInterface
      language={currentLanguage}
      onLanguageChange={setCurrentLanguage}
      onVisemeControl={setVisemeFunction}
      showDefaultUI={false}
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

        const submitTextDraft = async () => {
          const trimmed = textDraft.trim();
          if (!trimmed) {
            return;
          }

          await voice.sendMessage(trimmed);
          setTextDraft('');
        };

        const handleDraftKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
          if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            void submitTextDraft();
          }
        };

        return (
          <>
            <main className="relative h-[100svh] w-screen overflow-hidden">
              <div className="absolute inset-0 -z-10" style={stageBackgroundStyle}>
                <CharacterAvatar
                  modelPath="/characters/models/sakura.vrm"
                  sessionState={voice.sessionState}
                  background={characterBackground}
                  lightingIntensity={lightingIntensity}
                  enableClickAnimation={!showSlideMode}
                  showControls={!showSlideMode}
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
                  onBackgroundChange={setCharacterBackground}
                  onLightingChange={setLightingIntensity}
                />
              </div>

              <div
                className="pointer-events-none absolute inset-x-0 top-0 z-10 flex justify-center px-4 md:px-6"
                style={{
                  paddingTop: 'max(1rem, env(safe-area-inset-top))',
                  paddingLeft: 'max(1rem, env(safe-area-inset-left))',
                  paddingRight: 'max(1rem, env(safe-area-inset-right))',
                }}
              >
                <div className="pointer-events-auto w-full max-w-lg rounded-[28px] bg-black/60 p-4 text-white shadow-xl backdrop-blur-md transition-opacity duration-200 ease-out md:p-5">
                  <div className="flex items-center justify-between gap-3 text-xs font-medium text-white/70">
                    <span>{bubbleHeading}</span>
                    <span>
                      {voice.wakeWord.isSupported && !voice.error
                        ? labels.wakeWordReady
                        : labels.wakeWordOff}
                    </span>
                  </div>

                  {voice.transcript ? (
                    <div className="mt-3 rounded-2xl bg-white/8 px-3 py-2">
                      <p className="text-xs font-medium text-white/60">{labels.transcriptLabel}</p>
                      <p className="mt-1 text-sm text-pretty text-white/85" style={transcriptClampStyle}>
                        {voice.transcript}
                      </p>
                    </div>
                  ) : null}

                  <div className="mt-3">
                    <p className="text-base leading-7 text-pretty text-white md:text-lg" style={responseClampStyle}>
                      {bubbleBody}
                    </p>
                    {!voice.response && !voice.isLoading ? (
                      <p className="mt-2 text-sm text-pretty text-white/65">{labels.helperPrompt}</p>
                    ) : null}
                  </div>

                  {clarificationOptions.length > 0 ? (
                    <div className="mt-4">
                      <ClarificationButtons
                        options={clarificationOptions}
                        onSelect={voice.sendMessage}
                      />
                    </div>
                  ) : null}
                </div>
              </div>

              <div
                className="absolute z-30"
                style={{
                  top: 'max(1rem, env(safe-area-inset-top))',
                  right: 'max(4.75rem, calc(env(safe-area-inset-right) + 1rem))',
                }}
              >
                <button
                  type="button"
                  onClick={() => startPresentation(voice.currentLanguage)}
                  aria-label={labels.openSlides}
                  className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-black/45 px-3 py-2 text-sm font-medium text-white shadow-lg backdrop-blur-md transition-transform duration-200 ease-out hover:scale-105"
                >
                  <Presentation className="size-4" />
                  <span className="hidden sm:inline">{labels.openSlides}</span>
                  <span className="rounded-full bg-white/10 px-2 py-1 text-xs font-semibold">
                    {voice.currentLanguage.toUpperCase()}
                  </span>
                </button>
              </div>

              <div
                className="absolute inset-x-0 bottom-0 z-20 px-4 md:px-6"
                style={{
                  paddingBottom: 'max(1rem, env(safe-area-inset-bottom))',
                  paddingLeft: 'max(1rem, env(safe-area-inset-left))',
                  paddingRight: 'max(1rem, env(safe-area-inset-right))',
                }}
              >
                <div className="mx-auto flex w-full max-w-md flex-col items-center gap-3">
                  {voice.error ? (
                    <div className="w-full rounded-2xl border border-rose-400/30 bg-rose-500/20 px-4 py-3 text-sm text-white shadow-lg">
                      {voice.error}
                    </div>
                  ) : null}

                  <div className="w-full rounded-[32px] border border-white/15 bg-black/35 px-4 py-4 text-white shadow-xl backdrop-blur-md md:px-5">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-medium text-white/70">
                        {visualState === 'idle'
                          ? labels.currentLocale
                          : labels[buttonCopy[visualState]]}
                      </p>
                      {canCancelTurn || showConversationReset ? (
                        <button
                          type="button"
                          onClick={canCancelTurn ? voice.cancelSession : voice.clearConversation}
                          aria-label={canCancelTurn ? labels.cancelSession : labels.clearConversation}
                          className="inline-flex size-10 items-center justify-center rounded-full bg-white/10 text-white transition-transform duration-200 ease-out hover:scale-105"
                        >
                          {canCancelTurn ? <XCircle className="size-5" /> : <X className="size-5" />}
                        </button>
                      ) : (
                        <div className="size-10" aria-hidden="true" />
                      )}
                    </div>

                    <div className="mt-4 flex items-end justify-center gap-2">
                      {waveformBars.map((bar, index) => (
                        <span
                          key={`${index}-${bar}`}
                          className={cn(
                            'h-8 w-1.5 rounded-full bg-white/80 transition-transform duration-200 ease-out md:h-10',
                            isProcessing && 'bg-amber-100',
                          )}
                          style={{
                            transform: `scaleY(${bar})`,
                            transformOrigin: 'center bottom',
                          }}
                        />
                      ))}
                    </div>

                    <div className="mt-4 flex justify-center">
                      <button
                        type="button"
                        onClick={isListening ? voice.stopListening : voice.startListening}
                        disabled={isProcessing}
                        aria-label={micButtonLabel}
                        className={cn(
                          'inline-flex size-20 items-center justify-center rounded-full shadow-xl transition-transform duration-200 ease-out md:size-24',
                          'hover:scale-105 disabled:cursor-not-allowed disabled:hover:scale-100',
                          visualState === 'idle' && 'bg-white text-slate-900',
                          visualState === 'listening' && 'bg-rose-500 text-white motion-safe:animate-pulse',
                          visualState === 'processing' && 'bg-amber-500 text-white',
                          visualState === 'speaking' && 'bg-sky-500 text-white',
                        )}
                      >
                        {visualState === 'processing' ? (
                          <Loader2 className="size-8 animate-spin md:size-9" />
                        ) : visualState === 'listening' ? (
                          <MicOff className="size-8 md:size-9" />
                        ) : visualState === 'speaking' ? (
                          <Volume2 className="size-8 md:size-9" />
                        ) : (
                          <Mic className="size-8 md:size-9" />
                        )}
                      </button>
                    </div>

                    <div className="mt-4 flex items-center justify-center gap-2">
                      <button
                        type="button"
                        onClick={() => setCurrentLanguage('ja')}
                        className={cn(
                          'rounded-full px-3 py-1.5 text-sm font-medium transition-colors',
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
                          'rounded-full px-3 py-1.5 text-sm font-medium transition-colors',
                          voice.currentLanguage === 'en'
                            ? 'bg-white/90 text-slate-900'
                            : 'bg-white/20 text-white/70',
                        )}
                      >
                        {labels.languageEn}
                      </button>
                    </div>

                    <div className="mt-4 flex items-center justify-center">
                      <button
                        type="button"
                        onClick={() => setShowTextInput((current) => !current)}
                        className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-2 text-sm font-medium text-white transition-transform duration-200 ease-out hover:scale-105"
                      >
                        {showTextInput ? <ChevronDown className="size-4" /> : <MessageSquare className="size-4" />}
                        {showTextInput ? labels.textToggleClose : labels.textToggleOpen}
                      </button>
                    </div>
                  </div>

                  {showTextInput ? (
                    <div className="w-full rounded-[28px] border border-white/20 bg-white/10 p-4 text-white shadow-xl backdrop-blur-md">
                      <label className="sr-only" htmlFor="voice-text-draft">
                        {labels.textPlaceholder}
                      </label>
                      <textarea
                        id="voice-text-draft"
                        value={textDraft}
                        onChange={(event) => setTextDraft(event.target.value)}
                        onKeyDown={handleDraftKeyDown}
                        rows={3}
                        placeholder={labels.textPlaceholder}
                        aria-label={labels.textPlaceholder}
                        className="min-h-24 w-full resize-none rounded-2xl border border-white/15 bg-black/20 px-4 py-3 text-sm text-white placeholder:text-white/45 focus:outline-none focus:ring-2 focus:ring-white/30"
                      />
                      <div className="mt-3 flex items-center justify-between gap-3">
                        <p className="text-sm text-white/65">{labels.helperPrompt}</p>
                        <button
                          type="button"
                          onClick={() => void submitTextDraft()}
                          disabled={!textDraft.trim() || isInputDisabled}
                          aria-label={labels.send}
                          className="inline-flex size-11 items-center justify-center rounded-full bg-white text-slate-900 shadow-lg transition-transform duration-200 ease-out hover:scale-105 disabled:cursor-not-allowed disabled:bg-white/40 disabled:text-slate-500 disabled:hover:scale-100"
                        >
                          <SendHorizontal className="size-5" />
                        </button>
                      </div>
                    </div>
                  ) : null}
                </div>
              </div>
            </main>

            <Dialog
              open={showSlideMode}
              onClose={setShowSlideMode}
              className="relative z-40"
            >
              <div className="fixed inset-0 bg-black/50 backdrop-blur-sm" aria-hidden="true" />
              <div className="fixed inset-0 flex items-center justify-center px-4 py-6 md:px-8">
                <DialogPanel className="relative w-full max-w-5xl overflow-hidden rounded-[32px] bg-white shadow-2xl">
                  <DialogTitle className="sr-only">{labels.openSlides}</DialogTitle>
                  <button
                    type="button"
                    onClick={() => setShowSlideMode(false)}
                    aria-label={labels.closeSlides}
                    className="absolute right-4 top-4 z-10 inline-flex size-11 items-center justify-center rounded-full bg-black/70 text-white shadow-lg transition-transform duration-200 ease-out hover:scale-105"
                  >
                    <X className="size-5" />
                  </button>
                  <div className="h-[82svh] w-full bg-white md:h-[46rem]">
                    <MarpViewer
                      language={voice.currentLanguage}
                      onVisemeControl={setVisemeFunction}
                      onExpressionControl={setExpressionFunction}
                      volume={Math.round(voice.volume * 100)}
                    />
                  </div>
                </DialogPanel>
              </div>
            </Dialog>
          </>
        );
      }}
    </VoiceInterface>
  );
}
