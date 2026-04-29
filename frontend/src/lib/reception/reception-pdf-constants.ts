/**
 * Static reception slide deck shipped under public/reception/.
 * Add per-page audio optional: {prefix}/{01,02,...}.mp3 and lipsync JSON alongside.
 */
export const RECEPTION_GUIDE_PDFS = {
  ja: '/reception/engineer-cafe-ja.pdf',
  en: '/reception/engineer-cafe-en.pdf',
} as const;

/** @deprecated use RECEPTION_GUIDE_PDFS.ja */
export const RECEPTION_GUIDE_PDF_JA = RECEPTION_GUIDE_PDFS.ja;

export const RECEPTION_GUIDE_AUDIO_EXT = 'mp3';

export function receptionGuidePdfUrl(language: 'ja' | 'en'): string {
  return RECEPTION_GUIDE_PDFS[language];
}

export function receptionGuideAudioPrefix(language: 'ja' | 'en'): string {
  return `/reception/audio/${language}`;
}

export function receptionGuideLipsyncPrefix(language: 'ja' | 'en'): string {
  return `/reception/lipsync/${language}`;
}

/** @deprecated use receptionGuideAudioPrefix('ja') */
export const RECEPTION_GUIDE_AUDIO_PREFIX_JA = receptionGuideAudioPrefix('ja');
/** @deprecated use receptionGuideLipsyncPrefix('ja') */
export const RECEPTION_GUIDE_LIPSYNC_PREFIX_JA = receptionGuideLipsyncPrefix('ja');

export function receptionGuidePageStem(page: number): string {
  return String(page).padStart(2, '0');
}
