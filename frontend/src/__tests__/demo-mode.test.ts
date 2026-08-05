import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';

import { getDefaultKioskLanguage, getTtsProvider, isDemoMode } from '../lib/env-client';

const env = process.env as Record<string, string | undefined>;
const managedKey = 'NEXT_PUBLIC_DEMO_MODE';
const originalValue = env[managedKey];

function restoreEnv() {
  if (originalValue === undefined) {
    delete env[managedKey];
  } else {
    env[managedKey] = originalValue;
  }
}

afterEach(restoreEnv);

test('isDemoMode is false when NEXT_PUBLIC_DEMO_MODE is unset', () => {
  delete env[managedKey];
  assert.equal(isDemoMode(), false);
});

test('isDemoMode is true when NEXT_PUBLIC_DEMO_MODE=true', () => {
  env[managedKey] = 'true';
  assert.equal(isDemoMode(), true);
});

test('isDemoMode is false when NEXT_PUBLIC_DEMO_MODE=false', () => {
  env[managedKey] = 'false';
  assert.equal(isDemoMode(), false);
});

test('default kiosk language stays ja when demo mode is off', () => {
  delete env[managedKey];
  assert.equal(getDefaultKioskLanguage(), 'ja');
});

test('default kiosk language is en when demo mode is on', () => {
  env[managedKey] = 'true';
  assert.equal(getDefaultKioskLanguage(), 'en');
});

test('getTtsProvider stays piper when demo mode is off', () => {
  delete env[managedKey];
  assert.equal(getTtsProvider(), 'piper');
});

test('getTtsProvider is kokoro when demo mode is on', () => {
  env[managedKey] = 'true';
  assert.equal(getTtsProvider(), 'kokoro');
});
