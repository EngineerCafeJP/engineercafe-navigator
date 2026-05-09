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

  await page.addInitScript(
    ({ audioBase64 }) => {
      (
        window as Window & { __PLAYWRIGHT_VOICE_AUDIO_BASE64__?: string }
      ).__PLAYWRIGHT_VOICE_AUDIO_BASE64__ = audioBase64;
    },
    { audioBase64: sampleAudioBase64 },
  );
}

function readJsonBody(route: Route): Record<string, unknown> {
  const raw = route.request().postData();
  if (!raw) {
    return {};
  }

  try {
    return JSON.parse(raw) as Record<string, unknown>;
  } catch {
    return {};
  }
}

async function runVoiceTurn(page: Page, qaCount: () => number, expectedQaCount: number) {
  const voiceButton = page.getByTestId('kiosk-voice-button');
  const voiceStatus = page.getByTestId('kiosk-voice-status');

  await expect(voiceButton).toBeEnabled({ timeout: 15_000 });
  await voiceButton.click();
  await expect(voiceStatus).toHaveAttribute('data-session-state', 'listening', {
    timeout: 8_000,
  });
  await voiceButton.click();

  await expect.poll(qaCount, { timeout: 15_000 }).toBe(expectedQaCount);
  await expect(voiceStatus).toHaveAttribute('data-session-state', 'idle', {
    timeout: 15_000,
  });
}

test.describe('Voice session contract (#801 FE)', () => {
  test('uses one sessionId for sequential STT to QA cafe follow-ups', async ({ page }) => {
    await installDeterministicVoiceRecorder(page);

    const transcripts = ['エンジニアカフェの営業時間', '隣のカフェは？'];
    const sttBodies: Record<string, unknown>[] = [];
    const qaBodies: Record<string, unknown>[] = [];
    const ttsBodies: Record<string, unknown>[] = [];
    let sttCount = 0;

    await page.route('**/api/reception/start', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          reception_session_id: 'mock-session-contract',
          greeting: 'ようこそ。',
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

    await page.route('**/api/character**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, vrm_control: null }),
      });
    });

    await page.route('**/api/voice', async (route) => {
      const body = readJsonBody(route);

      if (body.action === 'speech_to_text') {
        sttBodies.push(body);
        const transcript = transcripts[sttCount] ?? transcripts[transcripts.length - 1];
        sttCount += 1;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ success: true, transcript }),
        });
        return;
      }

      if (body.action === 'text_to_speech') {
        ttsBodies.push(body);
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ success: true }),
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
      const body = readJsonBody(route);
      qaBodies.push(body);
      const answer =
        body.question === transcripts[1]
          ? '隣のカフェは Cafe & Bar Saino です。'
          : 'エンジニアカフェの営業時間は10時から22時です。';

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          answer,
          emotion: 'neutral',
          metadata: {},
        }),
      });
    });

    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await dismissInitialModal(page);

    await runVoiceTurn(page, () => qaBodies.length, 1);
    await runVoiceTurn(page, () => qaBodies.length, 2);

    expect(sttCount).toBe(2);
    expect(qaBodies).toHaveLength(2);
    expect(qaBodies.map((body) => body.action)).toEqual(['ask', 'ask']);
    expect(qaBodies.map((body) => body.question)).toEqual(transcripts);
    expect(qaBodies.map((body) => body.text)).toEqual(transcripts);
    expect(qaBodies.map((body) => body.language)).toEqual(['ja', 'ja']);
    expect(qaBodies.some((body) => 'history' in body || 'messages' in body)).toBe(false);

    const sessionId = qaBodies[0]?.sessionId;
    expect(typeof sessionId).toBe('string');
    expect(sessionId).not.toBe('');
    expect(qaBodies[1]?.sessionId).toBe(sessionId);
    expect(sttBodies.map((body) => body.sessionId)).toEqual([sessionId, sessionId]);
    expect(ttsBodies.map((body) => body.sessionId)).toEqual([sessionId, sessionId]);
  });
});
