import assert from 'node:assert/strict';
import { test } from 'node:test';

import type { OcrResponse } from '../lib/api/ocr-api';
import { createVisitorIdentityFromOcr } from '../lib/reception-identity';

function createOcrResponse(
  overrides: Partial<OcrResponse> = {},
): OcrResponse {
  return {
    success: true,
    mode: 'member_card',
    member_number: 12345,
    recognized_text: null,
    confidence: 0.99,
    language: null,
    expression: null,
    processing_time_ms: 120,
    visitor_identity: null,
    error: null,
    ...overrides,
  };
}

test('does not treat a raw member number as a resolved returning visitor', () => {
  const identity = createVisitorIdentityFromOcr(createOcrResponse());

  assert.equal(identity, undefined);
});

test('uses only resolved OCR visitor identity when a user_id is present', () => {
  const identity = createVisitorIdentityFromOcr(
    createOcrResponse({
      member_number: 99999,
      recognized_text: 'Fallback Name',
      visitor_identity: {
        user_id: 7,
        name: 'Resolved User',
        visit_count: 3,
        last_purpose: { category: 'facility_use', detail: 'coworking' },
      },
    }),
  );

  assert.deepEqual(identity, {
    user_id: 7,
    name: 'Resolved User',
    visit_count: 3,
    last_purpose: { category: 'facility_use', detail: 'coworking' },
  });
});
