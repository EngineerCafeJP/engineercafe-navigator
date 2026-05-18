'use client';

import { cn } from '@/lib/cn';
import { unlockAudioForUserGesture } from '@/lib/audio/audio-interaction-manager';
import { AlertCircle, Loader2, Mic, MicOff, Volume2, VolumeX, XCircle } from 'lucide-react';
import { STATUS_LABELS } from './constants';
import type { VoiceInterfaceRenderProps } from './types';

interface VoiceInterfaceDefaultUIProps {
  renderProps: VoiceInterfaceRenderProps;
  layout: 'vertical' | 'horizontal';
  className?: string;
}

export function VoiceInterfaceDefaultUI({
  renderProps,
  layout,
  className,
}: VoiceInterfaceDefaultUIProps) {
  const {
    cancelSession,
    currentLanguage,
    error,
    isLoading,
    isMuted,
    loadingMessage,
    response,
    sessionState,
    setMuted,
    setVolume,
    startListening,
    stopListening,
    transcript,
    unlockAudioPlayback,
    volume,
  } = renderProps;
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
