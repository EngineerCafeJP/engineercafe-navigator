import assert from 'node:assert/strict';
import { test } from 'node:test';

import { QueryClassifier } from '@/lib/query-classifier';

test('applies STT corrections before classifying Engineer Cafe queries', async () => {
  const classifier = new QueryClassifier();

  const result = await classifier.classifyWithDetails('エンジニア壁の営業時間は？');

  assert.equal(result.category, 'facility-info');
  assert.equal(result.confidence, 1.0);
  assert.equal(result.debugInfo?.reason, 'Engineer Cafe specific');
});

test('applies STT corrections before classifying Saino Cafe queries', async () => {
  const classifier = new QueryClassifier();

  const result = await classifier.classifyWithDetails('才納カフェの営業時間を教えて');

  assert.equal(result.category, 'saino-cafe');
});

test('uses corrected basement wording for facility classification', async () => {
  const classifier = new QueryClassifier();

  const result = await classifier.classifyWithDetails('階下のMTGスペースについて');

  assert.equal(result.category, 'facility-info');
});

test('keeps ambiguous cafe queries ambiguous after correction pass', async () => {
  const classifier = new QueryClassifier();

  const result = await classifier.classifyWithDetails('カフェの営業時間について教えて');

  assert.equal(result.category, 'cafe-clarification-needed');
});

test('handles blank input and leaves the caller string unchanged', async () => {
  const classifier = new QueryClassifier();
  const input = 'エンジニア壁の営業時間は？';

  assert.equal(await classifier.classify('   '), 'general');
  assert.equal(await classifier.classify(input), 'facility-info');
  assert.equal(input, 'エンジニア壁の営業時間は？');
});
