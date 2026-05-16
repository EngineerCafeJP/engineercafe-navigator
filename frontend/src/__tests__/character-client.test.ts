import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';

import {
  getCharacterStatus,
  getCharacterSupportedFeatures,
  requestAutoCharacterControl,
} from '../lib/api/character-client';

const originalFetch = global.fetch;

afterEach(() => {
  global.fetch = originalFetch;
});

function jsonResponse(body: Record<string, unknown>, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

test('requestAutoCharacterControl posts auto action without touching UI components', async () => {
  const controller = new AbortController();
  let capturedUrl: string | URL | Request | undefined;
  let capturedInit: RequestInit | undefined;
  let capturedBody: Record<string, unknown> | null = null;

  global.fetch = (async (input, init) => {
    capturedUrl = input;
    capturedInit = init;
    capturedBody =
      typeof init?.body === 'string' ? (JSON.parse(init.body) as Record<string, unknown>) : null;

    return jsonResponse({
      success: true,
      vrmControl: { name: 'thinking', duration: 800, keyframes: [] },
    });
  }) as typeof fetch;

  const result = await requestAutoCharacterControl(
    {
      cleanText: 'こんにちは',
      emotion: 'happy',
      ttsWavB64: 'wav-base64',
    },
    { signal: controller.signal },
  );

  assert.equal(capturedUrl, '/api/character');
  assert.equal(capturedInit?.method, 'POST');
  assert.equal(new Headers(capturedInit?.headers).get('Content-Type'), 'application/json');
  assert.equal(capturedInit?.signal, controller.signal);
  assert.deepEqual(capturedBody, {
    action: 'auto',
    cleanText: 'こんにちは',
    emotion: 'happy',
    ttsWavB64: 'wav-base64',
  });
  assert.equal(result.ok, true);
  assert.equal(result.status, 200);
  assert.equal(result.data.success, true);
  assert.deepEqual(result.data.vrmControl, {
    name: 'thinking',
    duration: 800,
    keyframes: [],
  });
});

test('requestAutoCharacterControl defaults blank emotion to neutral and normalizes errors', async () => {
  let capturedBody: Record<string, unknown> | null = null;
  global.fetch = (async (_input, init) => {
    capturedBody =
      typeof init?.body === 'string' ? (JSON.parse(init.body) as Record<string, unknown>) : null;

    return jsonResponse({ detail: 'VRM generation timed out' }, 504);
  }) as typeof fetch;

  const result = await requestAutoCharacterControl({
    cleanText: 'こんにちは',
    emotion: '   ',
  });

  assert.deepEqual(capturedBody, {
    action: 'auto',
    cleanText: 'こんにちは',
    emotion: 'neutral',
  });
  assert.equal(result.ok, false);
  assert.equal(result.status, 504);
  assert.deepEqual(result.data, {
    success: false,
    error: 'VRM generation timed out',
  });
});

test('getCharacterSupportedFeatures reads supported feature arrays', async () => {
  const controller = new AbortController();
  let capturedUrl: string | URL | Request | undefined;
  let capturedInit: RequestInit | undefined;
  global.fetch = (async (input, init) => {
    capturedUrl = input;
    capturedInit = init;
    return jsonResponse({
      success: true,
      expressions: ['neutral', 'happy'],
      animations: ['idle', 'bowing'],
    });
  }) as typeof fetch;

  const result = await getCharacterSupportedFeatures({ signal: controller.signal });

  assert.equal(capturedUrl, '/api/character?action=supported_features');
  assert.equal(capturedInit?.signal, controller.signal);
  assert.equal(result.data.success, true);
  assert.deepEqual(result.data.expressions, ['neutral', 'happy']);
  assert.deepEqual(result.data.animations, ['idle', 'bowing']);
});

test('getCharacterSupportedFeatures returns empty arrays on invalid error bodies', async () => {
  global.fetch = (async () => new Response('bad gateway', { status: 502 })) as typeof fetch;

  const result = await getCharacterSupportedFeatures();

  assert.equal(result.ok, false);
  assert.equal(result.status, 502);
  assert.deepEqual(result.data, {
    success: false,
    error: 'キャラクター機能の取得に失敗しました',
    expressions: [],
    animations: [],
  });
});

test('getCharacterStatus normalizes the default character health response', async () => {
  global.fetch = (async (input) => {
    assert.equal(input, '/api/character');
    return jsonResponse({ status: 'ok' });
  }) as typeof fetch;

  const result = await getCharacterStatus();

  assert.equal(result.ok, true);
  assert.deepEqual(result.data, {
    success: true,
    status: 'ok',
    error: undefined,
  });
});
