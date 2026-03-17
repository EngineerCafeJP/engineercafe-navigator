import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { NextRequest } from 'next/server';

import {
  createBackendErrorResponse,
  createInternalServerErrorResponse,
} from '../app/api/_shared/backend-error-response';

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

function mockBackendJsonResponse(body: unknown, status: number) {
  global.fetch = (async () =>
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    })) as typeof fetch;
}

test(
  'createBackendErrorResponse maps backend detail to the standard error payload',
  { concurrency: false },
  async () => {
    const response = createBackendErrorResponse({
      status: 400,
      data: { detail: 'Unknown action: ping' },
    });

    assert.equal(response.status, 400);
    assert.deepEqual(await response.json(), { error: 'Unknown action: ping' });
  }
);

test(
  'createInternalServerErrorResponse exposes details only in development',
  { concurrency: false },
  async () => {
    (process.env as Record<string, string | undefined>).NODE_ENV = 'development';
    const response = createInternalServerErrorResponse(new Error('backend timed out'));

    assert.equal(response.status, 500);
    assert.deepEqual(await response.json(), {
      error: 'Internal server error',
      details: 'backend timed out',
    });
  }
);

test(
  'qa POST preserves backend status codes and error payloads',
  { concurrency: false },
  async () => {
    process.env.BACKEND_API_URL = 'https://backend.example.com';
    (process.env as Record<string, string | undefined>).NODE_ENV = 'test';
    mockBackendJsonResponse({ detail: 'validation failed' }, 422);

    const { POST } = await import('../app/api/qa/route');
    const response = await POST(
      new NextRequest('https://example.com/api/qa', {
        method: 'POST',
        body: JSON.stringify({ question: 'hello' }),
        headers: { 'Content-Type': 'application/json' },
      })
    );

    assert.equal(response.status, 422);
    assert.deepEqual(await response.json(), { error: 'validation failed' });
  }
);

test(
  'voice GET preserves backend 4xx responses',
  { concurrency: false },
  async () => {
    process.env.BACKEND_API_URL = 'https://backend.example.com';
    (process.env as Record<string, string | undefined>).NODE_ENV = 'test';
    mockBackendJsonResponse({ error: 'Unsupported action' }, 400);

    const { GET } = await import('../app/api/voice/route');
    const response = await GET(
      new NextRequest('https://example.com/api/voice?action=unsupported')
    );

    assert.equal(response.status, 400);
    assert.deepEqual(await response.json(), { error: 'Unsupported action' });
  }
);

test(
  'slides route no longer exports a GET handler',
  { concurrency: false },
  async () => {
    const slidesRoute = await import('../app/api/slides/route');

    assert.equal('GET' in slidesRoute, false);
  }
);
