import fs from 'node:fs';
import path from 'node:path';

import { expect, test } from '@playwright/test';

/**
 * Alpha #638 — getUserMedia rejection UX (WebKit project in playwright.config).
 */

async function dismissInitialModal(page: import('@playwright/test').Page) {
  const modal = page.getByRole('dialog');
  const closeButton = page.getByTestId('initial-settings-close');
  if (await closeButton.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await closeButton.click({ force: true }).catch(() => {});
    await expect(modal).toBeHidden({ timeout: 10_000 });
  }
  await expect(page.getByRole('button', { name: 'Welcome' })).toBeVisible({ timeout: 5_000 });
}

async function installMicDenial(page: import('@playwright/test').Page, errorName: string) {
  await page.addInitScript((name: string) => {
    (window as Window & { __PLAYWRIGHT_VOICE_RECORDER_ERROR_NAME__?: string }).__PLAYWRIGHT_VOICE_RECORDER_ERROR_NAME__ =
      name;
  }, errorName);
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

async function installIOSUserAgent(page: import('@playwright/test').Page) {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'userAgent', {
      configurable: true,
      value:
        'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
    });
    Object.defineProperty(navigator, 'maxTouchPoints', {
      configurable: true,
      value: 5,
    });
  });
}

test.describe('Microphone permission denial (#638)', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/reception/start', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          reception_session_id: 'mock-permission',
          greeting: 'テストです。',
          stage: 'greeting',
        }),
      });
    });
    await page.route('**/api/voice', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true }),
      });
    });
  });

  async function assertMicDeniedRecovery(page: import('@playwright/test').Page) {
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await dismissInitialModal(page);

    const voiceButton = page.getByTestId('kiosk-voice-button');
    await voiceButton.click();

    await expect(page.getByTestId('kiosk-voice-status')).toContainText(/マイク|Microphone|HTTPS|許可|permission/i, {
      timeout: 8_000,
    });

    await expect.poll(async () => (await voiceButton.textContent()) ?? '').not.toMatch(/録音中|Recording/, {
      timeout: 8_000,
    });
  }

  test('NotFoundError while response-prep recovers to an enabled idle UI', async ({ page }) => {
    await installIOSUserAgent(page);
    await installDeterministicVoiceRecorder(page);

    let releaseQa: (() => void) | null = null;
    const qaRequested = new Promise<void>((resolve) => {
      releaseQa = resolve;
    });

    await page.route('**/api/voice/filler', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true }),
      });
    });

    await page.route('**/api/voice', async (route) => {
      const raw = route.request().postData();
      const action = raw ? (JSON.parse(raw) as { action?: string }).action : '';
      if (action === 'speech_to_text') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            transcript: 'Engineer Cafe の設備を教えてください。',
          }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, sttWarmupStatus: 'ready' }),
      });
    });

    await page.route('**/api/qa', async (route) => {
      releaseQa?.();
      await new Promise<void>((resolve) => {
        releaseQa = resolve;
      });
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          answer: 'Engineer Cafe の設備案内です。',
          emotion: 'neutral',
          metadata: {},
        }),
      }).catch(() => {});
    });

    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await dismissInitialModal(page);

    const voiceButton = page.getByTestId('kiosk-voice-button');
    const voiceStatus = page.getByTestId('kiosk-voice-status');
    const welcomeButton = page.getByRole('button', { name: 'Welcome' });

    await voiceButton.click();
    await expect(voiceStatus).toHaveAttribute('data-session-state', 'listening', {
      timeout: 8_000,
    });
    await voiceButton.dispatchEvent('click');
    await qaRequested;

    await expect(voiceStatus).toContainText(/応答を準備|Preparing an answer/, {
      timeout: 8_000,
    });
    await expect(voiceButton).toBeEnabled();
    await expect(welcomeButton).toBeEnabled();

    await page.waitForTimeout(500);
    await page.evaluate(() => {
      (window as Window & { __PLAYWRIGHT_VOICE_RECORDER_ERROR_NAME__?: string }).__PLAYWRIGHT_VOICE_RECORDER_ERROR_NAME__ =
        'NotFoundError';
    });
    await voiceButton.click();

    await expect(voiceStatus).toContainText(/画面録画|Settings.*Safari|マイク|microphone/i, {
      timeout: 8_000,
    });
    await expect(voiceStatus).toHaveAttribute('data-session-state', 'idle', {
      timeout: 8_000,
    });
    await expect(voiceButton).toBeEnabled();
    await expect(voiceButton).not.toContainText(/録音中|Recording/);
    await expect(welcomeButton).toBeEnabled();

    releaseQa?.();
  });

  test('NotAllowedError shows guidance and clears recording affordance', async ({ page }) => {
    await installMicDenial(page, 'NotAllowedError');
    await assertMicDeniedRecovery(page);
  });

  test('NotFoundError shows guidance', async ({ page }) => {
    await installMicDenial(page, 'NotFoundError');
    await assertMicDeniedRecovery(page);
  });

  test('InvalidStateError shows guidance', async ({ page }) => {
    await installMicDenial(page, 'InvalidStateError');
    await assertMicDeniedRecovery(page);
  });

  test('SecurityError shows HTTPS guidance', async ({ page }) => {
    await installMicDenial(page, 'SecurityError');
    await assertMicDeniedRecovery(page);
  });
});
