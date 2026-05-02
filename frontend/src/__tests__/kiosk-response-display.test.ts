import assert from 'node:assert/strict';
import { test } from 'node:test';
import { getKioskResponseDisplayState } from '@/lib/kiosk-response-display';

test('shows the default prompt instead of a stale response when returning to idle', () => {
  const now = 10_000;

  const result = getKioskResponseDisplayState({
    response: 'Thanks for visiting.',
    sessionState: 'idle',
    responseVisibleUntil: now - 1,
    defaultPromptVisibleUntil: now + 5_000,
    now,
    defaultPrompt: 'Ask a question to get started.',
  });

  assert.deepEqual(result, {
    text: 'Ask a question to get started.',
    showBubble: true,
    isLiveResponse: false,
  });
});

test('keeps showing the response while its visibility window is still active', () => {
  const now = 10_000;

  const result = getKioskResponseDisplayState({
    response: 'Thanks for visiting.',
    sessionState: 'idle',
    responseVisibleUntil: now + 5_000,
    defaultPromptVisibleUntil: now + 5_000,
    now,
    defaultPrompt: 'Ask a question to get started.',
  });

  assert.deepEqual(result, {
    text: 'Thanks for visiting.',
    showBubble: true,
    isLiveResponse: true,
  });
});

test('shows the response while playback is pending', () => {
  const now = 10_000;

  const result = getKioskResponseDisplayState({
    response: 'Thanks for visiting.',
    sessionState: 'processing',
    responseVisibleUntil: now - 1,
    responsePendingPlayback: true,
    defaultPromptVisibleUntil: now + 5_000,
    now,
    defaultPrompt: 'Ask a question to get started.',
  });

  assert.deepEqual(result, {
    text: 'Thanks for visiting.',
    showBubble: true,
    isLiveResponse: true,
  });
});

test('shows the response while processing continues before playback starts', () => {
  const now = 10_000;

  const result = getKioskResponseDisplayState({
    response: 'Thanks for visiting.',
    sessionState: 'processing',
    responseVisibleUntil: now - 1,
    defaultPromptVisibleUntil: now + 5_000,
    now,
    defaultPrompt: 'Ask a question to get started.',
  });

  assert.deepEqual(result, {
    text: 'Thanks for visiting.',
    showBubble: true,
    isLiveResponse: true,
  });
});

test('hides the bubble when neither a live response nor the default prompt should be visible', () => {
  const now = 10_000;

  const result = getKioskResponseDisplayState({
    response: '',
    sessionState: 'idle',
    responseVisibleUntil: now - 1,
    defaultPromptVisibleUntil: now - 1,
    now,
    defaultPrompt: 'Ask a question to get started.',
  });

  assert.deepEqual(result, {
    text: '',
    showBubble: false,
    isLiveResponse: false,
  });
});
