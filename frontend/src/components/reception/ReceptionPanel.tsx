'use client';

import { FormEvent, useEffect, useRef, useState } from 'react';
import { Loader2, MessageSquare, Sparkles } from 'lucide-react';

import { cn } from '@/lib/cn';
import { useReception } from '@/hooks/useReception';
import { StageIndicator } from './StageIndicator';

interface ReceptionPanelProps {
  sessionId: string;
  language?: string;
  triggerType?: string;
  className?: string;
}

export function ReceptionPanel({
  sessionId,
  language = 'ja',
  triggerType = 'manual',
  className,
}: ReceptionPanelProps) {
  const [draft, setDraft] = useState('');
  const hasAutoCompletedRef = useRef(false);
  const {
    stage,
    error,
    isLoading,
    purpose,
    messages,
    completion,
    startReception,
    sendMessage,
    completeReception,
    resetReception,
  } = useReception({
    sessionId,
    language,
    triggerType,
  });

  useEffect(() => {
    if (stage !== 'routing') {
      hasAutoCompletedRef.current = false;
      return;
    }

    if (isLoading || hasAutoCompletedRef.current) {
      return;
    }

    hasAutoCompletedRef.current = true;
    void completeReception().catch(() => {
      hasAutoCompletedRef.current = false;
    });
  }, [completeReception, isLoading, stage]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const message = draft.trim();
    if (!message || isLoading) {
      return;
    }

    setDraft('');
    await sendMessage(message);
  };

  const isConversationActive = stage !== 'idle';

  return (
    <section
      className={cn(
        'w-full max-w-3xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm',
        className
      )}
    >
      <div className="flex flex-col gap-5">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-2">
            <span className="inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">
              <Sparkles className="size-3.5" aria-hidden="true" />
              Reception Mode
            </span>
            <div className="space-y-1">
              <h2 className="text-2xl font-semibold text-balance text-slate-950">
                Front Desk Conversation
              </h2>
              <p className="text-sm text-pretty text-slate-600">
                Start a guided reception flow, collect the visitor&apos;s purpose, and route them to
                the right next action.
              </p>
            </div>
          </div>
          {isConversationActive && (
            <button
              type="button"
              onClick={resetReception}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50"
            >
              Reset
            </button>
          )}
        </div>

        <StageIndicator currentStage={stage} />

        {!isConversationActive ? (
          <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center">
            <p className="mx-auto max-w-xl text-sm text-pretty text-slate-600">
              Start reception when a visitor arrives. The assistant will greet them, ask their
              purpose, and finalize routing once enough detail is collected.
            </p>
            <button
              type="button"
              onClick={() => void startReception()}
              disabled={isLoading}
              className="mt-5 inline-flex items-center justify-center rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
            >
              {isLoading ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : null}
              <span className={cn(isLoading && 'ml-2')}>Start Reception</span>
            </button>
            {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : null}
          </div>
        ) : (
          <>
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
                        : 'ml-auto bg-slate-900 text-white'
                    )}
                  >
                    <p className="text-pretty">{message.text}</p>
                  </div>
                ))}
              </div>
            </div>

            {purpose ? (
              <p className="text-sm text-slate-600">
                Current purpose: <span className="font-medium text-slate-900">{purpose}</span>
              </p>
            ) : null}

            {stage !== 'completed' ? (
              <form className="space-y-3" onSubmit={(event) => void handleSubmit(event)}>
                <label className="block text-sm font-medium text-slate-700" htmlFor="reception-message">
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
                    {isLoading ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : null}
                    <span className={cn(isLoading && 'ml-2')}>{stage === 'routing' ? 'Finalizing' : 'Send Response'}</span>
                  </button>
                </div>
              </form>
            ) : (
              <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-slate-700">
                <p className="font-semibold text-slate-900">Reception completed</p>
                <p className="mt-1 text-pretty">{completion?.response_text}</p>
                {completion?.target_agent ? (
                  <p className="mt-3">
                    Route to: <span className="font-medium text-slate-900">{completion.target_agent}</span>
                  </p>
                ) : null}
                {completion?.requires_staff ? (
                  <p className="mt-1 text-slate-600">Staff assistance is required for this visitor.</p>
                ) : null}
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
