import assert from 'node:assert/strict';
import { test } from 'node:test';

import { isSlideAgentMetadata } from '@/lib/voice/slide-agent-metadata';

test('detects current SlideAgent metadata variants used by voice and kiosk flows', () => {
  assert.equal(isSlideAgentMetadata({ agent: 'SlideAgent' }), true);
  assert.equal(isSlideAgentMetadata({ route: 'slide' }), true);
  assert.equal(isSlideAgentMetadata({ reception_target_agent: 'slide_agent' }), true);
  assert.equal(isSlideAgentMetadata({ reception_target_agent: 'SlideAgent' }), true);
});

test('does not classify absent or unrelated metadata as SlideAgent output', () => {
  assert.equal(isSlideAgentMetadata(null), false);
  assert.equal(isSlideAgentMetadata(undefined), false);
  assert.equal(isSlideAgentMetadata({ agent: 'FacilityAgent', route: 'facility' }), false);
  assert.equal(isSlideAgentMetadata({ route: 'slides' }), false);
});
