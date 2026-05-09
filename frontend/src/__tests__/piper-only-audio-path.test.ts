import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';

const frontendRoot = path.resolve(__dirname, '..', '..');

function readComponent(relativePath: string): string {
  return fs.readFileSync(path.join(frontendRoot, 'src', relativePath), 'utf8');
}

test('voice UI does not synthesize assistant speech with browser Web Speech', () => {
  const voiceInterface = readComponent('app/components/VoiceInterface.tsx');
  const receptionGuide = readComponent('app/components/ReceptionPdfGuide.tsx');
  const combined = `${voiceInterface}\n${receptionGuide}`;

  assert.equal(combined.includes('SpeechSynthesisUtterance'), false);
  assert.equal(combined.includes('speechSynthesis.speak'), false);
});

test('assistant TTS requests explicitly use Piper Plus', () => {
  const voiceInterface = readComponent('app/components/VoiceInterface.tsx');
  const receptionGuide = readComponent('app/components/ReceptionPdfGuide.tsx');

  assert.ok((voiceInterface.match(/ttsProvider:\s*'piper'/g) ?? []).length >= 3);
  assert.ok(receptionGuide.includes("ttsProvider: 'piper'"));
});
