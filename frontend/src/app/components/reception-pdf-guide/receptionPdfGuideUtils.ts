import {
  RECEPTION_GUIDE_AUDIO_EXT,
  receptionGuideAudioPrefix,
  receptionGuidePageStem,
} from '@/lib/reception/reception-pdf-constants';

type Language = 'ja' | 'en';

export function toSameOriginUrl(path: string): string {
  if (typeof window === 'undefined') {
    return path;
  }
  return new URL(path, window.location.origin).toString();
}

export function receptionPageAudioUrl(language: Language, page: number): string {
  const audioPrefix = receptionGuideAudioPrefix(language);
  const stem = receptionGuidePageStem(page);
  return toSameOriginUrl(`${audioPrefix}/${stem}.${RECEPTION_GUIDE_AUDIO_EXT}`);
}
