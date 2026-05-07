import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  canUseStaticNarrationAudio,
  isAudioInteractionRequired,
  shouldFallbackToGeneratedNarration,
} from '../lib/reception/reception-audio-readiness';

test('static narration audio is used only after readiness is confirmed', () => {
  assert.equal(canUseStaticNarrationAudio(undefined), false);
  assert.equal(canUseStaticNarrationAudio('pending'), false);
  assert.equal(canUseStaticNarrationAudio('failed'), false);
  assert.equal(canUseStaticNarrationAudio('ready'), true);
});

test('non-permission playback failures fall back to generated narration', () => {
  assert.equal(shouldFallbackToGeneratedNarration(new Error('network error')), true);
  assert.equal(shouldFallbackToGeneratedNarration({ name: 'NotSupportedError' }), true);
});

test('permission-gated playback does not silently fall back', () => {
  assert.equal(isAudioInteractionRequired({ name: 'NotAllowedError' }), true);
  assert.equal(isAudioInteractionRequired({ requiresUserInteraction: true }), true);
  assert.equal(isAudioInteractionRequired(new Error('requires user interaction')), true);
  assert.equal(shouldFallbackToGeneratedNarration({ name: 'NotAllowedError' }), false);
});
