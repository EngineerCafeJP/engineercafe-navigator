import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';

import { getQaApiMode, submitQaQuestion } from '../lib/api/qa-client';

const originalBackendApiUrl = process.env.NEXT_PUBLIC_BACKEND_API_URL;
const originalQaApiMode = process.env.NEXT_PUBLIC_QA_API_MODE;
const originalFetch = global.fetch;

function restoreEnv(key: string, value: string | undefined): void {
  if (value === undefined) {
    delete process.env[key];
    return;
  }

  process.env[key] = value;
}

afterEach(() => {
  restoreEnv('NEXT_PUBLIC_BACKEND_API_URL', originalBackendApiUrl);
  restoreEnv('NEXT_PUBLIC_QA_API_MODE', originalQaApiMode);
  global.fetch = originalFetch;
});

function qaRequest() {
  return {
    question: '営業時間は？',
    text: '営業時間は？',
    sessionId: 'session-123',
    language: 'ja' as const,
    visitorId: 'visitor-456',
  };
}

test('QA client uses the Next proxy by default', { concurrency: false }, async () => {
  process.env.NEXT_PUBLIC_BACKEND_API_URL = 'https://backend.example.com';
  delete process.env.NEXT_PUBLIC_QA_API_MODE;

  let capturedUrl: string | URL | Request | undefined;
  let capturedBody: Record<string, unknown> | null = null;
  global.fetch = (async (input, init) => {
    capturedUrl = input;
    capturedBody =
      typeof init?.body === 'string' ? (JSON.parse(init.body) as Record<string, unknown>) : null;

    return new Response(
      JSON.stringify({
        success: true,
        answer: '10時から22時です',
        metadata: { agent: 'business_info' },
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    );
  }) as typeof fetch;

  assert.equal(getQaApiMode(), 'proxy');

  const result = await submitQaQuestion(qaRequest());

  assert.equal(capturedUrl, '/api/qa');
  assert.deepEqual(capturedBody, {
    action: 'ask',
    question: '営業時間は？',
    text: '営業時間は？',
    sessionId: 'session-123',
    language: 'ja',
    visitorId: 'visitor-456',
  });
  assert.equal(result.mode, 'proxy');
  assert.equal(result.usedProxyFallback, false);
  assert.equal(result.data.success, true);
  assert.equal(result.data.answer, '10時から22時です');
});

test('QA client direct mode calls backend /api/chat without exposing a browser API key', {
  concurrency: false,
}, async () => {
  process.env.NEXT_PUBLIC_BACKEND_API_URL = 'https://backend.example.com/';
  process.env.NEXT_PUBLIC_QA_API_MODE = 'direct';

  let capturedUrl: string | URL | Request | undefined;
  let capturedHeaders: Headers;
  let capturedBody: Record<string, unknown> | null = null;
  global.fetch = (async (input, init) => {
    capturedUrl = input;
    capturedHeaders = new Headers(init?.headers);
    capturedBody =
      typeof init?.body === 'string' ? (JSON.parse(init.body) as Record<string, unknown>) : null;

    return new Response(
      JSON.stringify({
        answer: '10時から22時です',
        emotion: 'happy',
        metadata: { agent: 'business_info', vrm_control: { name: 'nod' } },
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    );
  }) as typeof fetch;

  assert.equal(getQaApiMode(), 'direct');

  const result = await submitQaQuestion(qaRequest());

  assert.equal(capturedUrl, 'https://backend.example.com/api/chat');
  assert.deepEqual(capturedBody, {
    query: '営業時間は？',
    session_id: 'session-123',
    language: 'ja',
    visitor_id: 'visitor-456',
  });
  assert.equal(capturedHeaders!.get('Content-Type'), 'application/json');
  assert.equal(capturedHeaders!.has('X-API-Key'), false);
  assert.equal(capturedHeaders!.has('Authorization'), false);
  assert.equal(result.mode, 'direct');
  assert.equal(result.usedProxyFallback, false);
  assert.equal(result.data.success, true);
  assert.equal(result.data.vrm_control, result.data.metadata?.vrm_control);
});

test('QA client falls back to the proxy when direct backend auth rejects the browser call', {
  concurrency: false,
}, async () => {
  process.env.NEXT_PUBLIC_BACKEND_API_URL = 'https://backend.example.com';
  process.env.NEXT_PUBLIC_QA_API_MODE = 'direct';

  const calls: Array<{ url: string | URL | Request; body: Record<string, unknown> | null }> = [];
  global.fetch = (async (input, init) => {
    calls.push({
      url: input,
      body: typeof init?.body === 'string' ? (JSON.parse(init.body) as Record<string, unknown>) : null,
    });

    if (calls.length === 1) {
      return new Response(JSON.stringify({ detail: 'Forbidden' }), {
        status: 403,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    return new Response(JSON.stringify({ success: true, answer: 'Proxy answer' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }) as typeof fetch;

  const result = await submitQaQuestion(qaRequest());

  assert.equal(calls.length, 2);
  assert.equal(calls[0]?.url, 'https://backend.example.com/api/chat');
  assert.equal(calls[1]?.url, '/api/qa');
  assert.equal(result.mode, 'proxy');
  assert.equal(result.usedProxyFallback, true);
  assert.equal(result.data.answer, 'Proxy answer');
});

test('QA client proxy mode is an explicit rollback even when backend URL exists', {
  concurrency: false,
}, async () => {
  process.env.NEXT_PUBLIC_BACKEND_API_URL = 'https://backend.example.com';
  process.env.NEXT_PUBLIC_QA_API_MODE = 'proxy';

  let capturedUrl: string | URL | Request | undefined;
  global.fetch = (async (input) => {
    capturedUrl = input;
    return new Response(JSON.stringify({ success: true, answer: 'Proxy answer' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }) as typeof fetch;

  const result = await submitQaQuestion(qaRequest());

  assert.equal(getQaApiMode(), 'proxy');
  assert.equal(capturedUrl, '/api/qa');
  assert.equal(result.mode, 'proxy');
  assert.equal(result.usedProxyFallback, false);
});

test('QA client keeps one proxy sessionId for sequential cafe follow-up questions', {
  concurrency: false,
}, async () => {
  process.env.NEXT_PUBLIC_BACKEND_API_URL = 'https://backend.example.com';
  process.env.NEXT_PUBLIC_QA_API_MODE = 'proxy';

  const questions = ['エンジニアカフェの営業時間', '隣のカフェは？'];
  const bodies: Record<string, unknown>[] = [];
  global.fetch = (async (_input, init) => {
    if (typeof init?.body === 'string') {
      bodies.push(JSON.parse(init.body) as Record<string, unknown>);
    }

    return new Response(JSON.stringify({ success: true, answer: 'Proxy answer' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }) as typeof fetch;

  for (const question of questions) {
    const result = await submitQaQuestion({
      ...qaRequest(),
      question,
      text: question,
      sessionId: 'session-801',
    });
    assert.equal(result.mode, 'proxy');
    assert.equal(result.data.success, true);
  }

  assert.equal(bodies.length, 2);
  assert.deepEqual(
    bodies.map((body) => body.question),
    questions,
  );
  assert.deepEqual(
    bodies.map((body) => body.text),
    questions,
  );
  assert.deepEqual(
    bodies.map((body) => body.sessionId),
    ['session-801', 'session-801'],
  );
  assert.deepEqual(
    bodies.map((body) => body.language),
    ['ja', 'ja'],
  );
  assert.equal(bodies.some((body) => 'session_id' in body), false);
  assert.equal(bodies.some((body) => 'history' in body || 'messages' in body), false);
});

test('QA client keeps one direct session_id for sequential cafe follow-up questions', {
  concurrency: false,
}, async () => {
  process.env.NEXT_PUBLIC_BACKEND_API_URL = 'https://backend.example.com';
  process.env.NEXT_PUBLIC_QA_API_MODE = 'direct';

  const questions = ['エンジニアカフェの営業時間', '隣のカフェは？'];
  const calls: Array<{ url: string | URL | Request; body: Record<string, unknown> }> = [];
  global.fetch = (async (input, init) => {
    if (typeof init?.body === 'string') {
      calls.push({
        url: input,
        body: JSON.parse(init.body) as Record<string, unknown>,
      });
    }

    return new Response(JSON.stringify({ answer: 'Direct answer', metadata: {} }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }) as typeof fetch;

  for (const question of questions) {
    const result = await submitQaQuestion({
      ...qaRequest(),
      question,
      text: question,
      sessionId: 'session-801',
    });
    assert.equal(result.mode, 'direct');
    assert.equal(result.data.success, true);
  }

  assert.equal(calls.length, 2);
  assert.deepEqual(
    calls.map((call) => call.url),
    ['https://backend.example.com/api/chat', 'https://backend.example.com/api/chat'],
  );
  assert.deepEqual(
    calls.map((call) => call.body.query),
    questions,
  );
  assert.deepEqual(
    calls.map((call) => call.body.session_id),
    ['session-801', 'session-801'],
  );
  assert.deepEqual(
    calls.map((call) => call.body.language),
    ['ja', 'ja'],
  );
  assert.equal(calls.some((call) => 'sessionId' in call.body), false);
  assert.equal(calls.some((call) => 'history' in call.body || 'messages' in call.body), false);
});
