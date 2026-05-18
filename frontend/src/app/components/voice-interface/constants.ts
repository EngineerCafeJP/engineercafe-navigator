import type { VoiceSessionState } from './types';

export const DEFAULT_WAKE_WORDS = ['すみません', 'hello'];

export const STATUS_LABELS: Record<'ja' | 'en', Record<VoiceSessionState, string>> = {
  ja: {
    idle: '待機中',
    listening: '聞いています',
    processing: '考えています',
    speaking: '話しています',
  },
  en: {
    idle: 'Ready',
    listening: 'Listening',
    processing: 'Thinking',
    speaking: 'Speaking',
  },
};

export const LOADING_LABELS = {
  ja: {
    microphone: 'マイクに接続しています...',
    recognize: '音声を文字にしています...',
    answer: '回答を準備しています...',
    speaking: '音声を再生しています...',
  },
  en: {
    microphone: 'Connecting to the microphone...',
    recognize: 'Transcribing your speech...',
    answer: 'Preparing the answer...',
    speaking: 'Playing the response...',
  },
} as const;

export const PARALLEL_VOICE_FILLER_ENABLED =
  process.env.NEXT_PUBLIC_PARALLEL_VOICE_FILLER !== 'false';
export const AUTO_VRM_PLAYBACK_WAIT_MS = 180;
export const FALLBACK_NOTICE_LIMIT_PER_SESSION = 2;
export const FALLBACK_NOTICE_TEXT: Record<'ja' | 'en', string> = {
  ja: '音声の再生に失敗しました。もう一度お試しください。',
  en: 'Audio playback failed. Please try again.',
};
