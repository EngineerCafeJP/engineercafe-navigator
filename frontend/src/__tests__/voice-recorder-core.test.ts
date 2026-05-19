import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';

import { VoiceRecorder } from '../lib/voice-recorder-core';

const originalFetch = global.fetch;
const originalNavigatorDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'navigator');
const originalWindowDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'window');

function restoreProperty(name: 'navigator' | 'window', descriptor: PropertyDescriptor | undefined) {
  if (descriptor) {
    Object.defineProperty(globalThis, name, descriptor);
    return;
  }

  Reflect.deleteProperty(globalThis, name);
}

afterEach(() => {
  global.fetch = originalFetch;
  restoreProperty('navigator', originalNavigatorDescriptor);
  restoreProperty('window', originalWindowDescriptor);
});

test('VoiceRecorder posts recorder errors to dedicated telemetry endpoint', async () => {
  let capturedEventDetail: Record<string, unknown> | null = null;
  let capturedUrl: string | URL | Request | undefined;
  let capturedInit: RequestInit | undefined;

  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: {
      dispatchEvent: (event: Event): boolean => {
        if (event.type === 'voice-recorder-telemetry') {
          capturedEventDetail = (event as CustomEvent<Record<string, unknown>>).detail;
        }
        return true;
      },
    },
  });
  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    value: undefined,
  });
  global.fetch = (async (input, init) => {
    capturedUrl = input;
    capturedInit = init;
    return new Response(JSON.stringify({ success: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }) as typeof fetch;

  const errors: Error[] = [];
  const recorder = new VoiceRecorder(
    () => {},
    (error) => {
      errors.push(error);
    },
    undefined,
    { getSessionId: () => 'session-1' },
  );

  await recorder.initialize();
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.equal(errors.length, 1);
  assert.equal(errors[0].message, 'navigator is undefined');
  assert.equal(capturedUrl, '/api/telemetry/voice');
  assert.equal(capturedInit?.method, 'POST');
  assert.equal(capturedInit?.keepalive, true);

  const body = JSON.parse(capturedInit?.body as string) as Record<string, unknown>;
  assert.equal(body.event, 'voice_recorder_error');
  assert.equal(body.phase, 'navigator-unavailable');
  assert.equal(body.sessionId, 'session-1');
  assert.equal(body.errorName, 'Error');
  assert.equal(body.errorMessage, 'navigator is undefined');
  assert.equal('action' in body, false);
  assert.notEqual(capturedEventDetail, null);
  const eventDetail = capturedEventDetail as unknown as Record<string, unknown>;
  assert.equal(eventDetail.event, 'voice_recorder_error');
  assert.equal('action' in eventDetail, false);
});
