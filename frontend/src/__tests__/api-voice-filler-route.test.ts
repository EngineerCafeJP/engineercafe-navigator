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

test(
  'voice filler POST rejects invalid body (missing language)',
  { concurrency: false },
  async () => {
    process.env.BACKEND_API_URL = 'https://backend.example.com';
    (process.env as Record<string, string | undefined>).NODE_ENV = 'test';

    const { POST } = await import('../app/api/voice/filler/route');
    const response = await POST(
      new NextRequest('https://example.com/api/voice/filler', {
        method: 'POST',
        body: JSON.stringify({ query: 'hello' }),
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    assert.equal(response.status, 400);
    const json = (await response.json()) as { error: string; details: unknown };
    assert.equal(json.error, 'INVALID_REQUEST');
    assert.ok(json.details);
  },
);

test(
  'voice filler POST forwards validated body to backend',
  { concurrency: false },
  async () => {
    process.env.BACKEND_API_URL = 'https://backend.example.com';
    process.env.BACKEND_API_KEY = 'k';
    (process.env as Record<string, string | undefined>).NODE_ENV = 'test';

    let postedBody: string | undefined;
    global.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
      postedBody = init?.body as string;
      return new Response(
        JSON.stringify({
          audioResponse: 'qqq',
          intent: 'fallback',
          audioFormat: 'audio/wav',
          fillerText: '',
          source: 'static',
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }) as typeof fetch;

    const { POST } = await import('../app/api/voice/filler/route');
    const response = await POST(
      new NextRequest('https://example.com/api/voice/filler', {
        method: 'POST',
        body: JSON.stringify({ query: '営業時間は？', language: 'ja', sessionId: 's-1' }),
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    assert.equal(response.status, 200);
    const json = (await response.json()) as { audioResponse: string; intent: string };
    assert.equal(json.intent, 'fallback');
    assert.equal(json.audioResponse, 'qqq');
    assert.ok(postedBody);
    assert.deepStrictEqual(JSON.parse(postedBody!), { query: '営業時間は？', language: 'ja' });
  },
);
