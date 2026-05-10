import { expect, test } from '@playwright/test';

import {
  dismissInitialModal,
  failUnexpectedVoiceAction,
  installDeterministicVoiceRecorder,
  parseVoiceAction,
} from './helpers/voice';

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
      const action = parseVoiceAction(route.request());
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

      if (action === 'text_to_speech' || action === 'interrupt') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ success: true }),
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
