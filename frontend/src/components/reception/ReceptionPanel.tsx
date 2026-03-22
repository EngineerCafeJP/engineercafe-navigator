'use client';

import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { Camera, Loader2, MessageSquare, Mic, PenLine, Sparkles } from 'lucide-react';

import { cn } from '@/lib/cn';
import { useReception } from '@/hooks/useReception';
import { OcrCameraView } from './OcrCameraView';
import { StageIndicator } from './StageIndicator';
import type { DeviceDetectionEvent } from '@/lib/api/device-webhook';

// Import side-effects to register the global webhook handler
import '@/lib/api/device-webhook';

const WELCOME_TIMEOUT_MS = 10_000;

interface ReceptionPanelProps {
  sessionId: string;
  language?: string;
  triggerType?: string;
  className?: string;
  /** Called when reception is completed and the system should switch to chat mode. */
  onReceptionComplete?: () => void;
}

export function ReceptionPanel({
  sessionId,
  language = 'ja',
  triggerType = 'button_press',
  className,
  onReceptionComplete,
}: ReceptionPanelProps) {
  const [draft, setDraft] = useState('');
  const hasAutoCompletedRef = useRef(false);
  const welcomeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const {
    stage,
    error,
    isLoading,
    purpose,
    messages,
    completion,
    enterWelcome,
    startOcr,
    handleOcrSuccess,
    handleOcrFallback,
    startReception,
    sendMessage,
    completeReception,
    resetReception,
  } = useReception({
    sessionId,
    language,
    triggerType,
  });

  // Wrap resetReception to also clear the auto-complete guard
  const handleReset = useCallback(() => {
    hasAutoCompletedRef.current = false;
    resetReception();
  }, [resetReception]);

  // --- 10-second welcome timeout ---
  const clearWelcomeTimer = useCallback(() => {
    if (welcomeTimerRef.current) {
      clearTimeout(welcomeTimerRef.current);
      welcomeTimerRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (stage !== 'welcome') {
      clearWelcomeTimer();
      return;
    }

    welcomeTimerRef.current = setTimeout(() => {
      startOcr('member_card');
    }, WELCOME_TIMEOUT_MS);

    return clearWelcomeTimer;
  }, [clearWelcomeTimer, stage, startOcr]);

  // --- Auto-complete when routing ---
  useEffect(() => {
    if (stage !== 'routing') {
      return;
    }

    if (isLoading || hasAutoCompletedRef.current) {
      return;
    }

    hasAutoCompletedRef.current = true;
    void completeReception().catch(() => {
      // Don't reset on error — let manual retry handle it
    });
  }, [completeReception, isLoading, stage]);

  // --- Notify parent on completion ---
  useEffect(() => {
    if (stage === 'completed' && onReceptionComplete) {
      onReceptionComplete();
    }
  }, [onReceptionComplete, stage]);

  // --- Device detection listener (#128) ---
  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<DeviceDetectionEvent>).detail;
      if (!detail) return;

      // Only auto-trigger when idle
      if (stage === 'idle') {
        enterWelcome();
      }
    };

    window.addEventListener('device-detection', handler);
    return () => {
      window.removeEventListener('device-detection', handler);
    };
  }, [enterWelcome, stage]);

  // --- Form submit ---
  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const message = draft.trim();
    if (!message || isLoading) {
      return;
    }

    setDraft('');
    await sendMessage(message);
  };

  const handleWelcomeAction = (action: 'member_card' | 'handwriting' | 'voice') => {
    clearWelcomeTimer();
    if (action === 'member_card') {
      startOcr('member_card');
    } else if (action === 'handwriting') {
      startOcr('handwriting');
    } else {
      void startReception();
    }
  };

  const isConversationActive =
    stage === 'greeting' ||
    stage === 'purpose_hearing' ||
    stage === 'routing' ||
    stage === 'completed';

  const showResetButton =
    stage !== 'idle' && stage !== 'completed';

  return (
    <section
      className={cn(
        'w-full max-w-3xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm',
        className,
      )}
    >
      <div className="flex flex-col gap-5">
        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-2">
            <span className="inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">
              <Sparkles className="size-3.5" aria-hidden="true" />
              Reception Mode
            </span>
            <div className="space-y-1">
              <h2 className="text-2xl font-semibold text-balance text-slate-950">
                {stage === 'idle'
                  ? 'Front Desk'
                  : stage === 'welcome'
                    ? 'Welcome'
                    : stage === 'camera_ocr' || stage === 'text_input'
                      ? 'Card / Text Recognition'
                      : 'Front Desk Conversation'}
              </h2>
            </div>
          </div>
          {showResetButton && (
            <button
              type="button"
              onClick={handleReset}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50"
            >
              Reset
            </button>
          )}
        </div>

        {/* Stage indicator — visible once past idle */}
        {stage !== 'idle' && <StageIndicator currentStage={stage} />}

        {/* === IDLE state === */}
        {stage === 'idle' && (
          <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center">
            <p className="mx-auto max-w-xl text-sm text-pretty text-slate-600">
              来訪者が到着すると、センサーが自動で受付を開始します。
              <br />
              手動で開始することもできます。
            </p>
            <button
              type="button"
              onClick={() => enterWelcome()}
              disabled={isLoading}
              className="mt-5 inline-flex items-center justify-center rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
            >
              受付を開始
            </button>
            {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

            {/* Debug trigger — development only */}
            {process.env.NODE_ENV === 'development' && (
              <button
                type="button"
                onClick={() => enterWelcome()}
                className="mt-4 block w-full text-center text-xs text-gray-400 transition-colors hover:text-gray-600"
              >
                Debug: Simulate visitor detection
              </button>
            )}
          </div>
        )}

        {/* === WELCOME state === */}
        {stage === 'welcome' && (
          <div className="rounded-xl border border-slate-200 bg-gradient-to-b from-slate-50 to-white p-8">
            <h3 className="text-center text-xl font-bold text-slate-900">
              エンジニアカフェへようこそ！
            </h3>
            <p className="mt-2 text-center text-sm text-slate-600">
              受付方法を選んでください
            </p>

            <div className="mt-6 flex flex-col gap-3">
              <button
                type="button"
                onClick={() => handleWelcomeAction('member_card')}
                className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white px-5 py-4 text-left transition-colors hover:border-slate-400 hover:bg-slate-50"
              >
                <Camera className="size-6 shrink-0 text-slate-700" />
                <div>
                  <p className="font-semibold text-slate-900">会員証読み取り</p>
                  <p className="text-xs text-slate-500">会員カードをカメラで読み取ります</p>
                </div>
              </button>

              <button
                type="button"
                onClick={() => handleWelcomeAction('handwriting')}
                className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white px-5 py-4 text-left transition-colors hover:border-slate-400 hover:bg-slate-50"
              >
                <PenLine className="size-6 shrink-0 text-slate-700" />
                <div>
                  <p className="font-semibold text-slate-900">筆談</p>
                  <p className="text-xs text-slate-500">手書きのメッセージを読み取ります</p>
                </div>
              </button>

              <button
                type="button"
                onClick={() => handleWelcomeAction('voice')}
                className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white px-5 py-4 text-left transition-colors hover:border-slate-400 hover:bg-slate-50"
              >
                <Mic className="size-6 shrink-0 text-slate-700" />
                <div>
                  <p className="font-semibold text-slate-900">音声で話す</p>
                  <p className="text-xs text-slate-500">マイクで直接お話しください</p>
                </div>
              </button>
            </div>

            <p className="mt-5 text-center text-xs text-slate-400">
              10秒後に自動でカメラが起動します
            </p>
          </div>
        )}

        {/* === CAMERA_OCR / TEXT_INPUT state === */}
        {(stage === 'camera_ocr' || stage === 'text_input') && (
          <OcrCameraView
            mode={stage === 'camera_ocr' ? 'member_card' : 'handwriting'}
            language={language}
            onSuccess={handleOcrSuccess}
            onFallback={handleOcrFallback}
          />
        )}

        {/* === Conversation states (greeting / purpose_hearing / routing / completed) === */}
        {isConversationActive && (
          <>
            {/* Message thread */}
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <div className="flex items-center gap-2 text-sm font-medium text-slate-700">
                <MessageSquare className="size-4" aria-hidden="true" />
                Conversation
              </div>
              <div className="mt-4 space-y-3">
                {messages.map((message) => (
                  <div
                    key={message.id}
                    className={cn(
                      'max-w-[85%] rounded-2xl px-4 py-3 text-sm shadow-sm',
                      message.role === 'assistant'
                        ? 'bg-white text-slate-800'
                        : 'ml-auto bg-slate-900 text-white',
                    )}
                  >
                    <p className="text-pretty">{message.text}</p>
                  </div>
                ))}
              </div>
            </div>

            {/* Purpose display */}
            {purpose && (
              <p className="text-sm text-slate-600">
                Current purpose:{' '}
                <span className="font-medium text-slate-900">{purpose}</span>
              </p>
            )}

            {/* Input form — hidden when completed */}
            {stage !== 'completed' ? (
              <form className="space-y-3" onSubmit={(event) => void handleSubmit(event)}>
                <label
                  className="block text-sm font-medium text-slate-700"
                  htmlFor="reception-message"
                >
                  Visitor response
                </label>
                <textarea
                  id="reception-message"
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  rows={3}
                  placeholder="Enter the visitor's message"
                  disabled={isLoading}
                  className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition-colors placeholder:text-slate-400 focus:border-slate-900"
                />
                <div className="flex items-center justify-between gap-3">
                  {error ? <p className="text-sm text-red-600">{error}</p> : <span />}
                  <button
                    type="submit"
                    disabled={isLoading || !draft.trim()}
                    className="inline-flex items-center justify-center rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
                  >
                    {isLoading && (
                      <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                    )}
                    <span className={cn(isLoading && 'ml-2')}>
                      {stage === 'routing' ? 'Finalizing' : 'Send Response'}
                    </span>
                  </button>
                </div>
              </form>
            ) : (
              <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-slate-700">
                <p className="font-semibold text-slate-900">Reception completed</p>
                <p className="mt-1 text-pretty">{completion?.response_text}</p>
                {completion?.target_agent && (
                  <p className="mt-3">
                    Route to:{' '}
                    <span className="font-medium text-slate-900">
                      {completion.target_agent}
                    </span>
                  </p>
                )}
                {completion?.requires_staff && (
                  <p className="mt-1 text-slate-600">
                    Staff assistance is required for this visitor.
                  </p>
                )}
              </div>
            )}
          </>
        )}

        {/* Global error (visible in all non-idle states that don't already show it) */}
        {error && !isConversationActive && stage !== 'idle' && (
          <p className="text-center text-sm text-red-600">{error}</p>
        )}
      </div>
    </section>
  );
}
