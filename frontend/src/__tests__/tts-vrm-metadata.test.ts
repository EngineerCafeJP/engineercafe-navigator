import assert from 'node:assert/strict';
import test from 'node:test';

import { mergePlaybackMetadataWithTtsVrmControl } from '@/lib/voice/tts-vrm-metadata';

test('replaces qa vrm_control when TTS vrmControl is present', () => {
  const result = mergePlaybackMetadataWithTtsVrmControl(
    {
      source: 'qa',
      vrm_control: { name: 'idle', duration: 1000, keyframes: [] },
    },
    {
      vrmControl: { name: 'thinking', duration: 800, keyframes: [] },
    },
  );

  assert.deepEqual(result, {
    source: 'qa',
    vrm_control: { name: 'thinking', duration: 800, keyframes: [] },
  });
});

test('accepts legacy vrm_control payloads too', () => {
  const result = mergePlaybackMetadataWithTtsVrmControl(
    {
      source: 'qa',
      vrm_control: { name: 'idle', duration: 1000, keyframes: [] },
    },
    {
      vrm_control: { name: 'thinking', duration: 800, keyframes: [] },
    },
  );

  assert.deepEqual(result, {
    source: 'qa',
    vrm_control: { name: 'thinking', duration: 800, keyframes: [] },
  });
});

test('drops stale qa vrm_control when TTS vrm payload is missing', () => {
  const result = mergePlaybackMetadataWithTtsVrmControl(
    {
      source: 'qa',
      vrm_control: { name: 'idle', duration: 1000, keyframes: [] },
    },
    {},
  );

  assert.deepEqual(result, { source: 'qa' });
});

test('returns null when stale qa vrm_control was the only metadata', () => {
  const result = mergePlaybackMetadataWithTtsVrmControl(
    {
      vrm_control: { name: 'idle', duration: 1000, keyframes: [] },
    },
    {},
  );

  assert.equal(result, null);
});
