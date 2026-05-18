import { parseReceptionNarrationMarkdown } from '@/lib/reception/parse-reception-narration-md';
import { useEffect, useState } from 'react';

type Language = 'ja' | 'en';

export function useReceptionNarrationText(language: Language) {
  const [narrationTexts, setNarrationTexts] = useState<string[]>([]);
  const [isNarrationTextReady, setIsNarrationTextReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setIsNarrationTextReady(false);
    (async () => {
      const mdUrl =
        language === 'ja'
          ? '/reception/engineer-cafe-narration-ja.md'
          : '/reception/engineer-cafe-narration-en.md';
      try {
        const res = await fetch(mdUrl);
        const md = await res.text();
        const slides = parseReceptionNarrationMarkdown(md, language);
        if (!cancelled) {
          setNarrationTexts(slides);
          setIsNarrationTextReady(true);
        }
      } catch {
        if (!cancelled) {
          setNarrationTexts([]);
          setIsNarrationTextReady(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [language]);

  return {
    isNarrationTextReady,
    narrationTexts,
  };
}
