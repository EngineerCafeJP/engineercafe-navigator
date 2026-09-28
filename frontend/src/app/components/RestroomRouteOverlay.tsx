'use client';

import { X } from 'lucide-react';
import type { overlayLabels } from '@/lib/kiosk-labels';

export function RestroomRouteOverlay({
  visible,
  language = 'ja',
  onClose,
  bumpUserActivity,
}: {
  visible: boolean;
  language?: 'ja' | 'en' | 'zh' | 'ko' | string;
  onClose: () => void;
  bumpUserActivity?: () => void;
}) {
  if (!visible) return null;

  const labels: Record<string, { title: string; step1: string; step2: string; step3: string; close: string }> = {
    ja: {
      title: 'トイレへの道順',
      step1: '1. 受付の後ろの通路を進みます',
      step2: '2. 1Fのテラスを横切ります',
      step3: '3. 突き当たりまで進むとトイレがあります',
      close: '閉じる',
    },
    en: {
      title: 'Route to Restroom',
      step1: '1. Go through the passage behind the reception desk',
      step2: '2. Cross the 1F terrace',
      step3: '3. Continue to the far end',
      close: 'Close',
    },
    zh: {
      title: '洗手間路線',
      step1: '1. 穿過接待台後面的通道',
      step2: '2. 穿過1樓露台',
      step3: '3. 繼續走到盡頭',
      close: '關閉',
    },
    ko: {
      title: '화장실 가는 길',
      step1: '1. 리셉션 데스크 뒤의 통로로 이동합니다',
      step2: '2. 1층 테라스를 건넙니다',
      step3: '3. 끝까지 계속 가십시오',
      close: '닫기',
    }
  };

  const text = labels[language] || labels['ja'];

  return (
    <div
      data-testid="restroom-route-overlay"
      className="absolute inset-0 z-40 grid min-h-0 place-items-center overflow-y-auto bg-black/60 p-4"
      style={{
        paddingTop: 'max(1rem, env(safe-area-inset-top))',
        paddingRight: 'max(1rem, env(safe-area-inset-right))',
        paddingBottom: 'max(1rem, env(safe-area-inset-bottom))',
        paddingLeft: 'max(1rem, env(safe-area-inset-left))',
      }}
      onPointerDownCapture={bumpUserActivity}
    >
      <div className="relative mx-auto max-h-full w-full max-w-4xl overflow-y-auto rounded-[28px] border border-white/15 bg-white/95 p-6 shadow-xl md:p-10">
        <button
          type="button"
          onClick={onClose}
          className="absolute top-4 right-4 rounded-full p-2 text-slate-500 transition-colors hover:bg-slate-100"
          aria-label={text.close}
        >
          <X className="h-6 w-6" />
        </button>
        
        <h3 className="mb-8 text-center text-2xl font-bold text-slate-900">
          {text.title}
        </h3>

        <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
          <div className="flex flex-col items-center gap-3">
            <div className="flex aspect-[4/3] w-full items-center justify-center rounded-xl bg-slate-200 shadow-inner">
              <span className="text-slate-500">Photo 1 (TODO)</span>
            </div>
            <p className="text-center font-medium text-slate-800">{text.step1}</p>
          </div>
          
          <div className="flex flex-col items-center gap-3">
            <div className="flex aspect-[4/3] w-full items-center justify-center rounded-xl bg-slate-200 shadow-inner">
              <span className="text-slate-500">Photo 2 (TODO)</span>
            </div>
            <p className="text-center font-medium text-slate-800">{text.step2}</p>
          </div>

          <div className="flex flex-col items-center gap-3">
            <div className="flex aspect-[4/3] w-full items-center justify-center rounded-xl bg-slate-200 shadow-inner">
              <span className="text-slate-500">Photo 3 (TODO)</span>
            </div>
            <p className="text-center font-medium text-slate-800">{text.step3}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
