'use client';

import { Languages, X } from 'lucide-react';

interface SlideLanguagePickerProps {
  language: 'ja' | 'en';
  onClose: () => void;
  onStartPresentation: (language: 'ja' | 'en') => void;
}

export function SlideLanguagePicker({
  language,
  onClose,
  onStartPresentation,
}: SlideLanguagePickerProps) {
  return (
    <div className="pointer-events-auto absolute inset-0 z-50 flex items-center justify-center bg-black/55 px-4 backdrop-blur-sm">
      <div className="w-full max-w-sm rounded-lg border border-white/25 bg-white p-5 text-slate-900 shadow-2xl">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="inline-flex size-10 items-center justify-center rounded-lg bg-slate-900 text-white">
              <Languages className="size-5" aria-hidden />
            </span>
            <div>
              <h2 className="text-base font-semibold leading-6">
                {language === 'ja' ? 'スライド案内の言語' : 'Slide Guide Language'}
              </h2>
              <p className="mt-1 text-sm leading-5 text-slate-600">
                {language === 'ja'
                  ? '表示と音声の言語を選んでください。'
                  : 'Choose the language for slides and narration.'}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={language === 'ja' ? '閉じる' : 'Close'}
            className="inline-flex size-9 shrink-0 items-center justify-center rounded-lg border border-slate-200 text-slate-600 transition-colors hover:bg-slate-50"
          >
            <X className="size-4" aria-hidden />
          </button>
        </div>
        <div className="mt-5 grid grid-cols-2 gap-3">
          <button
            type="button"
            data-testid="slide-language-ja"
            onClick={() => onStartPresentation('ja')}
            className="flex min-h-20 flex-col items-center justify-center rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 text-center transition-colors hover:border-slate-900 hover:bg-white"
          >
            <span className="text-lg font-semibold">日本語</span>
            <span className="mt-1 text-xs text-slate-500">Japanese</span>
          </button>
          <button
            type="button"
            data-testid="slide-language-en"
            onClick={() => onStartPresentation('en')}
            className="flex min-h-20 flex-col items-center justify-center rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 text-center transition-colors hover:border-slate-900 hover:bg-white"
          >
            <span className="text-lg font-semibold">English</span>
            <span className="mt-1 text-xs text-slate-500">英語</span>
          </button>
        </div>
      </div>
    </div>
  );
}
