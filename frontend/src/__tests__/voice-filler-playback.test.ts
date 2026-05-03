import assert from 'node:assert/strict';
import { test } from 'node:test';

import { createVoiceFillerPlaybackGate } from '../lib/voice-filler-playback';

test('voice filler gate accepts non-empty audio while turn is active', () => {
  const gate = createVoiceFillerPlaybackGate({ aborted: false });

  assert.equal(gate.canEnqueue('audio-b64'), true);
  assert.equal(gate.canEnqueue(''), false);
  assert.equal(gate.canEnqueue(null), false);
});

test('voice filler gate drops late audio after assistant response is ready', () => {
  const gate = createVoiceFillerPlaybackGate({ aborted: false });

  gate.close();

  assert.equal(gate.canEnqueue('audio-b64'), false);
});

test('voice filler gate drops audio after the voice turn is aborted', () => {
  const signal = { aborted: false };
  const gate = createVoiceFillerPlaybackGate(signal);

  signal.aborted = true;

  assert.equal(gate.canEnqueue('audio-b64'), false);
});
