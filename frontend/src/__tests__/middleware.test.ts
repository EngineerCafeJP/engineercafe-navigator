import assert from 'node:assert/strict';
import { afterEach, mock, test } from 'node:test';
import { NextRequest } from 'next/server';

import { config, middleware } from '../middleware';

const env = process.env as Record<string, string | undefined>;
const originalAdminApiSecret = process.env.ADMIN_API_SECRET;
const originalNodeEnv = process.env.NODE_ENV;

function createRequest(pathname: string, authorization?: string): NextRequest {
  const headers = new Headers();

  if (authorization) {
    headers.set('authorization', authorization);
  }

  return new NextRequest(`https://example.com${pathname}`, { headers });
}

afterEach(() => {
  if (originalAdminApiSecret === undefined) {
    delete env.ADMIN_API_SECRET;
  } else {
    env.ADMIN_API_SECRET = originalAdminApiSecret;
  }

  if (originalNodeEnv === undefined) {
    delete env.NODE_ENV;
  } else {
    env.NODE_ENV = originalNodeEnv;
  }

  mock.restoreAll();
});

test('returns 401 when authorization header is missing', async () => {
  process.env.ADMIN_API_SECRET = 'test-secret';

  const response = middleware(createRequest('/api/admin/knowledge'));

  assert.equal(response.status, 401);
  assert.deepEqual(await response.json(), { error: 'Unauthorized' });
});

test('returns 401 when bearer token is wrong', async () => {
  process.env.ADMIN_API_SECRET = 'test-secret';

  const response = middleware(createRequest('/api/cron/update-slides', 'Bearer wrong-secret'));

  assert.equal(response.status, 401);
  assert.deepEqual(await response.json(), { error: 'Unauthorized' });
});

test('returns NextResponse.next() when bearer token is correct', () => {
  process.env.ADMIN_API_SECRET = 'test-secret';

  const response = middleware(createRequest('/api/monitoring/dashboard', 'Bearer test-secret'));

  assert.equal(response.status, 200);
  assert.equal(response.headers.get('x-middleware-next'), '1');
});

test('fails closed in production when ADMIN_API_SECRET is not set', async () => {
  delete env.ADMIN_API_SECRET;
  env.NODE_ENV = 'production';

  const response = middleware(createRequest('/api/admin/knowledge'));

  assert.equal(response.status, 401);
  assert.deepEqual(await response.json(), { error: 'Unauthorized' });
});

test('warns and allows requests in development when ADMIN_API_SECRET is not set', () => {
  delete env.ADMIN_API_SECRET;
  env.NODE_ENV = 'development';
  const warn = mock.method(console, 'warn', () => {});

  const response = middleware(createRequest('/api/admin/knowledge'));

  assert.equal(response.status, 200);
  assert.equal(response.headers.get('x-middleware-next'), '1');
  assert.equal(warn.mock.callCount(), 1);
});

test('/api/alerts/webhook is not matched by middleware config', () => {
  assert.deepEqual(config.matcher, [
    '/api/admin/:path*',
    '/api/cron/:path*',
    '/api/monitoring/:path*',
  ]);
  assert.equal(config.matcher.includes('/api/alerts/webhook'), false);
});
