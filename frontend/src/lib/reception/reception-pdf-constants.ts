/**
 * Static reception slide deck shipped under public/reception/.
 * Add per-page audio optional: {prefix}/{01,02,...}.mp3 and lipsync JSON alongside.
 */
export const RECEPTION_GUIDE_PDF_JA = '/reception/engineer-cafe-ja.pdf';

export const RECEPTION_GUIDE_AUDIO_PREFIX_JA = '/reception/audio/ja';
export const RECEPTION_GUIDE_LIPSYNC_PREFIX_JA = '/reception/lipsync/ja';
export const RECEPTION_GUIDE_AUDIO_EXT = 'mp3';

export function receptionGuidePageStem(page: number): string {
  return String(page).padStart(2, '0');
}
