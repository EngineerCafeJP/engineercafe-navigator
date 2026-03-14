'use client';

import { ArrowLeft, Languages } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

import CharacterAvatar from '@/app/components/CharacterAvatar';
import MarpViewer from '@/app/components/MarpViewer';

const guideCopy = {
  ja: {
    badge: 'Customer Surface',
    title: '初回登録ガイド',
    subtitle:
      'エンジニアカフェの概要、利用マナー、初回登録、利用規約の要点を順番に説明します。',
    agendaTitle: 'このガイドで扱う内容',
    agenda: ['施設の概要', '文化財での利用マナー', '会員登録の流れ', '次回以降の受付'],
    back: '受付画面に戻る',
    toggle: '英語に切り替え',
  },
  en: {
    badge: 'Customer Surface',
    title: 'First Visit Registration Guide',
    subtitle:
      'This guide walks through Engineer Cafe, cultural-property etiquette, first-time registration, and key terms for future visits.',
    agendaTitle: 'What this covers',
    agenda: ['Facility overview', 'Etiquette and terms', 'Registration flow', 'Future check-in process'],
    back: 'Back to reception',
    toggle: 'Switch to Japanese',
  },
} as const;

export default function CustomerGuideShell() {
  const router = useRouter();
  const [language, setLanguage] = useState<'ja' | 'en'>('ja');
  const [autoPlay, setAutoPlay] = useState(false);
  const [setViseme, setSetViseme] = useState<((viseme: string, intensity: number) => void) | null>(null);
  const [setExpression, setSetExpression] = useState<((expression: string, weight: number) => void) | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const nextLanguage = params.get('lang') === 'en' ? 'en' : 'ja';
    setLanguage(nextLanguage);
    setAutoPlay(params.get('autoplay') === '1');
  }, []);

  const copy = guideCopy[language];

  const handleLanguageChange = (nextLanguage: 'ja' | 'en') => {
    setLanguage(nextLanguage);
    const params = new URLSearchParams(window.location.search);
    params.set('lang', nextLanguage);
    router.replace(`/onboarding?${params.toString()}`);
  };

  return (
    <main
      className="min-h-dvh bg-slate-100 px-4 py-4 md:px-6 md:py-6"
      data-testid="customer-guide-shell"
    >
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-4">
        <header className="flex flex-col gap-4 rounded-3xl border border-slate-200 bg-white p-5 shadow-sm lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-3xl">
            <p className="text-xs font-semibold uppercase text-slate-500">{copy.badge}</p>
            <h1 className="mt-2 text-balance text-3xl font-semibold text-slate-950">{copy.title}</h1>
            <p className="mt-3 text-pretty text-sm leading-6 text-slate-600">{copy.subtitle}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => router.push('/')}
              className="inline-flex min-h-11 items-center gap-2 rounded-full border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-900 transition-colors hover:bg-slate-50"
            >
              <ArrowLeft className="size-4" aria-hidden="true" />
              {copy.back}
            </button>
            <button
              type="button"
              onClick={() => handleLanguageChange(language === 'ja' ? 'en' : 'ja')}
              className="inline-flex min-h-11 items-center gap-2 rounded-full bg-slate-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-slate-800"
            >
              <Languages className="size-4" aria-hidden="true" />
              {copy.toggle}
            </button>
          </div>
        </header>

        <div className="grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
          <section className="space-y-4">
            <div
              className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm"
              data-testid="customer-guide-avatar-stage"
            >
              <div className="h-[280px] sm:h-[340px]">
                <CharacterAvatar
                  modelPath="/characters/models/sakura.vrm"
                  sessionState="speaking"
                  enableClickAnimation={false}
                  showControls={false}
                  onVisemeControl={(callback) => {
                    setSetViseme(() => callback);
                  }}
                  onExpressionControl={(callback) => {
                    setSetExpression(() => callback);
                  }}
                />
              </div>
            </div>

            <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="text-balance text-xl font-semibold text-slate-950">{copy.agendaTitle}</h2>
              <div className="mt-4 grid gap-2">
                {copy.agenda.map((item, index) => (
                  <div
                    key={item}
                    className="rounded-2xl bg-slate-100 px-4 py-3 text-sm font-medium text-slate-800"
                  >
                    {index + 1}. {item}
                  </div>
                ))}
              </div>
            </section>
          </section>

          <section className="min-h-[560px] overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
            <MarpViewer
              language={language}
              autoPlay={autoPlay}
              surface="customer"
              onVisemeControl={setViseme}
              onExpressionControl={setExpression}
            />
          </section>
        </div>
      </div>
    </main>
  );
}
