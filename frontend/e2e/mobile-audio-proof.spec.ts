import fs from 'node:fs';
import path from 'node:path';

import { expect, test, type Page, type Request } from '@playwright/test';

import { MOCK_VOICE_RESPONSE, setupWebAudioMock } from './helpers/mocks';

interface ObservedCalls {
  stt: number;
  qa: number;
  tts: number;
}

async function installDeterministicVoiceRecorder(page: Page): Promise<void> {
  const sampleAudioBase64 = fs
    .readFileSync(path.resolve(__dirname, 'fixtures/voice/sample.wav'))
    .toString('base64');

  await page.addInitScript(({ audioBase64 }) => {
    (window as Window & { __PLAYWRIGHT_VOICE_AUDIO_BASE64__?: string }).__PLAYWRIGHT_VOICE_AUDIO_BASE64__ =
      audioBase64;
  }, { audioBase64: sampleAudioBase64 });
}

async function installAudioProofCounters(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const proof = {
      interactionRequired: 0,
    };
    (window as Window & { __MOBILE_AUDIO_PROOF__?: typeof proof }).__MOBILE_AUDIO_PROOF__ = proof;
    window.addEventListener('engineer-cafe:audio-interaction-required', () => {
      proof.interactionRequired += 1;
    });
  });
}

function parseAction(request: Request): string | undefined {
  const raw = request.postData();
  if (!raw) return undefined;
  try {
    const parsed = JSON.parse(raw) as { action?: unknown };
    return typeof parsed.action === 'string' ? parsed.action : undefined;
  } catch {
    return undefined;
  }
}

async function dismissInitialModal(page: Page): Promise<void> {
  const closeButton = page.getByTestId('initial-settings-close');
  if (await closeButton.isVisible({ timeout: 10_000 }).catch(() => false)) {
    await closeButton.click();
  }
  await expect(page.getByRole('button', { name: 'Welcome' })).toBeVisible({ timeout: 15_000 });
}

async function getAudioStarts(page: Page): Promise<number> {
  return page.evaluate(() => {
    return (window as Window & { __PLAYWRIGHT_AUDIO_STARTS__?: number }).__PLAYWRIGHT_AUDIO_STARTS__ ?? 0;
  });
}

async function getInteractionRequiredCount(page: Page): Promise<number> {
  return page.evaluate(() => {
    return (
      (window as Window & { __MOBILE_AUDIO_PROOF__?: { interactionRequired: number } })
        .__MOBILE_AUDIO_PROOF__?.interactionRequired ?? 0
    );
  });
}

test.describe('Mobile audio proof', () => {
  test('iPhone WebKit completes 10 voice turns without silent audio interaction failures', async ({
    page,
  }) => {
    test.setTimeout(180_000);

    const calls: ObservedCalls = { stt: 0, qa: 0, tts: 0 };

    await installAudioProofCounters(page);
    await setupWebAudioMock(page);
    await installDeterministicVoiceRecorder(page);

    await page.route('**/api/reception/start', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          reception_session_id: 'mobile-audio-proof',
          greeting: 'Welcome to Engineer Cafe.',
          stage: 'greeting',
        }),
      });
    });

    await page.route('**/api/voice/filler', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true }),
      });
    });

    await page.route('**/api/voice', async (route) => {
      const action = parseAction(route.request());
      if (action === 'speech_to_text') {
        calls.stt += 1;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            transcript: `Engineer Cafe mobile audio proof turn ${calls.stt}`,
          }),
        });
        return;
      }

      if (action === 'text_to_speech') {
        calls.tts += 1;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_VOICE_RESPONSE),
        });
        return;
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, sttWarmupStatus: 'skipped' }),
      });
    });

    await page.route('**/api/character', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, vrm_control: null }),
      });
    });

    await page.route('**/api/qa', async (route) => {
      calls.qa += 1;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          answer: `Turn ${calls.qa}: Engineer Cafe mobile audio proof response.`,
          emotion: 'neutral',
          metadata: {},
        }),
      });
    });

    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await dismissInitialModal(page);

    const voiceButton = page.getByTestId('kiosk-voice-button');
    const voiceStatus = page.getByTestId('kiosk-voice-status');
    await expect(voiceButton).toBeVisible({ timeout: 15_000 });
    await expect(voiceButton).toBeEnabled();

    const audioStartsAtBaseline = await getAudioStarts(page);

    for (let turn = 1; turn <= 10; turn += 1) {
      await voiceButton.click();
      await expect(voiceStatus).toHaveAttribute('data-session-state', 'listening', {
        timeout: 15_000,
      });

      await page.waitForTimeout(250);
      await voiceButton.dispatchEvent('click');

      await expect(page.getByTestId('response-text')).toContainText(`Turn ${turn}:`, {
        timeout: 30_000,
      });
      await expect(voiceStatus).toHaveAttribute('data-session-state', 'idle', {
        timeout: 30_000,
      });
      await expect(voiceButton).toBeEnabled();
      await expect
        .poll(() => getAudioStarts(page), { timeout: 10_000 })
        .toBeGreaterThanOrEqual(audioStartsAtBaseline + turn);
      await expect(page.getByTestId('audio-interaction-toast')).toHaveCount(0);
      expect(await getInteractionRequiredCount(page)).toBe(0);
      if (turn < 10) {
        await page.waitForTimeout(500);
      }
    }

    expect(calls.stt).toBe(10);
    expect(calls.qa).toBe(10);
    expect(calls.tts).toBe(10);
  });
});
