import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';

import {
  getMissingProductionRequiredVercelEnvKeys,
  productionRequiredVercelEnvKeys,
  validateServerEnv,
} from '../lib/env';

const env = process.env as Record<string, string | undefined>;
const managedKeys = [
  ...productionRequiredVercelEnvKeys,
  'ADMIN_API_SECRET',
  'CRON_SECRET',
  'OPENROUTER_API_KEY',
  'SUPABASE_SERVICE_ROLE_KEY',
] as const;
const originalValues = new Map<string, string | undefined>(
  managedKeys.map((key) => [key, env[key]]),
);

function restoreEnv() {
  originalValues.forEach((value, key) => {
    if (value === undefined) {
      delete env[key];
    } else {
      env[key] = value;
    }
  });
}

function setValidRequiredEnv() {
  env.NEXT_PUBLIC_SUPABASE_URL = 'https://project-ref.supabase.co';
  env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'test-anon-key';
  env.BACKEND_API_URL = 'https://backend.example.com';
  env.BACKEND_API_KEY = 'test-backend-key';
}

afterEach(restoreEnv);

test('Vercel production required env contract includes public Supabase config', () => {
  assert.ok(productionRequiredVercelEnvKeys.includes('NEXT_PUBLIC_SUPABASE_URL'));
  assert.ok(productionRequiredVercelEnvKeys.includes('NEXT_PUBLIC_SUPABASE_ANON_KEY'));
});

test('detects missing Vercel production required Supabase env vars by name only', () => {
  setValidRequiredEnv();
  delete env.NEXT_PUBLIC_SUPABASE_URL;
  delete env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  assert.deepEqual(getMissingProductionRequiredVercelEnvKeys(), [
    'NEXT_PUBLIC_SUPABASE_URL',
    'NEXT_PUBLIC_SUPABASE_ANON_KEY',
  ]);

  const result = validateServerEnv();
  const errors = result.errors.join('\n');

  assert.equal(result.success, false);
  assert.match(errors, /NEXT_PUBLIC_SUPABASE_URL/);
  assert.match(errors, /NEXT_PUBLIC_SUPABASE_ANON_KEY/);
  assert.doesNotMatch(errors, /test-backend-key/);
});

test('treats blank production required env values as missing', () => {
  setValidRequiredEnv();
  env.NEXT_PUBLIC_SUPABASE_ANON_KEY = '   ';

  assert.deepEqual(getMissingProductionRequiredVercelEnvKeys(), [
    'NEXT_PUBLIC_SUPABASE_ANON_KEY',
  ]);

  const result = validateServerEnv();

  assert.equal(result.success, false);
  assert.match(result.errors.join('\n'), /NEXT_PUBLIC_SUPABASE_ANON_KEY is required/);
});

test('passes required env validation when Vercel production required vars are present', () => {
  setValidRequiredEnv();

  const result = validateServerEnv();

  assert.equal(result.success, true);
  assert.deepEqual(getMissingProductionRequiredVercelEnvKeys(), []);
});
