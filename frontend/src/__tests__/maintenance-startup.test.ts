import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { afterEach, test } from 'node:test';

import { register } from '../instrumentation';
import { productionRequiredVercelEnvKeys } from '../lib/env';

const env = process.env as Record<string, string | undefined>;
const frontendRoot = path.resolve(__dirname, '..', '..');
const managedKeys = [
  ...productionRequiredVercelEnvKeys,
  'MAINTENANCE_MODE',
  'VERCEL_ENV',
  'NEXT_RUNTIME',
  'NODE_ENV',
] as const;
const originalValues = new Map<string, string | undefined>(
  managedKeys.map((key) => [key, env[key]]),
);

function restoreEnv(): void {
  originalValues.forEach((value, key) => {
    if (value === undefined) {
      delete env[key];
    } else {
      env[key] = value;
    }
  });
}

// Simulates Vercel production after the retired backend and Supabase credentials are removed.
function useProductionWithoutRetiredCredentials(maintenanceMode: string | undefined): void {
  for (const key of productionRequiredVercelEnvKeys) {
    delete env[key];
  }

  env.NEXT_RUNTIME = 'nodejs';
  env.NODE_ENV = 'production';
  env.VERCEL_ENV = 'production';

  if (maintenanceMode === undefined) {
    delete env.MAINTENANCE_MODE;
  } else {
    env.MAINTENANCE_MODE = maintenanceMode;
  }
}

function runBuildEnvCheck(maintenanceMode: string | undefined) {
  const childEnv: Record<string, string> = {};

  for (const [key, value] of Object.entries(process.env)) {
    if (value !== undefined) {
      childEnv[key] = value;
    }
  }

  for (const key of productionRequiredVercelEnvKeys) {
    delete childEnv[key];
  }

  childEnv.VERCEL_ENV = 'production';
  delete childEnv.MAINTENANCE_MODE;

  if (maintenanceMode !== undefined) {
    childEnv.MAINTENANCE_MODE = maintenanceMode;
  }

  return spawnSync(
    process.execPath,
    ['--import', 'tsx', 'scripts/check-vercel-production-env.ts'],
    { cwd: frontendRoot, env: childEnv, encoding: 'utf8' },
  );
}

afterEach(restoreEnv);

test('startup validation is skipped in maintenance mode without retired-service credentials', async () => {
  useProductionWithoutRetiredCredentials(undefined);

  await assert.doesNotReject(register());
});

test('startup validation still blocks production when maintenance mode is off', async () => {
  useProductionWithoutRetiredCredentials('off');

  await assert.rejects(register(), /Server startup blocked/);
});

test('build-time env check passes in maintenance mode without retired-service credentials', () => {
  const result = runBuildEnvCheck(undefined);

  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /maintenance mode is on/);
});

test('build-time env check still fails when maintenance mode is off', () => {
  const result = runBuildEnvCheck('off');

  assert.equal(result.status, 1, result.stdout);
  assert.match(result.stderr, /Missing required env var/);
});
