import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { NextRequest } from 'next/server';

const originalBackendApiUrl = process.env.BACKEND_API_URL;
const originalBackendApiKey = process.env.BACKEND_API_KEY;
const originalNodeEnv = process.env.NODE_ENV;
const originalFetch = global.fetch;

afterEach(() => {
  process.env.BACKEND_API_URL = originalBackendApiUrl;
  process.env.BACKEND_API_KEY = originalBackendApiKey;
  (process.env as Record<string, string | undefined>).NODE_ENV = originalNodeEnv;
  global.fetch = originalFetch;
});

function setBackendProxyEnv() {
  process.env.BACKEND_API_URL = 'https://backend.example.com';
  process.env.BACKEND_API_KEY = 'test-backend-key';
  (process.env as Record<string, string | undefined>).NODE_ENV = 'test';
}

test(
  'voice telemetry POST proxies payload to backend telemetry endpoint',
  { concurrency: false },
  async () => {
    setBackendProxyEnv();
    let capturedUrl: string | undefined;
    let capturedInit: RequestInit | undefined;

    global.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      capturedUrl = typeof input === 'string' ? input : input.toString();
      capturedInit = init;

      return new Response(JSON.stringify({ success: true }), {
        status: 202,
        headers: { 'Content-Type': 'application/json' },
      });
    }) as typeof fetch;

    const { POST } = await import('../app/api/telemetry/voice/route');
    const response = await POST(
      new NextRequest('https://example.com/api/telemetry/voice', {
        method: 'POST',
        body: JSON.stringify({
          event: 'voice_turn_timing',
          phase: 'stt',
          sessionId: 'session-1',
          sttMs: 42,
        }),
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { success: true });
    assert.equal(capturedUrl, 'https://backend.example.com/api/telemetry/voice');
    assert.equal(capturedInit?.method, 'POST');
    const headers = new Headers(capturedInit?.headers);
    assert.equal(headers.get('Content-Type'), 'application/json');
    assert.equal(headers.get('X-API-Key'), 'test-backend-key');
    assert.deepEqual(JSON.parse(capturedInit?.body as string), {
      event: 'voice_turn_timing',
      phase: 'stt',
      sessionId: 'session-1',
      sttMs: 42,
    });
  },
);

test(
  'voice telemetry POST rejects non-object JSON bodies',
  { concurrency: false },
  async () => {
    setBackendProxyEnv();
    let fetchCalled = false;
    global.fetch = (async () => {
      fetchCalled = true;
      return new Response(JSON.stringify({ success: true }));
    }) as typeof fetch;

    const { POST } = await import('../app/api/telemetry/voice/route');
    const response = await POST(
      new NextRequest('https://example.com/api/telemetry/voice', {
        method: 'POST',
        body: JSON.stringify(['voice_turn_timing']),
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    assert.equal(response.status, 400);
    assert.deepEqual(await response.json(), { error: 'INVALID_REQUEST' });
    assert.equal(fetchCalled, false);
  },
);

test(
  'voice telemetry POST remains best-effort when backend returns an error',
  { concurrency: false },
  async () => {
    setBackendProxyEnv();
    global.fetch = (async () =>
      new Response(JSON.stringify({ detail: 'telemetry unavailable' }), {
        status: 503,
        headers: { 'Content-Type': 'application/json' },
      })) as typeof fetch;

    const { POST } = await import('../app/api/telemetry/voice/route');
    const response = await POST(
      new NextRequest('https://example.com/api/telemetry/voice', {
        method: 'POST',
        body: JSON.stringify({ event: 'audio_playback_failed' }),
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    assert.equal(response.status, 202);
    assert.deepEqual(await response.json(), { success: true, proxied: false });
  },
);
