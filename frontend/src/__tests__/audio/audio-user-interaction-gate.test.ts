import assert from 'node:assert/strict';
import { afterEach, beforeEach, test } from 'node:test';

import {
  AUDIO_USER_INTERACTION_SESSION_STORAGE_KEY,
  getTapToEnableAudioMessage,
  hasAudioUserInteraction,
  isIOSWebKitAudio,
  registerAudioInteractionCallback,
  resetAudioUserInteractionGate,
  waitForAudioUserInteraction,
} from '../../lib/audio/audio-user-interaction-gate';

interface NavigatorStub {
  userAgent: string;
  vendor: string;
  platform: string;
  maxTouchPoints: number;
}

interface SessionStorageStub {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

const originalWindowDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'window');
const originalDocumentDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'document');
const originalNavigatorDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'navigator');

const restoreGlobalProperty = (
  key: 'window' | 'document' | 'navigator',
  descriptor: PropertyDescriptor | undefined,
): void => {
  if (descriptor) {
    Object.defineProperty(globalThis, key, descriptor);
    return;
  }

  Reflect.deleteProperty(globalThis, key);
};

const defineNavigatorProperty = <Key extends keyof NavigatorStub>(
  key: Key,
  value: NavigatorStub[Key],
): void => {
  Object.defineProperty(globalThis.navigator, key, {
    configurable: true,
    value,
  });
};

const stubNavigator = ({
  userAgent,
  vendor,
  platform,
  maxTouchPoints,
}: NavigatorStub): void => {
  defineNavigatorProperty('userAgent', userAgent);
  defineNavigatorProperty('vendor', vendor);
  defineNavigatorProperty('platform', platform);
  defineNavigatorProperty('maxTouchPoints', maxTouchPoints);
};

const createSessionStorageStub = (): SessionStorageStub => {
  const values = new Map<string, string>();

  return {
    getItem(key: string): string | null {
      return values.get(key) ?? null;
    },
    setItem(key: string, value: string): void {
      values.set(key, value);
    },
    removeItem(key: string): void {
      values.delete(key);
    },
  };
};

beforeEach(() => {
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: {
      sessionStorage: createSessionStorageStub(),
    },
  });
  Object.defineProperty(globalThis, 'document', {
    configurable: true,
    value: {
      addEventListener() {},
      removeEventListener() {},
    },
  });
  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    value: {},
  });

  stubNavigator({
    userAgent: '',
    vendor: '',
    platform: '',
    maxTouchPoints: 0,
  });
});

afterEach(() => {
  resetAudioUserInteractionGate();
  restoreGlobalProperty('window', originalWindowDescriptor);
  restoreGlobalProperty('document', originalDocumentDescriptor);
  restoreGlobalProperty('navigator', originalNavigatorDescriptor);
});

test('isIOSWebKitAudio returns false outside the browser', { concurrency: false }, () => {
  Reflect.deleteProperty(globalThis, 'window');
  Reflect.deleteProperty(globalThis, 'document');

  assert.equal(isIOSWebKitAudio(), false);
});

test('isIOSWebKitAudio returns true for iPhone UA', { concurrency: false }, () => {
  stubNavigator({
    userAgent:
      'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
    vendor: 'Apple Computer, Inc.',
    platform: 'iPhone',
    maxTouchPoints: 1,
  });

  assert.equal(isIOSWebKitAudio(), true);
});

test('isIOSWebKitAudio returns true for iPad UA', { concurrency: false }, () => {
  stubNavigator({
    userAgent:
      'Mozilla/5.0 (iPad; CPU OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
    vendor: 'Apple Computer, Inc.',
    platform: 'iPad',
    maxTouchPoints: 5,
  });

  assert.equal(isIOSWebKitAudio(), true);
});

test('isIOSWebKitAudio returns true for iPadOS desktop UA spoofing', { concurrency: false }, () => {
  stubNavigator({
    userAgent:
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15',
    vendor: 'Apple Computer, Inc.',
    platform: 'MacIntel',
    maxTouchPoints: 5,
  });

  assert.equal(isIOSWebKitAudio(), true);
});

test('isIOSWebKitAudio returns false for desktop Chrome', { concurrency: false }, () => {
  stubNavigator({
    userAgent:
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    vendor: 'Google Inc.',
    platform: 'MacIntel',
    maxTouchPoints: 0,
  });

  assert.equal(isIOSWebKitAudio(), false);
});

test('isIOSWebKitAudio returns false for desktop Safari on macOS', { concurrency: false }, () => {
  stubNavigator({
    userAgent:
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15',
    vendor: 'Apple Computer, Inc.',
    platform: 'MacIntel',
    maxTouchPoints: 0,
  });

  assert.equal(isIOSWebKitAudio(), false);
});

test('isIOSWebKitAudio returns false for Android Chrome', { concurrency: false }, () => {
  stubNavigator({
    userAgent:
      'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Mobile Safari/537.36',
    vendor: 'Google Inc.',
    platform: 'Linux armv8l',
    maxTouchPoints: 5,
  });

  assert.equal(isIOSWebKitAudio(), false);
});

test('getTapToEnableAudioMessage returns localized messages', { concurrency: false }, () => {
  assert.equal(getTapToEnableAudioMessage('ja'), '音声を有効にするには、もう一度画面をタップしてください');
  assert.equal(getTapToEnableAudioMessage('en'), 'Tap once more to enable audio playback');
  assert.equal(getTapToEnableAudioMessage('zh'), '请再次点按屏幕以启用音频');
  assert.equal(getTapToEnableAudioMessage('ko'), '오디오를 활성화하려면 화면을 한 번 더 탭하세요');
});

test('getTapToEnableAudioMessage falls back to English for unknown languages', {
  concurrency: false,
}, () => {
  assert.equal(getTapToEnableAudioMessage('fr'), 'Tap once more to enable audio playback');
});

test('getTapToEnableAudioMessage falls back to English for empty string', {
  concurrency: false,
}, () => {
  assert.equal(getTapToEnableAudioMessage(''), 'Tap once more to enable audio playback');
});

test('waitForAudioUserInteraction unlocks after timeout and persists session bypass', {
  concurrency: false,
}, async () => {
  const startedAt = Date.now();

  await waitForAudioUserInteraction(10);

  assert.equal(hasAudioUserInteraction(), true);
  assert.equal(
    window.sessionStorage.getItem(AUDIO_USER_INTERACTION_SESSION_STORAGE_KEY),
    'true',
  );
  assert.ok(Date.now() - startedAt < 1000);
});

test('sessionStorage bypass immediately unlocks gate callbacks', {
  concurrency: false,
}, async () => {
  window.sessionStorage.setItem(AUDIO_USER_INTERACTION_SESSION_STORAGE_KEY, 'true');

  let callbackCalls = 0;
  registerAudioInteractionCallback(() => {
    callbackCalls += 1;
  });

  await waitForAudioUserInteraction(1000);

  assert.equal(hasAudioUserInteraction(), true);
  assert.equal(callbackCalls, 1);
});
