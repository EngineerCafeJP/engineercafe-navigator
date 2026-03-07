'use client';

import { Presentation, Play, X } from 'lucide-react';
import { useCallback, useState } from 'react';
import { BackgroundOption } from './components/BackgroundSelector';
import CharacterAvatar from './components/CharacterAvatar';
import MarpViewer from './components/MarpViewer';
import VoiceConversationShell from './components/VoiceConversationShell';

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
    <main className="min-h-dvh bg-slate-100">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-4 py-4 md:px-6 md:py-6">
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1.3fr)_minmax(320px,0.9fr)]">
          <VoiceConversationShell
            language={currentLanguage}
            onLanguageChange={setCurrentLanguage}
            onVisemeControl={setVisemeFunction}
            renderAvatar={({ sessionState }) => (
              <CharacterAvatar
                modelPath="/characters/models/sakura.vrm"
                sessionState={sessionState}
                background={characterBackground}
                lightingIntensity={lightingIntensity}
                enableClickAnimation={!showSlideMode}
                onVisemeControl={(setViseme) => {
                  setSetVisemeFunction(() => setViseme);
                }}
                onExpressionControl={(setExpression) => {
                  setSetExpressionFunction(() => setExpression);
                }}
                onBackgroundChange={setCharacterBackground}
                onLightingChange={setLightingIntensity}
              />
            )}
          />

          <section className="rounded-[28px] border border-slate-200 bg-white/90 p-4 shadow-sm backdrop-blur-sm md:p-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="text-sm font-medium text-slate-500">Presentation</p>
                <h2 className="text-balance text-2xl font-semibold text-slate-950">
                  {currentLanguage === 'ja' ? 'スライド案内' : 'Presentation Guide'}
                </h2>
                <p className="mt-2 text-pretty text-sm leading-6 text-slate-600">
                  {currentLanguage === 'ja'
                    ? '初めての方向けの案内をスライドで再生できます。'
                    : 'You can start the introductory slide deck for first-time visitors.'}
                </p>
              </div>

              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => startPresentation('ja')}
                  className="inline-flex items-center gap-2 rounded-full bg-slate-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-slate-800"
                >
                  <Play className="size-4" />
                  日本語で開始
                </button>
                <button
                  type="button"
                  onClick={() => startPresentation('en')}
                  className="inline-flex items-center gap-2 rounded-full bg-slate-200 px-4 py-2 text-sm font-medium text-slate-800 transition-colors hover:bg-slate-300"
                >
                  <Presentation className="size-4" />
                  Start in English
                </button>
                {showSlideMode ? (
                  <button
                    type="button"
                    onClick={() => setShowSlideMode(false)}
                    className="inline-flex items-center gap-2 rounded-full border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50"
                  >
                    <X className="size-4" />
                    {currentLanguage === 'ja' ? '閉じる' : 'Close'}
                  </button>
                ) : null}
              </div>
            </div>

            <div className="mt-5 overflow-hidden rounded-[24px] border border-slate-200 bg-slate-50">
              {showSlideMode ? (
                <div className="h-[560px]">
                  <MarpViewer
                    language={currentLanguage}
                    onVisemeControl={setVisemeFunction}
                    onExpressionControl={setExpressionFunction}
                  />
                </div>
              ) : (
                <div className="flex min-h-[560px] items-center justify-center px-8 text-center">
                  <div className="max-w-sm">
                    <div className="mx-auto flex size-16 items-center justify-center rounded-full bg-slate-900 text-white">
                      <Presentation className="size-7" />
                    </div>
                    <h3 className="mt-5 text-balance text-xl font-semibold text-slate-900">
                      {currentLanguage === 'ja'
                        ? 'プレゼンテーションは必要なときだけ起動'
                        : 'Start the presentation only when needed'}
                    </h3>
                    <p className="mt-3 text-pretty text-sm leading-6 text-slate-600">
                      {currentLanguage === 'ja'
                        ? '音声で案内しながら、必要なら右上のボタンからスライド説明へ切り替えられます。'
                        : 'Stay in voice mode by default, then switch to slides from the buttons above when you need the guided tour.'}
                    </p>
                  </div>
                </div>
              )}
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}
