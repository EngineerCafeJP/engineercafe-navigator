import { expect, test, type Page } from '@playwright/test';

import {
  dismissInitialModal,
  failUnexpectedVoiceAction,
  installDeterministicVoiceRecorder,
  installIOSUserAgent,
  installMicDenial,
  parseVoiceAction,
} from './helpers/voice';

/**
 * Alpha #638 — getUserMedia rejection UX (WebKit project in playwright.config).
 */

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
      const action = parseVoiceAction(route.request());

      if (
        action === 'warmup' ||
        action === 'speech_to_text' ||
        action === 'text_to_speech' ||
        action === 'interrupt'
      ) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ success: true }),
        });
        return;
      }

      await failUnexpectedVoiceAction(route, action, [
        'warmup',
        'speech_to_text',
        'text_to_speech',
        'interrupt',
      ]);
    });
  });

  async function assertMicDeniedRecovery(page: Page) {
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
      const action = parseVoiceAction(route.request());
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

      if (action === 'warmup' || action === 'text_to_speech' || action === 'interrupt') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ success: true, sttWarmupStatus: 'ready' }),
        });
        return;
      }

      await failUnexpectedVoiceAction(route, action, [
        'speech_to_text',
        'warmup',
        'text_to_speech',
        'interrupt',
      ]);
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
