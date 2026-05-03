import assert from "node:assert/strict";
import { test } from "node:test";

import { WebAudioPlayer } from "../lib/audio/web-audio-player";

test("WebAudioPlayer reuses the gesture-unlocked AudioContext", async () => {
  let closeCalled = false;
  const sharedContext = {
    state: "running",
    destination: {},
    createGain: () => ({
      connect: () => undefined,
      gain: { value: 1 },
    }),
    close: () => {
      closeCalled = true;
      return Promise.resolve();
    },
  } as unknown as AudioContext;

  const player = new WebAudioPlayer({}, sharedContext);
  await player.initializeContext();

  assert.equal(player.getAudioContextState(), "running");

  player.dispose();
  assert.equal(closeCalled, false);
});

test("WebAudioPlayer returns decode timeout instead of hanging", async () => {
  const originalConsoleError = console.error;
  const sharedContext = {
    state: "running",
    destination: {},
    createGain: () => ({
      connect: () => undefined,
      gain: { value: 1 },
    }),
    decodeAudioData: () => new Promise<AudioBuffer>(() => {}),
  } as unknown as AudioContext;

  console.error = () => undefined;
  try {
    const player = new WebAudioPlayer({ decodeTimeoutMs: 5 }, sharedContext);
    const result = await player.loadAudioData("UklGRiQAAABXQVZFZm10IBAAAAABAAEA");

    assert.equal(result.success, false);
    assert.equal(result.error?.type, "decode_failed");
    assert.match(result.error?.message ?? "", /timed out/);
  } finally {
    console.error = originalConsoleError;
  }
});
