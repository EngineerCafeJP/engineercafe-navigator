import assert from 'node:assert/strict';
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { afterEach, test } from 'node:test';
import { NextRequest } from 'next/server';

const originalCwd = process.cwd();
const originalBackendApiUrl = process.env.BACKEND_API_URL;
const originalBackendApiKey = process.env.BACKEND_API_KEY;
const originalFetch = global.fetch;
let tempDir: string | null = null;

process.env.BACKEND_API_URL = originalBackendApiUrl ?? 'https://backend.example.com';

afterEach(async () => {
  process.chdir(originalCwd);
  process.env.BACKEND_API_URL = originalBackendApiUrl ?? 'https://backend.example.com';
  process.env.BACKEND_API_KEY = originalBackendApiKey;
  global.fetch = originalFetch;

  if (tempDir) {
    await rm(tempDir, { recursive: true, force: true });
    tempDir = null;
  }
});

test('returns supported feature arrays when manifest is missing', async () => {
  const { GET } = await import('../app/api/character/route');
  const response = await GET(
    new NextRequest('https://example.com/api/character?action=supported_features')
  );

  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), {
    success: true,
    expressions: ['neutral', 'happy', 'sad', 'angry', 'relaxed', 'surprised'],
    animations: ['idle', 'bowing', 'greeting', 'looking', 'talking', 'thinking'],
  });
});

test('returns manifest animations when a character animation manifest exists', async () => {
  tempDir = await mkdtemp(path.join(os.tmpdir(), 'character-route-'));
  await mkdir(path.join(tempDir, 'public', 'characters', 'animations'), { recursive: true });
  await writeFile(
    path.join(tempDir, 'public', 'characters', 'animations', 'manifest.json'),
    JSON.stringify({
      animations: ['wave', 'bow'],
    })
  );

  process.chdir(tempDir);

  const { GET } = await import('../app/api/character/route');
  const response = await GET(
    new NextRequest('https://example.com/api/character?action=supported_features')
  );

  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), {
    success: true,
    expressions: ['neutral', 'happy', 'sad', 'angry', 'relaxed', 'surprised'],
    animations: ['wave', 'bow'],
  });
});

test('keeps the default GET health payload for other actions', async () => {
  const { GET } = await import('../app/api/character/route');
  const response = await GET(
    new NextRequest('https://example.com/api/character?action=current_state')
  );

  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), {
    status: 'ok',
  });
});

test(
  'POST action auto forwards to backend character auto endpoint without action field',
  { concurrency: false },
  async () => {
    process.env.BACKEND_API_URL = 'https://backend.example.com';
    process.env.BACKEND_API_KEY = 'k';

    let requestUrl = '';
    let postedBody = '';
    global.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      requestUrl = String(input);
      postedBody = String(init?.body ?? '');
      return new Response(
        JSON.stringify({
          success: true,
          vrmControl: { name: 'thinking', duration: 800, keyframes: [] },
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }) as typeof fetch;

    const { POST } = await import('../app/api/character/route');
    const response = await POST(
      new NextRequest('https://example.com/api/character', {
        method: 'POST',
        body: JSON.stringify({
          action: 'auto',
          cleanText: 'こんにちは',
          emotion: 'happy',
        }),
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    assert.equal(response.status, 200);
    assert.equal(requestUrl, 'https://backend.example.com/api/character/auto');
    assert.deepEqual(JSON.parse(postedBody), {
      cleanText: 'こんにちは',
      emotion: 'happy',
    });
    assert.deepEqual(await response.json(), {
      success: true,
      vrmControl: { name: 'thinking', duration: 800, keyframes: [] },
    });
  },
);

test('POST with an empty body forwards to the default backend character endpoint', async () => {
  process.env.BACKEND_API_URL = 'https://backend.example.com';
  process.env.BACKEND_API_KEY = 'k';

  let requestUrl = '';
  let postedBody = '';
  global.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    requestUrl = String(input);
    postedBody = String(init?.body ?? '');
    return new Response(JSON.stringify({ success: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }) as typeof fetch;

  const { POST } = await import('../app/api/character/route');
  const response = await POST(
    new NextRequest('https://example.com/api/character', {
      method: 'POST',
    }),
  );

  assert.equal(response.status, 200);
  assert.equal(requestUrl, 'https://backend.example.com/api/character');
  assert.deepEqual(JSON.parse(postedBody), {});
  assert.deepEqual(await response.json(), { success: true });
});
