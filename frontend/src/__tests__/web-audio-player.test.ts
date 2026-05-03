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
