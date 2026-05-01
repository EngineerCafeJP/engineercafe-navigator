import fs from 'node:fs';
import path from 'node:path';

import { expect, test } from '@playwright/test';

async function dismissInitialModal(page: import('@playwright/test').Page) {
  const modal = page.getByRole('dialog');
  const closeButton = page.getByTestId('initial-settings-close');
  if (await closeButton.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await closeButton.click({ force: true }).catch(() => {});
    await expect(modal).toBeHidden({ timeout: 10_000 });
  }
  await expect(page.getByRole('button', { name: 'Welcome' })).toBeVisible({ timeout: 5_000 });
}

async function installDeterministicVoiceRecorder(page: import('@playwright/test').Page) {
  const sampleAudioBase64 = fs
    .readFileSync(path.resolve(__dirname, 'fixtures/voice/sample.wav'))
    .toString('base64');

  await page.addInitScript(({ audioBase64 }) => {
    (window as Window & { __PLAYWRIGHT_VOICE_AUDIO_BASE64__?: string }).__PLAYWRIGHT_VOICE_AUDIO_BASE64__ =
      audioBase64;
  }, { audioBase64: sampleAudioBase64 });
}

test.describe('Parallel voice filler (#610 FE)', () => {
  test('STT completion hits /api/voice/filler while QA runs', async ({ page }) => {
    let ttsHits = 0;
    await installDeterministicVoiceRecorder(page);

    await page.route('**/api/reception/start', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          reception_session_id: 'mock-filler',
          greeting: 'ようこそ。',
          stage: 'greeting',
        }),
      });
    });

    await page.route(
      (url) => url.pathname === '/api/qa',
      async (route) => {
        await new Promise((r) => setTimeout(r, 120));
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            answer: 'テスト応答です。',
            emotion: 'neutral',
            metadata: {},
          }),
        });
      },
    );

    const wavB64 = fs.readFileSync(path.resolve(__dirname, 'fixtures/voice/sample.wav')).toString('base64');

    let fillerHits = 0;
    await page.route('**/api/voice/filler', async (route) => {
      fillerHits++;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          audioResponse: wavB64,
          intent: 'general',
          audioFormat: 'audio/wav',
          fillerText: '',
          source: 'static',
        }),
      });
    });

    await page.route('**/api/voice', async (route) => {
      const req = route.request();
      if (req.method() !== 'POST') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
        return;
      }
      let body: Record<string, unknown> = {};
      try {
        body = req.postDataJSON() as Record<string, unknown>;
      } catch {
        body = {};
      }
      if (body.action === 'speech_to_text') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ success: true, transcript: '営業時間は？' }),
        });
        return;
      }
      if (body.action === 'text_to_speech') {
        ttsHits++;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ success: true, audioResponse: wavB64 }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true }),
      });
    });

    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await dismissInitialModal(page);

    const voiceBtn = page.getByTestId('kiosk-voice-button');
    await expect(voiceBtn).toBeVisible({ timeout: 15_000 });
    await voiceBtn.click();
    await page.waitForTimeout(1200);
    await voiceBtn.click();

    await expect.poll(() => fillerHits, { timeout: 20_000 }).toBeGreaterThan(0);
    await expect.poll(() => ttsHits, { timeout: 25_000 }).toBeGreaterThan(0);
  });
});
