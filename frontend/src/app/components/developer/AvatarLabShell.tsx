'use client';

import Link from 'next/link';
import { ArrowRight, FlaskConical } from 'lucide-react';

import CharacterAvatar from '@/app/components/CharacterAvatar';
import ReceptionPdfGuide from '@/app/components/ReceptionPdfGuide';

export default function AvatarLabShell() {
  return (
    <main className="min-h-dvh bg-slate-100 px-4 py-4 md:px-6 md:py-6" data-testid="avatar-lab-shell">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-4">
        <header className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-3xl">
              <p className="text-xs font-semibold uppercase text-slate-500">Developer Surface</p>
              <h1 className="mt-2 text-balance text-3xl font-semibold text-slate-950">Avatar Lab</h1>
              <p className="mt-3 text-pretty text-sm leading-6 text-slate-600">
                PR #63 の設定面を visitor-facing から分離し、VRM・VRMA・背景・ライティング・音声・スライド検証を
                開発者専用にまとめた画面です。
              </p>
            </div>

            <div className="flex flex-wrap gap-2">
              <Link
                href="/"
                className="inline-flex min-h-11 items-center gap-2 rounded-full border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-900 transition-colors hover:bg-slate-50"
              >
                受付画面へ
              </Link>
              <Link
                href="/onboarding?lang=ja"
                className="inline-flex min-h-11 items-center gap-2 rounded-full bg-slate-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-slate-800"
              >
                初回登録ガイドへ
                <ArrowRight className="size-4" aria-hidden="true" />
              </Link>
            </div>
          </div>
        </header>

        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
          <section
            className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm"
            data-testid="avatar-lab-avatar-stage"
          >
            <div className="h-[420px] md:h-[560px]">
              <CharacterAvatar modelPath="/characters/models/sakura.vrm" sessionState="idle" showControls />
            </div>
          </section>

          <section className="space-y-4">
            <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex items-center gap-2">
                <FlaskConical className="size-4 text-slate-700" aria-hidden="true" />
                <h2 className="text-lg font-semibold text-slate-950">Lab Checklist</h2>
              </div>
              <div className="mt-4 grid gap-2">
                {[
                  'Controls: expression / viseme / position / VRMA',
                  'Keyframe: JSON animation playback',
                  'Background / lighting tuning',
                  'Audio mute / volume checks',
                  'PDF slide guide and static narration checks',
                ].map((item) => (
                  <div key={item} className="rounded-2xl bg-slate-100 px-4 py-3 text-sm text-slate-800">
                    {item}
                  </div>
                ))}
              </div>
            </section>

            <section
              className="min-h-[320px] overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm"
              data-testid="avatar-lab-slide-stage"
            >
              <ReceptionPdfGuide
                language="ja"
                rotateLandscapeHint="スライド確認には端末を横向きにしてください。"
                className="h-[420px]"
                sessionId="avatar-lab"
              />
            </section>
          </section>
        </div>
      </div>
    </main>
  );
}
