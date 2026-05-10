import assert from "node:assert/strict";
import { afterEach, test } from "node:test";

import { AudioQueue } from "../lib/audio-queue";
import { AudioError, AudioErrorType, type AudioOperationResult } from "../lib/audio/audio-interfaces";
import { AudioInteractionManager } from "../lib/audio/audio-interaction-manager";
import { resetAudioUserInteractionGate } from "../lib/audio/audio-user-interaction-gate";
import {
  GlobalAudioManager,
} from "../lib/audio/web-audio-player";
import {
  MobileAudioService,
  type MobileAudioOptions,
} from "../lib/audio/mobile-audio-service";

const originalConsoleError = console.error;
const originalNavigator = globalThis.navigator;
const originalWindow = (globalThis as typeof globalThis & { window?: unknown }).window;
const originalDocument = (globalThis as typeof globalThis & { document?: unknown }).document;
const originalPlayAudio = MobileAudioService.prototype.playAudio;

const restoreAudioInteractionSingleton = (): void => {
  (AudioInteractionManager as unknown as { instance?: AudioInteractionManager }).instance = undefined;
};

const installBrowserStubs = (): void => {
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: { userAgent: "node:test", vendor: "", platform: "", maxTouchPoints: 0 },
  });
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      addEventListener() {},
      removeEventListener() {},
      dispatchEvent() {
        return true;
      },
    },
  });
  Object.defineProperty(globalThis, "document", {
    configurable: true,
    value: {
      addEventListener() {},
      removeEventListener() {},
    },
  });
};

afterEach(() => {
  MobileAudioService.prototype.playAudio = originalPlayAudio;
  console.error = originalConsoleError;
  resetAudioUserInteractionGate();
  GlobalAudioManager.getInstance().dispose();
  restoreAudioInteractionSingleton();
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
});

test("AudioQueue only fires onPlaybackEnd once when service emits onError before resolving failure", async () => {
  installBrowserStubs();
  console.error = () => undefined;

  let playAudioCalls = 0;
  MobileAudioService.prototype.playAudio = function (): Promise<AudioOperationResult> {
    playAudioCalls += 1;
    const error = new AudioError(AudioErrorType.PLAYBACK_FAILED, "decode failed before resolve");
    (this as unknown as { options: MobileAudioOptions }).options.onError?.(error);
    return Promise.resolve({
      success: false,
      method: "web-audio",
      error,
    });
  };

  const queue = new AudioQueue();
  let playbackEndCalls = 0;
  const finished = new Promise<void>((resolve) => {
    queue.setOnFinished(resolve);
  });

  queue.add({
    id: "service-error-before-resolve",
    audioData: "UklGRiQAAABXQVZFZm10IBAAAAABAAEA",
    onPlaybackEnd: () => {
      playbackEndCalls += 1;
    },
  });

  await Promise.race([
    finished,
    new Promise<never>((_, reject) => {
      setTimeout(() => reject(new Error("AudioQueue did not finish")), 1000);
    }),
  ]);

  assert.equal(playAudioCalls, 1);
  assert.equal(playbackEndCalls, 1);
});
