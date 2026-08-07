import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';

const frontendRoot = path.resolve(__dirname, '..', '..');

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

function readVoiceInterfaceModules(): string {
  const voiceRoot = path.join(frontendRoot, 'src', 'app', 'components');
  const voiceFiles = [
    'VoiceInterface.tsx',
    'voice-interface/useVoiceTurnProcessor.ts',
  ];

  return voiceFiles
    .map((file) => fs.readFileSync(path.join(voiceRoot, file), 'utf8'))
    .join('\n');
}

test('voice UI does not synthesize assistant speech with browser Web Speech', () => {
  const voiceInterface = readVoiceInterfaceModules();
  const receptionGuide = readReceptionGuideModule();
  const combined = `${voiceInterface}\n${receptionGuide}`;

  assert.equal(combined.includes('SpeechSynthesisUtterance'), false);
  assert.equal(combined.includes('speechSynthesis.speak'), false);
});

test('assistant TTS requests use getTtsProvider() (defaults to Piper Plus)', () => {
  const voiceInterface = readVoiceInterfaceModules();
  const receptionGuide = readReceptionGuideModule();

  // アシスタント TTS は getTtsProvider() 経由（既定=piper、デモモード=kokoro）。
  // デモモード以外の本番経路が piper であることは getTtsProvider() の実装が保証する。
  assert.ok((voiceInterface.match(/getTtsProvider\(\)/g) ?? []).length >= 3);
  assert.ok(receptionGuide.includes("ttsProvider: 'piper'"));
});
