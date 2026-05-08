import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  RECEPTION_NARRATION_MIN_SLIDE_DWELL_MS,
  getReceptionNarrationAdvanceDelay,
} from '../lib/reception/reception-narration-timing';

test('slide narration advance waits for minimum dwell after immediate completion', () => {
  assert.equal(
    getReceptionNarrationAdvanceDelay({
      slideShownAtMs: 1_000,
      nowMs: 1_100,
      requestedDelayMs: 500,
    }),
    RECEPTION_NARRATION_MIN_SLIDE_DWELL_MS - 100,
  );
});

test('slide narration advance keeps requested delay after minimum dwell is satisfied', () => {
  assert.equal(
    getReceptionNarrationAdvanceDelay({
      slideShownAtMs: 1_000,
      nowMs: 8_000,
      requestedDelayMs: 500,
    }),
    500,
  );
});

test('slide narration advance handles invalid timing values safely', () => {
  assert.equal(
    getReceptionNarrationAdvanceDelay({
      slideShownAtMs: Number.NaN,
      nowMs: 8_000,
      requestedDelayMs: -1,
      minimumDwellMs: 2_000,
    }),
    2_000,
  );
});
