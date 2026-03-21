import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { NextRequest } from 'next/server';

const originalBackendApiUrl = process.env.BACKEND_API_URL;
const originalBackendApiKey = process.env.BACKEND_API_KEY;
const originalFetch = global.fetch;
let lastFetchRequest: { url: string; method: string } | null = null;

afterEach(() => {
  process.env.BACKEND_API_URL = originalBackendApiUrl;
  process.env.BACKEND_API_KEY = originalBackendApiKey;
  global.fetch = originalFetch;
  lastFetchRequest = null;
});

function mockBackendJsonResponse(body: unknown, status: number) {
  global.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString();
    lastFetchRequest = {
      url,
      method: init?.method ?? 'GET',
    };

    return new Response(JSON.stringify(body), {
      status,
      headers: {
        'Content-Type': 'application/json',
      },
    });
  }) as typeof fetch;
}

test(
  'calendar GET proxies to backend GET /api/calendar',
  { concurrency: false },
  async () => {
    process.env.BACKEND_API_URL = 'https://backend.example.com';
    process.env.BACKEND_API_KEY = 'test-backend-key';
    mockBackendJsonResponse(
      {
        success: true,
        data: {
          events: [{ id: 'event-1', title: 'Calendar Event' }],
        },
      },
      200
    );

    const { GET } = await import('../app/api/calendar/route');
    const response = await GET(new NextRequest('https://example.com/api/calendar'));

    assert.equal(response.status, 200);
    assert.deepEqual(lastFetchRequest, {
      url: 'https://backend.example.com/api/calendar',
      method: 'GET',
    });
    assert.deepEqual(await response.json(), {
      success: true,
      data: {
        events: [{ id: 'event-1', title: 'Calendar Event' }],
      },
    });
  }
);

test(
  'calendar GET preserves backend error responses',
  { concurrency: false },
  async () => {
    process.env.BACKEND_API_URL = 'https://backend.example.com';
    process.env.BACKEND_API_KEY = 'test-backend-key';
    mockBackendJsonResponse({ detail: 'calendar unavailable' }, 503);

    const { GET } = await import('../app/api/calendar/route');
    const response = await GET(new NextRequest('https://example.com/api/calendar'));

    assert.equal(response.status, 503);
    assert.deepEqual(lastFetchRequest, {
      url: 'https://backend.example.com/api/calendar',
      method: 'GET',
    });
    assert.deepEqual(await response.json(), { error: 'calendar unavailable' });
  }
);
