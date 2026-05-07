import { test } from 'node:test';
import assert from 'node:assert/strict';

import { resolveVoiceResponseLanguage } from '@/lib/voice/response-language';

test('uses chat response_language for TTS when it differs from kiosk language', () => {
  assert.equal(resolveVoiceResponseLanguage({ response_language: 'en' }, 'ja'), 'en');
});

test('falls back to metadata language and normalizes locale tags', () => {
  assert.equal(resolveVoiceResponseLanguage({ language: 'en-US' }, 'ja'), 'en');
});

test('keeps the kiosk language when metadata is absent or unsupported by the voice UI', () => {
  assert.equal(resolveVoiceResponseLanguage(null, 'ja'), 'ja');
  assert.equal(resolveVoiceResponseLanguage({ response_language: 'ko' }, 'en'), 'en');
});
