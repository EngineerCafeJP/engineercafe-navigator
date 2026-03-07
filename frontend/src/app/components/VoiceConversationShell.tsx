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
  Volume2,
  XCircle,
} from 'lucide-react';
import { useState, type ReactNode } from 'react';
import VoiceInterface, {
  type VoiceSessionState,
} from './VoiceInterface';
import ClarificationButtons from './ClarificationButtons';

interface VoiceConversationShellProps {
  language?: 'ja' | 'en';
  onLanguageChange?: (language: 'ja' | 'en') => void;
  onVisemeControl?: ((viseme: string, intensity: number) => void) | null;
  renderAvatar?: (props: {
    sessionState: VoiceSessionState;
    isMuted: boolean;
    volume: number;
  }) => ReactNode;
}

const shellLabels = {
  ja: {
    title: '音声ガイド',
    subtitle: 'マイク中心で案内します。必要なときだけテキストを補助入力してください。',
    idle: '話しかける',
    listening: '録音を止める',
    processing: '応答を生成中',
    speaking: '応答を再生中',
    responseTitle: '応答',
    transcriptTitle: '聞き取り結果',
    wakeWordReady: 'ウェイクワード待機中',
    wakeWordOff: 'マイク操作で開始',
    textToggle: 'テキスト入力を開く',
    textPlaceholder: 'ここに質問を入力します',
    send: '送信',
    cancel: 'キャンセル',
    languageJa: '日本語',
    languageEn: 'English',
  },
  en: {
    title: 'Voice Guide',
    subtitle: 'Voice is the primary interaction. Open the text field only when you need a backup.',
    idle: 'Start talking',
    listening: 'Stop recording',
    processing: 'Generating',
    speaking: 'Speaking',
    responseTitle: 'Answer',
    transcriptTitle: 'Transcript',
    wakeWordReady: 'Wake word is armed',
    wakeWordOff: 'Use the mic button',
    textToggle: 'Open text input',
    textPlaceholder: 'Type your question here',
    send: 'Send',
    cancel: 'Cancel',
    languageJa: 'Japanese',
    languageEn: 'English',
  },
} as const;

const buttonCopy: Record<VoiceSessionState, keyof typeof shellLabels.ja> = {
  idle: 'idle',
  listening: 'listening',
  processing: 'processing',
  speaking: 'speaking',
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

export default function VoiceConversationShell({
  language = 'ja',
  onLanguageChange,
  onVisemeControl,
  renderAvatar,
}: VoiceConversationShellProps) {
  const [draft, setDraft] = useState('');

  return (
    <VoiceInterface
      language={language}
      onLanguageChange={onLanguageChange}
      onVisemeControl={onVisemeControl}
      showDefaultUI={false}
    >
      {(voice) => {
        const labels = shellLabels[voice.currentLanguage];
        const isListening = voice.sessionState === 'listening';
        const isProcessing = voice.sessionState === 'processing';
        const isSpeaking = voice.sessionState === 'speaking';
        const waveformBars = (
          isListening || isSpeaking ? voice.waveformBars : [0.18, 0.24, 0.2, 0.26, 0.18]
        ).map((value) => Math.max(value, 0.16));
        const clarificationOptions = getClarificationOptions(
          voice.currentLanguage,
          voice.response,
          voice.metadata,
        );

        const submitDraft = async () => {
          const trimmed = draft.trim();
          if (!trimmed) {
            return;
          }

          await voice.sendMessage(trimmed);
          setDraft('');
        };

        return (
          <section className="rounded-[28px] border border-slate-200 bg-white/90 p-4 shadow-sm backdrop-blur-sm md:p-6">
            <div className="grid gap-6 xl:grid-cols-[minmax(0,1.05fr)_minmax(320px,420px)]">
              <div className="space-y-4">
                <header className="flex flex-wrap items-start justify-between gap-4">
                  <div className="space-y-2">
                    <p className="text-sm font-medium text-slate-500">{labels.title}</p>
                    <h1 className="text-balance text-2xl font-semibold text-slate-950 md:text-3xl">
                      {labels.subtitle}
                    </h1>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => onLanguageChange?.('ja')}
                      className={cn(
                        'rounded-full px-3 py-1.5 text-sm font-medium transition-colors',
                        voice.currentLanguage === 'ja'
                          ? 'bg-slate-900 text-white'
                          : 'bg-slate-100 text-slate-700',
                      )}
                    >
                      {labels.languageJa}
                    </button>
                    <button
                      type="button"
                      onClick={() => onLanguageChange?.('en')}
                      className={cn(
                        'rounded-full px-3 py-1.5 text-sm font-medium transition-colors',
                        voice.currentLanguage === 'en'
                          ? 'bg-slate-900 text-white'
                          : 'bg-slate-100 text-slate-700',
                      )}
                    >
                      {labels.languageEn}
                    </button>
                  </div>
                </header>

                {renderAvatar ? (
                  <div className="overflow-hidden rounded-[24px] border border-slate-200 bg-slate-50">
                    {renderAvatar({
                      sessionState: voice.sessionState,
                      isMuted: voice.isMuted,
                      volume: voice.volume,
                    })}
                  </div>
                ) : null}

                <div className="rounded-[24px] border border-slate-200 bg-slate-950 px-5 py-6 text-white">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium text-slate-300">
                        {voice.wakeWord.isSupported && !voice.error
                          ? labels.wakeWordReady
                          : labels.wakeWordOff}
                      </p>
                      <p className="mt-1 text-sm text-slate-400">
                        {labels[buttonCopy[voice.sessionState]]}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={isListening ? voice.stopListening : voice.startListening}
                      disabled={isProcessing}
                      aria-label={labels[buttonCopy[voice.sessionState]]}
                      className={cn(
                        'relative flex size-28 items-center justify-center rounded-full text-white transition-transform duration-200 md:size-32',
                        isListening && 'bg-rose-500 motion-safe:animate-pulse',
                        isProcessing && 'bg-amber-500',
                        isSpeaking && 'bg-sky-500',
                        voice.sessionState === 'idle' && 'bg-white text-slate-950',
                        !isProcessing && 'motion-safe:hover:scale-[1.02]',
                      )}
                    >
                      <span className="absolute inset-0 rounded-full border border-white/10" />
                      {isProcessing ? (
                        <Loader2 className="size-11 animate-spin" />
                      ) : isListening ? (
                        <MicOff className="size-11" />
                      ) : isSpeaking ? (
                        <Volume2 className="size-11" />
                      ) : (
                        <Mic className="size-11" />
                      )}
                    </button>
                  </div>

                  <div className="mt-5 flex items-end justify-center gap-2">
                    {waveformBars.map((bar, index) => (
                      <span
                        key={`${index}-${bar}`}
                        className={cn(
                          'w-2 rounded-full bg-white/85 transition-transform duration-150',
                          (isListening || isSpeaking) && 'motion-safe:animate-pulse',
                          isProcessing && 'bg-amber-100',
                        )}
                        style={{ height: '48px', transform: `scaleY(${bar})` }}
                      />
                    ))}
                  </div>

                  <div className="mt-5 flex flex-wrap gap-3">
                    <button
                      type="button"
                      onClick={voice.clearConversation}
                      className="inline-flex items-center gap-2 rounded-full border border-white/15 px-4 py-2 text-sm font-medium text-white/90 transition-colors hover:bg-white/10"
                    >
                      <XCircle className="size-4" />
                      {labels.cancel}
                    </button>
                    {voice.loadingMessage ? (
                      <div className="inline-flex items-center gap-2 rounded-full bg-white/10 px-4 py-2 text-sm text-white/80">
                        <Loader2 className="size-4 animate-spin" />
                        {voice.loadingMessage}
                      </div>
                    ) : null}
                  </div>
                </div>
              </div>

              <div className="space-y-4">
                <div className="rounded-[24px] border border-slate-200 bg-slate-50 p-5">
                  <p className="text-sm font-medium text-slate-500">{labels.responseTitle}</p>
                  <div className="mt-3 space-y-4">
                    {voice.transcript ? (
                      <div className="rounded-2xl bg-white p-4">
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                          {labels.transcriptTitle}
                        </p>
                        <p className="mt-2 text-pretty text-sm leading-6 text-slate-700">
                          {voice.transcript}
                        </p>
                      </div>
                    ) : null}
                    <div className="min-h-40 rounded-2xl bg-white p-4">
                      <p className="text-pretty text-sm leading-7 text-slate-800">
                        {voice.response ||
                          (voice.currentLanguage === 'ja'
                            ? '回答はここに表示されます。'
                            : 'The answer will appear here.')}
                      </p>
                    </div>
                    {clarificationOptions.length > 0 ? (
                      <div className="rounded-2xl bg-white p-4">
                        <ClarificationButtons
                          key={`${voice.response}-${clarificationOptions.join('|')}`}
                          options={clarificationOptions}
                          onSelect={voice.sendMessage}
                        />
                      </div>
                    ) : null}
                  </div>
                </div>

                {voice.error ? (
                  <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
                    {voice.error}
                  </div>
                ) : null}

                <details className="group rounded-[24px] border border-slate-200 bg-white p-5">
                  <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-medium text-slate-700">
                    <span className="inline-flex items-center gap-2">
                      <MessageSquare className="size-4" />
                      {labels.textToggle}
                    </span>
                    <ChevronDown className="size-4 text-slate-400 transition-transform duration-200 group-open:rotate-180" />
                  </summary>
                  <div className="mt-4 space-y-3">
                    <textarea
                      value={draft}
                      onChange={(event) => setDraft(event.target.value)}
                      placeholder={labels.textPlaceholder}
                      rows={4}
                      className="w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm leading-6 text-slate-900 outline-none transition-colors focus:border-slate-400"
                    />
                    <div className="flex justify-end">
                      <button
                        type="button"
                        onClick={() => {
                          void submitDraft();
                        }}
                        disabled={!draft.trim()}
                        className="inline-flex items-center gap-2 rounded-full bg-slate-900 px-4 py-2 text-sm font-medium text-white transition-colors disabled:bg-slate-300"
                      >
                        <SendHorizontal className="size-4" />
                        {labels.send}
                      </button>
                    </div>
                  </div>
                </details>
              </div>
            </div>
          </section>
        );
      }}
    </VoiceInterface>
  );
}
