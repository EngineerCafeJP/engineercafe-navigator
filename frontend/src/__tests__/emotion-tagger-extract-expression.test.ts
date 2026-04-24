import assert from 'node:assert/strict';
import { test } from 'node:test';

import { EmotionTagger } from '../lib/emotion-tagger';

test('extractExpression maps apologetic → sad (alias)', () => {
  assert.strictEqual(EmotionTagger.extractExpression('[apologetic]Text'), 'sad');
});

test('extractExpression maps helpful → happy (alias)', () => {
  assert.strictEqual(EmotionTagger.extractExpression('[helpful]x'), 'happy');
});

test('extractExpression maps neutral → neutral (direct)', () => {
  assert.strictEqual(EmotionTagger.extractExpression('[neutral]x'), 'neutral');
});

test('extractExpression maps surprised → surprised (direct)', () => {
  assert.strictEqual(EmotionTagger.extractExpression('[surprised]x'), 'surprised');
});

test('extractExpression returns null when no tag present', () => {
  assert.strictEqual(EmotionTagger.extractExpression('No tag here'), null);
});

test('extractExpression maps sad → sad with trailing text', () => {
  assert.strictEqual(EmotionTagger.extractExpression('[sad]Some text'), 'sad');
});

test('extractExpression maps confused → sad (alias)', () => {
  assert.strictEqual(EmotionTagger.extractExpression('[confused]text'), 'sad');
});
