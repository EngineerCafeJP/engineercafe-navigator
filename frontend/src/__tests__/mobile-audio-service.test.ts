import assert from "node:assert/strict";
import { after, test } from "node:test";

import {
  estimateAudioDataByteLength,
  MobileAudioService,
  shouldResetWebAudioPlayerForDevice,
  shouldUseHtmlAudioFirstForPlayback,
} from "../lib/audio/mobile-audio-service";
import { AudioPlaybackService } from "../lib/audio/audio-playback-service";

const originalNavigator = globalThis.navigator;
const originalWindow = (globalThis as typeof globalThis & { window?: unknown }).window;
const originalDocument = (globalThis as typeof globalThis & { document?: unknown }).document;
const originalAudio = (globalThis as typeof globalThis & { Audio?: unknown }).Audio;
const originalCreateObjectURL = URL.createObjectURL;
const originalRevokeObjectURL = URL.revokeObjectURL;

const setUserAgent = (userAgent: string): void => {
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: { userAgent },
  });
};

after(() => {
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: originalNavigator,
  });
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: originalWindow,
  });
  Object.defineProperty(globalThis, "document", {
    configurable: true,
    value: originalDocument,
  });
  Object.defineProperty(globalThis, "Audio", {
    configurable: true,
    value: originalAudio,
  });
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: originalCreateObjectURL,
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    value: originalRevokeObjectURL,
  });
});

test("estimateAudioDataByteLength handles raw and data URL base64", () => {
  assert.equal(estimateAudioDataByteLength("AQIDBA=="), 4);
  assert.equal(estimateAudioDataByteLength("data:audio/wav;base64,AQIDBA=="), 4);
  assert.equal(estimateAudioDataByteLength(""), 0);
});

test("estimateAudioDataByteLength handles Blob and ArrayBuffer inputs", () => {
  assert.equal(estimateAudioDataByteLength(new Blob([new Uint8Array(7)])), 7);
  assert.equal(estimateAudioDataByteLength(new ArrayBuffer(9)), 9);
});

test("Android large audio uses HTML audio before Web Audio decode", () => {
  setUserAgent("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36");

  const largeBase64 = "A".repeat(1_333_340);
  assert.equal(estimateAudioDataByteLength(largeBase64), 1_000_005);
  assert.equal(shouldUseHtmlAudioFirstForPlayback(largeBase64), true);
});

test("mobile Web Audio reset applies to Android phones as well as iOS", () => {
  setUserAgent("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36");
  assert.equal(shouldResetWebAudioPlayerForDevice(), true);

  setUserAgent("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15");
  assert.equal(shouldResetWebAudioPlayerForDevice(), true);

  setUserAgent("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15");
  assert.equal(shouldResetWebAudioPlayerForDevice(), false);
});

test("Android large base64 playback uses HTML audio without constructing AudioContext", async () => {
  let audioContextConstructed = false;
  let createdObjectUrl = "";

  class MockAudioElement {
    public preload = "";
    public volume = 1;
    public paused = true;
    public ended = false;
    private listeners = new Map<string, Set<() => void>>();

    constructor(public readonly url: string) {}

    setAttribute() {}
    removeAttribute() {}
    load() {}
    pause() {
      this.paused = true;
    }
    addEventListener(event: string, listener: () => void) {
      const listeners = this.listeners.get(event) ?? new Set<() => void>();
      listeners.add(listener);
      this.listeners.set(event, listeners);
    }
    removeEventListener(event: string, listener: () => void) {
      this.listeners.get(event)?.delete(listener);
    }
    async play() {
      this.paused = false;
      this.listeners.get("play")?.forEach((listener) => listener());
      setTimeout(() => {
        this.ended = true;
        this.listeners.get("ended")?.forEach((listener) => listener());
      }, 0);
    }
  }

  class FailIfConstructedAudioContext {
    constructor() {
      audioContextConstructed = true;
    }
  }

  setUserAgent("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36");
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      innerWidth: 390,
      setTimeout,
      clearTimeout,
      AudioContext: FailIfConstructedAudioContext,
      webkitAudioContext: FailIfConstructedAudioContext,
    },
  });
  Object.defineProperty(globalThis, "document", {
    configurable: true,
    value: {
      addEventListener() {},
      removeEventListener() {},
    },
  });
  Object.defineProperty(globalThis, "Audio", {
    configurable: true,
    value: MockAudioElement,
  });
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: (blob: Blob) => {
      createdObjectUrl = `blob:android-large-${blob.size}`;
      return createdObjectUrl;
    },
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    value: () => {},
  });

  const largeBase64 = Buffer.alloc(1_000_005).toString("base64");
  const service = new MobileAudioService();
  const result = await service.playAudio(largeBase64);

  assert.equal(result.success, true);
  assert.equal(result.method, "html-audio");
  assert.equal(createdObjectUrl, "blob:android-large-1000005");
  assert.equal(audioContextConstructed, false);

  service.dispose();
});

test("non-Android and small Android audio stay on Web Audio first", () => {
  const largeBase64 = "A".repeat(1_333_340);
  const smallBase64 = "A".repeat(400);

  setUserAgent("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15");
  assert.equal(shouldUseHtmlAudioFirstForPlayback(largeBase64), false);

  setUserAgent("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36");
  assert.equal(shouldUseHtmlAudioFirstForPlayback(smallBase64), false);
});

test("blob and http audio URLs use HTML audio without creating object URLs", async () => {
  let lastAudioUrl = "";
  let createObjectURLCalled = false;

  class MockAudioElement {
    public preload = "";
    public volume = 1;
    public paused = true;
    public ended = false;
    private listeners = new Map<string, Set<() => void>>();

    constructor(url: string) {
      lastAudioUrl = url;
    }

    setAttribute() {}
    removeAttribute() {}
    load() {}
    pause() {
      this.paused = true;
    }
    addEventListener(event: string, listener: () => void) {
      const listeners = this.listeners.get(event) ?? new Set<() => void>();
      listeners.add(listener);
      this.listeners.set(event, listeners);
    }
    removeEventListener(event: string, listener: () => void) {
      this.listeners.get(event)?.delete(listener);
    }
    async play() {
      this.paused = false;
      this.listeners.get("play")?.forEach((listener) => listener());
      setTimeout(() => {
        this.ended = true;
        this.listeners.get("ended")?.forEach((listener) => listener());
      }, 0);
    }
  }

  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: { innerWidth: 390, setTimeout, clearTimeout },
  });
  Object.defineProperty(globalThis, "document", {
    configurable: true,
    value: {
      addEventListener() {},
      removeEventListener() {},
    },
  });
  Object.defineProperty(globalThis, "Audio", {
    configurable: true,
    value: MockAudioElement,
  });
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: () => {
      createObjectURLCalled = true;
      return "blob:created";
    },
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    value: () => {},
  });

  const service = new MobileAudioService();
  const result = await service.playAudio("blob:existing-audio");

  assert.equal(result.success, true);
  assert.equal(result.method, "html-audio");
  assert.equal(lastAudioUrl, "blob:existing-audio");
  assert.equal(createObjectURLCalled, false);

  const httpResult = await service.playAudio("https://example.com/audio.mp3");
  assert.equal(httpResult.success, true);
  assert.equal(httpResult.method, "html-audio");
  assert.equal(lastAudioUrl, "https://example.com/audio.mp3");
  assert.equal(createObjectURLCalled, false);

  const playbackResult = await AudioPlaybackService.playAudioFast("blob:playback-audio");
  assert.equal(playbackResult.success, true);
  assert.equal(playbackResult.method, "html-audio");

  service.dispose();
});

test("playAudioWithLipSync skips analyzer for blob audio URLs", async () => {
  let audioContextConstructed = false;

  class MockAudioElement {
    public preload = "";
    public volume = 1;
    public paused = true;
    public ended = false;
    private listeners = new Map<string, Set<() => void>>();

    constructor(public readonly url: string) {}

    setAttribute() {}
    removeAttribute() {}
    load() {}
    pause() {
      this.paused = true;
    }
    addEventListener(event: string, listener: () => void) {
      const listeners = this.listeners.get(event) ?? new Set<() => void>();
      listeners.add(listener);
      this.listeners.set(event, listeners);
    }
    removeEventListener(event: string, listener: () => void) {
      this.listeners.get(event)?.delete(listener);
    }
    async play() {
      this.paused = false;
      this.listeners.get("play")?.forEach((listener) => listener());
      setTimeout(() => {
        this.ended = true;
        this.listeners.get("ended")?.forEach((listener) => listener());
      }, 0);
    }
  }

  class AnalyzerAudioContext {
    constructor() {
      audioContextConstructed = true;
    }
    async resume() {}
    createAnalyser() {
      return { fftSize: 0 };
    }
  }

  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      innerWidth: 390,
      setTimeout,
      clearTimeout,
      AudioContext: AnalyzerAudioContext,
      webkitAudioContext: AnalyzerAudioContext,
    },
  });
  Object.defineProperty(globalThis, "document", {
    configurable: true,
    value: {
      addEventListener() {},
      removeEventListener() {},
    },
  });
  Object.defineProperty(globalThis, "Audio", {
    configurable: true,
    value: MockAudioElement,
  });

  const result = await AudioPlaybackService.playAudioWithLipSync("blob:playback-audio", {
    enableLipSync: true,
    onVisemeUpdate: () => undefined,
  });

  assert.equal(result.success, true);
  assert.equal(result.method, "html-audio");
  assert.equal(audioContextConstructed, false);
});
