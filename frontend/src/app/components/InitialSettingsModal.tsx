'use client';

import { markAudioUserInteraction } from '@/lib/audio/audio-user-interaction-gate';
import {
  type KioskMicMode,
  type KioskTriggerMode,
  readKioskMicMode,
  readKioskTriggerMode,
  writeKioskMicMode,
  writeKioskTriggerMode,
} from '@/lib/kiosk-constants';
import { cn } from '@/lib/cn';
import { X } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

const copy = {
  ja: {
    title: '初期設定',
    triggerTitle: '操作のしかた',
    triggerScreen: '画面のボタンで操作する',
    triggerDevice: '物理ボタン・センサーで操作する（準備中）',
    displayLangTitle: '表示言語',
    displayLangJa: '日本語',
    displayLangEn: 'English',
    micModeTitle: '音声応対のマイクボタン',
    micPushToTalk: '押している間だけ聞き取る（プッシュトーク）',
    micToggle: '押すたびに録音のON/OFFが切り替わる',
    close: '閉じてはじめる',
    noticeFooter: '閉じる操作で音声再生が有効になります。',
  },
  en: {
    title: 'Before you start',
    triggerTitle: 'How to operate',
    triggerScreen: 'Use on-screen buttons',
    triggerDevice: 'Use physical buttons / sensors (coming soon)',
    displayLangTitle: 'Display language',
    displayLangJa: '日本語',
    displayLangEn: 'English',
    micModeTitle: 'Mic button (voice mode)',
    micPushToTalk: 'Push and hold to talk (push-to-talk)',
    micToggle: 'Tap to toggle recording on and off',
    close: 'Close and continue',
    noticeFooter: 'Closing enables audio playback in the browser.',
  },
} as const;

export interface InitialSettingsPreferences {
  language: 'ja' | 'en';
  triggerMode: KioskTriggerMode;
  micMode: KioskMicMode;
}

export interface InitialSettingsModalProps {
  language: 'ja' | 'en';
  open: boolean;
  onClose: () => void;
  onPreferencesSaved?: (prefs: InitialSettingsPreferences) => void;
  className?: string;
}

export default function InitialSettingsModal({
  language,
  open,
  onClose,
  onPreferencesSaved,
  className,
}: InitialSettingsModalProps) {
  const [uiLanguage, setUiLanguage] = useState<'ja' | 'en'>(language);
  const [triggerMode, setTriggerMode] = useState<KioskTriggerMode>('screen');
  const [micMode, setMicMode] = useState<KioskMicMode>('toggle');

  useEffect(() => {
    if (open) {
      setUiLanguage(language);
      setTriggerMode(readKioskTriggerMode());
      setMicMode(readKioskMicMode());
    }
  }, [open, language]);

  const labels = copy[uiLanguage];

  const handleClose = useCallback(async () => {
    writeKioskTriggerMode(triggerMode);
    writeKioskMicMode(micMode);
    onPreferencesSaved?.({
      language: uiLanguage,
      triggerMode,
      micMode,
    });
    markAudioUserInteraction();
    try {
      const { AudioInteractionManager } = await import('@/lib/audio/audio-interaction-manager');
      await AudioInteractionManager.getInstance().ensureAudioContext();
    } catch {
      // Autoplay gate may still block until further gesture; kiosk flow continues.
    }
    onClose();
  }, [micMode, onClose, onPreferencesSaved, triggerMode, uiLanguage]);

  if (!open) {
    return null;
  }

  return (
    <div
      className={cn('fixed inset-0 z-[100] flex items-center justify-center p-4', className)}
      role="dialog"
      aria-modal="true"
      aria-labelledby="initial-settings-title"
    >
      <div className="absolute inset-0 bg-black/55 backdrop-blur-[2px]" aria-hidden />
      <div className="pointer-events-none relative flex max-h-full w-full max-w-lg items-center justify-center">
        <div className="pointer-events-auto relative max-h-[min(90vh,720px)] w-full overflow-y-auto rounded-[28px] border border-white/20 bg-slate-900/95 p-6 text-white shadow-2xl backdrop-blur-md md:p-8">
          <button
            type="button"
            onClick={() => void handleClose()}
            className="absolute right-4 top-4 inline-flex size-10 items-center justify-center rounded-full bg-white/10 text-white transition-transform hover:scale-105"
            aria-label={labels.close}
          >
            <X className="size-5" />
          </button>

          <h2 id="initial-settings-title" className="pr-12 text-2xl font-semibold tracking-tight">
            {labels.title}
          </h2>

          <div className="mt-6 space-y-5 text-sm leading-relaxed text-white/90">
            <section className="rounded-2xl border border-white/15 bg-black/25 p-4">
              <h3 className="text-base font-semibold text-white">{labels.displayLangTitle}</h3>
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => setUiLanguage('ja')}
                  className={cn(
                    'rounded-full px-4 py-2 text-sm font-medium transition-colors',
                    uiLanguage === 'ja'
                      ? 'bg-white text-slate-900'
                      : 'bg-white/10 text-white/80 hover:bg-white/15',
                  )}
                >
                  {labels.displayLangJa}
                </button>
                <button
                  type="button"
                  onClick={() => setUiLanguage('en')}
                  className={cn(
                    'rounded-full px-4 py-2 text-sm font-medium transition-colors',
                    uiLanguage === 'en'
                      ? 'bg-white text-slate-900'
                      : 'bg-white/10 text-white/80 hover:bg-white/15',
                  )}
                >
                  {labels.displayLangEn}
                </button>
              </div>
            </section>

            <section className="rounded-2xl border border-white/15 bg-black/25 p-4">
              <h3 className="text-base font-semibold text-white">{labels.triggerTitle}</h3>
              <div className="mt-3 flex flex-col gap-3">
                <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-white/10 bg-white/5 p-3 has-[:checked]:border-sky-400/60">
                  <input
                    type="radio"
                    name="kiosk-trigger"
                    className="mt-1"
                    checked={triggerMode === 'screen'}
                    onChange={() => setTriggerMode('screen')}
                  />
                  <span>{labels.triggerScreen}</span>
                </label>
                <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-white/10 bg-white/5 p-3 has-[:checked]:border-sky-400/60">
                  <input
                    type="radio"
                    name="kiosk-trigger"
                    className="mt-1"
                    checked={triggerMode === 'device'}
                    onChange={() => setTriggerMode('device')}
                  />
                  <span className="text-white/85">{labels.triggerDevice}</span>
                </label>
              </div>
            </section>

            <section className="rounded-2xl border border-white/15 bg-black/25 p-4">
              <h3 className="text-base font-semibold text-white">{labels.micModeTitle}</h3>
              <div className="mt-3 flex flex-col gap-3">
                <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-white/10 bg-white/5 p-3 has-[:checked]:border-sky-400/60">
                  <input
                    type="radio"
                    name="kiosk-mic-mode"
                    className="mt-1"
                    checked={micMode === 'toggle'}
                    onChange={() => setMicMode('toggle')}
                  />
                  <span>{labels.micToggle}</span>
                </label>
                <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-white/10 bg-white/5 p-3 has-[:checked]:border-sky-400/60">
                  <input
                    type="radio"
                    name="kiosk-mic-mode"
                    className="mt-1"
                    checked={micMode === 'push_to_talk'}
                    onChange={() => setMicMode('push_to_talk')}
                  />
                  <span>{labels.micPushToTalk}</span>
                </label>
              </div>
            </section>
          </div>

          <p className="mt-6 text-xs text-white/55">{labels.noticeFooter}</p>

          <div className="mt-6 flex justify-end">
            <button
              type="button"
              onClick={() => void handleClose()}
              className="inline-flex min-h-11 min-w-[140px] items-center justify-center rounded-full bg-white px-6 py-3 text-sm font-semibold text-slate-900 shadow-lg transition-transform hover:scale-[1.02]"
            >
              {labels.close}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
