import { AudioQueue } from '@/lib/audio-queue';
import { audioStateManager } from '@/lib/audio-state-manager';
import { MobileAudioService } from '@/lib/audio/mobile-audio-service';
import { VoiceRecorder } from '@/lib/voice-recorder';
import type { MutableRefObject } from 'react';
import type { VoiceSessionState } from './types';

const VISITOR_ID_STORAGE_KEY = 'engineer_cafe_visitor_id';

/** UUID v4 を生成する。crypto.randomUUID が無い環境（HTTP や古いブラウザ）用のフォールバック付き。 */
export const generateUuid = (): string => {
  if (typeof window !== 'undefined' && typeof window.crypto?.randomUUID === 'function') {
    return window.crypto.randomUUID();
  }
  if (typeof window !== 'undefined' && window.crypto?.getRandomValues) {
    const bytes = new Uint8Array(16);
    window.crypto.getRandomValues(bytes);
    bytes[6] = (bytes[6]! & 0x0f) | 0x40;
    bytes[8] = (bytes[8]! & 0x3f) | 0x80;
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }
  return `fallback-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
};

export const getOrCreateVisitorId = (): string => {
  if (typeof window === 'undefined') {
    return 'anonymous';
  }

  const existing = window.localStorage.getItem(VISITOR_ID_STORAGE_KEY);
  if (existing) {
    return existing;
  }

  const created = generateUuid();
  window.localStorage.setItem(VISITOR_ID_STORAGE_KEY, created);
  return created;
};

export const clearVisitorId = (): void => {
  if (typeof window === 'undefined') {
    return;
  }

  window.localStorage.removeItem(VISITOR_ID_STORAGE_KEY);
};

export const createSessionId = (): string => generateUuid();

export const toLocale = (language: 'ja' | 'en'): string => (language === 'ja' ? 'ja-JP' : 'en-US');

export const normalizeSessionState = (mode: string): VoiceSessionState =>
  mode === 'listening' || mode === 'processing' || mode === 'speaking' ? mode : 'idle';

export const toBase64 = async (blob: Blob): Promise<string> => {
  const arrayBuffer = await blob.arrayBuffer();
  return VoiceRecorder.arrayBufferToBase64(arrayBuffer);
};

export const elapsedMs = (startedAt: number): number => Math.max(0, Math.round(performance.now() - startedAt));

export const isAudioGestureRequiredError = (error: unknown): boolean => {
  if (
    typeof error === 'object' &&
    error !== null &&
    'requiresUserInteraction' in error &&
    error.requiresUserInteraction === true
  ) {
    return true;
  }

  if (
    typeof error === 'object' &&
    error !== null &&
    'type' in error &&
    error.type === 'user_interaction_required'
  ) {
    return true;
  }

  if (error instanceof Error) {
    const message = error.message.toLowerCase();
    return (
      error.name === 'NotAllowedError' ||
      message.includes('user interaction') ||
      message.includes('user gesture') ||
      message.includes('autoplay')
    );
  }

  return false;
};

export const stopAudioPlayback = (
  audioQueueRef: MutableRefObject<AudioQueue | null>,
  mobileAudioServiceRef: MutableRefObject<MobileAudioService | null>,
  onVisemeControl?: ((viseme: string, intensity: number) => void) | null,
) => {
  audioStateManager.stopAll();
  audioQueueRef.current?.clear();
  mobileAudioServiceRef.current?.stop();
  onVisemeControl?.('Closed', 0);
};
