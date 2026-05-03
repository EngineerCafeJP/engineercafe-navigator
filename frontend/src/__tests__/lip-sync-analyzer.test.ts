import assert from "node:assert/strict";
import { after, test } from "node:test";

import { LipSyncAnalyzer, shouldSkipLipSyncAnalysis } from "../lib/lip-sync-analyzer";

const originalWindow = (globalThis as typeof globalThis & { window?: unknown }).window;
const originalNavigator = globalThis.navigator;
const originalConsoleError = console.error;

const setUserAgent = (userAgent: string): void => {
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: { userAgent },
  });
};

after(() => {
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: originalWindow,
  });
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: originalNavigator,
  });
  console.error = originalConsoleError;
});

test("shouldSkipLipSyncAnalysis skips large Android audio only", () => {
  setUserAgent("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36");
  assert.equal(shouldSkipLipSyncAnalysis(new Blob([new Uint8Array(1_000_001)])), true);
  assert.equal(shouldSkipLipSyncAnalysis(new Blob([new Uint8Array(128)])), false);

  setUserAgent("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15");
  assert.equal(shouldSkipLipSyncAnalysis(new Blob([new Uint8Array(1_000_001)])), false);
});

test("LipSyncAnalyzer decode timeout rejects instead of hanging", async () => {
  class HangingAudioContext {
    public state = "running" as AudioContextState;

    async resume() {}
    async close() {
      this.state = "closed";
    }
    createAnalyser() {
      return { fftSize: 0 };
    }
    decodeAudioData() {
      return new Promise<AudioBuffer>(() => {});
    }
  }

  setUserAgent("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15");
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      AudioContext: HangingAudioContext,
      webkitAudioContext: HangingAudioContext,
    },
  });

  console.error = () => undefined;
  const analyzer = new LipSyncAnalyzer();

  await assert.rejects(
    () => analyzer.analyzeLipSync(new Blob([new Uint8Array(32)]), 20),
    /Lip-sync audio decode timed out/,
  );

  analyzer.dispose();
});
