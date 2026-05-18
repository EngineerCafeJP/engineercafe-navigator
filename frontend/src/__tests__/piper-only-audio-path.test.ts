import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';

const frontendRoot = path.resolve(__dirname, '..', '..');

function readComponent(relativePath: string): string {
  return fs.readFileSync(path.join(frontendRoot, 'src', relativePath), 'utf8');
}

function readReceptionGuideModule(): string {
  const guideRoot = path.join(frontendRoot, 'src', 'app', 'components');
  const guideFiles = [
    'ReceptionPdfGuide.tsx',
    'reception-pdf-guide/ReceptionPdfGuideView.tsx',
    'reception-pdf-guide/receptionPdfGuideUtils.ts',
    'reception-pdf-guide/types.ts',
    'reception-pdf-guide/useLandscapeReady.ts',
    'reception-pdf-guide/useReceptionNarrationText.ts',
    'reception-pdf-guide/useReceptionPdfCanvas.ts',
    'reception-pdf-guide/useReceptionPdfPlayback.ts',
    'reception-pdf-guide/useSlideSwipeNavigation.ts',
    'reception-pdf-guide/useStaticNarrationAudioPreloader.ts',
  ];

  return guideFiles
    .map((file) => fs.readFileSync(path.join(guideRoot, file), 'utf8'))
    .join('\n');
}

test('voice UI does not synthesize assistant speech with browser Web Speech', () => {
  const voiceInterface = readComponent('app/components/VoiceInterface.tsx');
  const receptionGuide = readReceptionGuideModule();
  const combined = `${voiceInterface}\n${receptionGuide}`;

  assert.equal(combined.includes('SpeechSynthesisUtterance'), false);
  assert.equal(combined.includes('speechSynthesis.speak'), false);
});

test('assistant TTS requests explicitly use Piper Plus', () => {
  const voiceInterface = readComponent('app/components/VoiceInterface.tsx');
  const receptionGuide = readReceptionGuideModule();

  assert.ok((voiceInterface.match(/ttsProvider:\s*'piper'/g) ?? []).length >= 3);
  assert.ok(receptionGuide.includes("ttsProvider: 'piper'"));
});
