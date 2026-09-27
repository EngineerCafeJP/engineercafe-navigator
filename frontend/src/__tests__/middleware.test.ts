import assert from 'node:assert/strict';
import { afterEach, beforeEach, test } from 'node:test';
import { NextRequest } from 'next/server';

import { isMaintenanceMode, type MaintenanceModeEnv } from '../lib/maintenance-mode';
import { config, middleware } from '../middleware';

const env = process.env as Record<string, string | undefined>;
const originalAdminApiSecret = process.env.ADMIN_API_SECRET;
const originalNodeEnv = process.env.NODE_ENV;
const originalMaintenanceMode = process.env.MAINTENANCE_MODE;
const originalVercelEnv = process.env.VERCEL_ENV;

function setEnv(name: string, value: string | undefined): void {
  if (value === undefined) {
    delete env[name];
  } else {
    env[name] = value;
  }
}

// The matcher is a single regular-expression pattern, so it can be checked directly.
function isMatchedByMiddleware(pathname: string): boolean {
  return config.matcher.some((pattern) => new RegExp(`^${pattern}$`).test(pathname));
}

function createRequest(
  pathname: string,
  authorization?: string,
  extraHeaders: Record<string, string> = {},
): NextRequest {
  const headers = new Headers();

  if (authorization) {
    headers.set('authorization', authorization);
  }

  for (const [key, value] of Object.entries(extraHeaders)) {
    headers.set(key, value);
  }

  return new NextRequest(`https://example.com${pathname}`, { headers });
}

beforeEach(() => {
  // Keep every test independent of the shell or CI job that runs it.
  delete env.MAINTENANCE_MODE;
  delete env.VERCEL_ENV;
});

afterEach(() => {
  setEnv('ADMIN_API_SECRET', originalAdminApiSecret);
  setEnv('NODE_ENV', originalNodeEnv);
  setEnv('MAINTENANCE_MODE', originalMaintenanceMode);
  setEnv('VERCEL_ENV', originalVercelEnv);
});

test('returns 401 when authorization header is missing', async () => {
  process.env.ADMIN_API_SECRET = 'test-secret';

  const response = await middleware(createRequest('/api/admin/knowledge'));

  assert.equal(response.status, 401);
  assert.deepEqual(await response.json(), { error: 'Unauthorized' });
});

test('returns 401 for same-origin admin browser requests without bearer token', async () => {
  process.env.ADMIN_API_SECRET = 'test-secret';

  const response = await middleware(
    createRequest('/api/admin/knowledge', undefined, {
      'sec-fetch-site': 'same-origin',
    }),
  );

  assert.equal(response.status, 401);
  assert.deepEqual(await response.json(), { error: 'Unauthorized' });
});

test('returns 401 when bearer token is wrong', async () => {
  process.env.ADMIN_API_SECRET = 'test-secret';

  const response = await middleware(
    createRequest('/api/cron/update-slides', 'Bearer wrong-secret'),
  );

  assert.equal(response.status, 401);
  assert.deepEqual(await response.json(), { error: 'Unauthorized' });
});

test('returns 401 when authorization scheme is not Bearer', async () => {
  process.env.ADMIN_API_SECRET = 'test-secret';

  const response = await middleware(createRequest('/api/admin/knowledge', 'Basic abc123'));

  assert.equal(response.status, 401);
  assert.deepEqual(await response.json(), { error: 'Unauthorized' });
});

test('returns NextResponse.next() when bearer token is correct', async () => {
  process.env.ADMIN_API_SECRET = 'test-secret';

  const response = await middleware(
    createRequest('/api/monitoring/dashboard', 'Bearer test-secret'),
  );

  assert.equal(response.status, 200);
  assert.equal(response.headers.get('x-middleware-next'), '1');
});

test('fails closed in production when ADMIN_API_SECRET is not set', async () => {
  delete env.ADMIN_API_SECRET;
  env.NODE_ENV = 'production';

  const response = await middleware(createRequest('/api/admin/knowledge'));

  assert.equal(response.status, 401);
  assert.deepEqual(await response.json(), { error: 'Unauthorized' });
});

test('fails closed in production when ADMIN_API_SECRET is only whitespace', async () => {
  env.ADMIN_API_SECRET = '   ';
  env.NODE_ENV = 'production';

  const response = await middleware(createRequest('/api/admin/knowledge'));

  assert.equal(response.status, 401);
  assert.deepEqual(await response.json(), { error: 'Unauthorized' });
});

test('fails closed for admin routes in development when ADMIN_API_SECRET is not set', async () => {
  delete env.ADMIN_API_SECRET;
  env.NODE_ENV = 'development';

  const response = await middleware(createRequest('/api/admin/knowledge'));

  assert.equal(response.status, 401);
  assert.deepEqual(await response.json(), { error: 'Unauthorized' });
});

test('allows non-admin operational routes in development when ADMIN_API_SECRET is not set', async () => {
  delete env.ADMIN_API_SECRET;
  env.NODE_ENV = 'development';

  const response = await middleware(createRequest('/api/monitoring/dashboard'));

  assert.equal(response.status, 200);
  assert.equal(response.headers.get('x-middleware-next'), '1');
});

test('allows traced public API routes without admin bearer token', async () => {
  process.env.ADMIN_API_SECRET = 'test-secret';
  env.NODE_ENV = 'production';

  const response = await middleware(createRequest('/api/voice'));

  assert.equal(response.status, 200);
  assert.equal(response.headers.get('x-middleware-next'), '1');
});

test('/api/alerts/webhook skips the admin bearer check and keeps its own secret check', async () => {
  process.env.ADMIN_API_SECRET = 'test-secret';
  env.NODE_ENV = 'production';

  const response = await middleware(createRequest('/api/alerts/webhook'));

  assert.equal(response.status, 200);
  assert.equal(response.headers.get('x-middleware-next'), '1');
});

test('middleware config matches pages and APIs but skips Next.js assets', () => {
  const matched = [
    '/',
    '/guide',
    '/api/voice',
    '/api/voice/filler',
    '/api/admin/knowledge',
    '/api/cron/update-knowledge-base',
    '/api/reception/start',
    '/api/alerts/webhook',
  ];

  for (const pathname of matched) {
    assert.equal(isMatchedByMiddleware(pathname), true, pathname);
  }

  for (const pathname of ['/_next/static/chunks/main.js', '/_next/image', '/favicon.ico']) {
    assert.equal(isMatchedByMiddleware(pathname), false, pathname);
  }
});

test('serves the maintenance page for page routes on Vercel production', async () => {
  env.VERCEL_ENV = 'production';

  const response = await middleware(createRequest('/'));

  assert.equal(response.status, 503);
  assert.match(response.headers.get('content-type') ?? '', /^text\/html/);
  assert.equal(response.headers.get('cache-control'), 'no-store');
  assert.equal(response.headers.get('retry-after'), '86400');
  assert.match(await response.text(), /メンテナンス中です/);
});

test('returns 503 JSON for API routes in maintenance mode before checking admin auth', async () => {
  env.VERCEL_ENV = 'production';
  process.env.ADMIN_API_SECRET = 'test-secret';

  const apiRoutes = [
    '/api/voice',
    '/api/cron/update-knowledge-base',
    '/api/admin/knowledge',
    '/api/alerts/webhook',
  ];

  for (const pathname of apiRoutes) {
    const response = await middleware(createRequest(pathname, 'Bearer test-secret'));

    assert.equal(response.status, 503, pathname);
    assert.deepEqual(await response.json(), {
      error: 'Service Unavailable',
      reason: 'maintenance',
    });
  }
});

test('MAINTENANCE_MODE=off turns off the Vercel production default', async () => {
  env.VERCEL_ENV = 'production';
  env.MAINTENANCE_MODE = 'off';

  const response = await middleware(createRequest('/'));

  assert.equal(response.status, 200);
  assert.equal(response.headers.get('x-middleware-next'), '1');
});

test('MAINTENANCE_MODE=on serves the maintenance page outside Vercel', async () => {
  env.MAINTENANCE_MODE = 'on';

  const response = await middleware(createRequest('/guide'));

  assert.equal(response.status, 503);
  assert.match(await response.text(), /メンテナンス中です/);
});

test('local runs and Vercel previews are not in maintenance by default', async () => {
  for (const vercelEnv of [undefined, 'preview', 'development']) {
    setEnv('VERCEL_ENV', vercelEnv);

    const response = await middleware(createRequest('/'));

    assert.equal(response.status, 200, String(vercelEnv));
    assert.equal(response.headers.get('x-middleware-next'), '1');
  }
});

test('isMaintenanceMode reads MAINTENANCE_MODE case-insensitively and falls back to VERCEL_ENV', () => {
  const cases: ReadonlyArray<readonly [MaintenanceModeEnv, boolean]> = [
    [{}, false],
    [{ VERCEL_ENV: 'production' }, true],
    [{ VERCEL_ENV: 'preview' }, false],
    [{ MAINTENANCE_MODE: ' ON ' }, true],
    [{ MAINTENANCE_MODE: 'TRUE' }, true],
    [{ MAINTENANCE_MODE: '1' }, true],
    [{ MAINTENANCE_MODE: 'Off', VERCEL_ENV: 'production' }, false],
    [{ MAINTENANCE_MODE: 'false', VERCEL_ENV: 'production' }, false],
    [{ MAINTENANCE_MODE: '0', VERCEL_ENV: 'production' }, false],
    [{ MAINTENANCE_MODE: 'maybe', VERCEL_ENV: 'production' }, true],
    [{ MAINTENANCE_MODE: 'maybe' }, false],
  ];

  for (const [input, expected] of cases) {
    assert.equal(isMaintenanceMode(input), expected, JSON.stringify(input));
  }
});
