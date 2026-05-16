import assert from 'node:assert/strict';
import { test } from 'node:test';

import { getMemberCardPhase2ReceptionMessage } from '../lib/member-card-reception';

test('member card reception message explains Phase 2 limitation in Japanese', () => {
  const message = getMemberCardPhase2ReceptionMessage(12345, 'ja');

  assert.match(message, /会員番号 12345 を読み取りました/);
  assert.match(message, /会員情報に基づく座席の提案や個別案内/);
  assert.match(message, /フェーズ2以降/);
  assert.match(message, /ご用件をお聞かせください/);
});

test('member card reception message explains Phase 2 limitation in English', () => {
  const message = getMemberCardPhase2ReceptionMessage(12345, 'en');

  assert.match(message, /Read member number 12345/);
  assert.match(message, /personalized guidance/);
  assert.match(message, /Phase 2 or later/);
});
