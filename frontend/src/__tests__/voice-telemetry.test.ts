import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';

import { sendVoiceTelemetry } from '../lib/telemetry/voice-telemetry';

const originalFetch = globalThis.fetch;
const originalNavigatorDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'navigator');

function restoreNavigator(): void {
  if (originalNavigatorDescriptor) {
    Object.defineProperty(globalThis, 'navigator', originalNavigatorDescriptor);
    return;
  }

  Reflect.deleteProperty(globalThis, 'navigator');
}

afterEach(() => {
  globalThis.fetch = originalFetch;
  restoreNavigator();
});

test('sendVoiceTelemetry posts with sendBeacon when available', async () => {
  let capturedUrl: string | URL | null = null;
  let capturedData: BodyInit | null = null;
  let fetchCalls = 0;

  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    value: {
      userAgent: 'node-test',
      sendBeacon: (url: string | URL, data?: BodyInit | null): boolean => {
        capturedUrl = url;
        capturedData = data ?? null;
        return true;
      },
    },
  });
  globalThis.fetch = (async () => {
    fetchCalls += 1;
    return new Response('{}');
  }) as typeof fetch;

  const transport = await sendVoiceTelemetry('voice_state_transition', {
    from: 'listening',
    to: 'processing',
  });

  assert.equal(transport, 'sendBeacon');
  assert.equal(capturedUrl, '/api/telemetry/voice');
  assert.equal(fetchCalls, 0);
  assert.ok((capturedData as unknown) instanceof Blob);

  const payload = JSON.parse(
    await (capturedData as unknown as Blob).text(),
  ) as Record<string, unknown>;
  assert.equal(payload.event, 'voice_state_transition');
  assert.equal(payload.from, 'listening');
  assert.equal(payload.to, 'processing');
  assert.equal(payload.userAgent, 'node-test');
  assert.equal(typeof payload.timestamp, 'string');
});

test('sendVoiceTelemetry falls back to fetch keepalive when sendBeacon returns false', async () => {
  let capturedUrl: string | URL | Request | null = null;
  let capturedInit: RequestInit | undefined;

  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    value: {
      userAgent: 'node-test',
      sendBeacon: (): boolean => false,
    },
  });
  globalThis.fetch = (async (input, init) => {
    capturedUrl = input;
    capturedInit = init;
    return new Response(JSON.stringify({ success: true }), { status: 200 });
  }) as typeof fetch;

  const transport = await sendVoiceTelemetry('audio_playback_failed', {
    method: 'web-audio',
    errorType: 'playback_failed',
  });

  assert.equal(transport, 'fetch');
  assert.equal(capturedUrl, '/api/telemetry/voice');
  assert.equal(capturedInit?.method, 'POST');
  assert.equal(capturedInit?.keepalive, true);
  assert.equal(new Headers(capturedInit?.headers).get('Content-Type'), 'application/json');

  const payload = JSON.parse(capturedInit?.body as string) as Record<string, unknown>;
  assert.equal(payload.event, 'audio_playback_failed');
  assert.equal(payload.method, 'web-audio');
  assert.equal(payload.errorType, 'playback_failed');
});
