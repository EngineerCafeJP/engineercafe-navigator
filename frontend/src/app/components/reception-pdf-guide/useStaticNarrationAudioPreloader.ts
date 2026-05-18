import { useEffect, useRef } from 'react';
import type { StaticNarrationAudioState } from '@/lib/reception/reception-audio-readiness';
import { receptionPageAudioUrl } from './receptionPdfGuideUtils';

type Language = 'ja' | 'en';

export function useStaticNarrationAudioPreloader(language: Language, totalPages: number) {
  const preloadedAudioRef = useRef<Map<string, HTMLAudioElement>>(new Map());
  const preloadedAudioStateRef = useRef<Map<string, StaticNarrationAudioState>>(new Map());

  useEffect(() => {
    const preloadedAudio = preloadedAudioRef.current;
    const preloadedAudioState = preloadedAudioStateRef.current;
    return () => {
      for (const audio of Array.from(preloadedAudio.values())) {
        audio.pause();
        audio.removeAttribute('src');
        audio.load();
      }
      preloadedAudio.clear();
      preloadedAudioState.clear();
    };
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined' || totalPages <= 0) {
      return;
    }

    const expected = new Set<string>();
    for (let page = 1; page <= totalPages; page += 1) {
      const audioUrl = receptionPageAudioUrl(language, page);
      expected.add(audioUrl);
      if (preloadedAudioRef.current.has(audioUrl)) {
        continue;
      }
      const audio = new Audio(audioUrl);
      audio.preload = 'auto';
      audio.setAttribute('playsinline', 'true');
      audio.setAttribute('webkit-playsinline', 'true');
      const markReady = () => {
        if (preloadedAudioRef.current.get(audioUrl) === audio) {
          preloadedAudioStateRef.current.set(audioUrl, 'ready');
        }
      };
      const markFailed = () => {
        if (preloadedAudioRef.current.get(audioUrl) === audio) {
          preloadedAudioStateRef.current.set(audioUrl, 'failed');
        }
      };
      audio.addEventListener('canplay', markReady, { once: true });
      audio.addEventListener('canplaythrough', markReady, { once: true });
      audio.addEventListener('error', markFailed, { once: true });
      preloadedAudioRef.current.set(audioUrl, audio);
      preloadedAudioStateRef.current.set(audioUrl, audio.readyState >= 3 ? 'ready' : 'pending');
      audio.load();
      if (audio.readyState >= 3) {
        preloadedAudioStateRef.current.set(audioUrl, 'ready');
      }
    }

    for (const [url, audio] of Array.from(preloadedAudioRef.current.entries())) {
      if (!expected.has(url)) {
        audio.pause();
        audio.removeAttribute('src');
        audio.load();
        preloadedAudioRef.current.delete(url);
        preloadedAudioStateRef.current.delete(url);
      }
    }
  }, [language, totalPages]);

  return preloadedAudioStateRef;
}
