import assert from "node:assert/strict";
import { after, test } from "node:test";

import {
  estimateAudioDataByteLength,
  shouldUseHtmlAudioFirstForPlayback,
} from "../lib/audio/mobile-audio-service";

const originalNavigator = globalThis.navigator;

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

test("non-Android and small Android audio stay on Web Audio first", () => {
  const largeBase64 = "A".repeat(1_333_340);
  const smallBase64 = "A".repeat(400);

  setUserAgent("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15");
  assert.equal(shouldUseHtmlAudioFirstForPlayback(largeBase64), false);

  setUserAgent("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36");
  assert.equal(shouldUseHtmlAudioFirstForPlayback(smallBase64), false);
});
