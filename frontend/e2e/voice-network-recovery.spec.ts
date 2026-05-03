import fs from 'node:fs';
import path from 'node:path';

import { expect, test, type Page, type Route } from '@playwright/test';

async function dismissInitialModal(page: Page) {
  const modal = page.getByRole('dialog');
  const closeButton = page.getByTestId('initial-settings-close');
  if (await closeButton.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await page.waitForTimeout(1_500);
    const deadline = Date.now() + 30_000;
    while (Date.now() < deadline && !(await modal.isHidden().catch(() => false))) {
      await closeButton.click({ timeout: 1_000, force: true }).catch(() => {});
      if (!(await modal.isHidden().catch(() => false))) {
        await closeButton
          .evaluate((button) => {
            if (button instanceof HTMLButtonElement) {
              button.click();
            }
          })
          .catch(() => {});
      }
      await page.waitForTimeout(250);
    }
    await expect(modal).toBeHidden({ timeout: 10_000 });
  }
  await expect(page.getByRole('button', { name: 'Welcome' })).toBeVisible({ timeout: 5_000 });
}

async function installDeterministicVoiceRecorder(page: Page) {
  const sampleAudioBase64 = fs
    .readFileSync(path.resolve(__dirname, 'fixtures/voice/sample.wav'))
    .toString('base64');

  await page.addInitScript(({ audioBase64 }) => {
    (window as Window & { __PLAYWRIGHT_VOICE_AUDIO_BASE64__?: string }).__PLAYWRIGHT_VOICE_AUDIO_BASE64__ =
      audioBase64;
  }, { audioBase64: sampleAudioBase64 });
}

function requestAction(route: Route): string {
  const raw = route.request().postData();
  if (!raw) return '';
  try {
    const parsed = JSON.parse(raw) as { action?: unknown };
    return typeof parsed.action === 'string' ? parsed.action : '';
  } catch {
    return '';
  }
}

test.describe('Voice network recovery (#584 F-1)', () => {
  test('STT network failure returns to idle and a second voice turn can succeed', async ({ page }) => {
    await installDeterministicVoiceRecorder(page);

    let sttAttempts = 0;

    await page.route('**/api/reception/start', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          reception_session_id: 'mock-network-recovery',
          greeting: 'テストです。',
          stage: 'greeting',
        }),
      });
    });

    await page.route('**/api/voice', async (route) => {
      const action = requestAction(route);
      if (action === 'speech_to_text') {
        sttAttempts += 1;
        if (sttAttempts === 1) {
          await route.abort('internetdisconnected');
          return;
        }
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            transcript: 'Engineer Cafe の Wi-Fi について教えてください。',
          }),
        });
        return;
      }

      if (action === 'warmup') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ success: true, sttWarmupStatus: 'ready' }),
        });
        return;
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true }),
      });
    });

    await page.route('**/api/voice/filler', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true }),
      });
    });

    await page.route('**/api/qa', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          answer: 'Engineer Cafe の Wi-Fi は受付で確認してください。',
          emotion: 'neutral',
          metadata: {},
        }),
      });
    });

    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await dismissInitialModal(page);

    const voiceButton = page.getByTestId('kiosk-voice-button');
    const voiceStatus = page.getByTestId('kiosk-voice-status');

    await voiceButton.click();
    await expect(voiceStatus).toHaveAttribute('data-session-state', 'listening', {
      timeout: 8_000,
    });
    await voiceButton.click();

    await expect(voiceStatus).toContainText(/ネットワーク|network/i, { timeout: 10_000 });
    await expect(voiceStatus).toHaveAttribute('data-session-state', 'idle', {
      timeout: 10_000,
    });
    await expect(voiceButton).toBeEnabled();
    await expect(voiceButton).not.toContainText(/録音中|Recording/);

    await voiceButton.click();
    await expect(voiceStatus).toHaveAttribute('data-session-state', 'listening', {
      timeout: 8_000,
    });
    await voiceButton.click();

    await expect(page.getByTestId('response-text')).toContainText(/Wi-Fi|Engineer Cafe/, {
      timeout: 15_000,
    });
    await expect(voiceStatus).toHaveAttribute('data-session-state', 'idle', {
      timeout: 15_000,
    });
    expect(sttAttempts).toBe(2);
  });
});
