import fs from 'node:fs';
import path from 'node:path';

import { expect, test } from '@playwright/test';

import { m5stackPayloads } from './fixtures/m5stack-payloads';

/**
 * M5Stack sensor webhook → backend → kiosk sensor polling → Welcome flow (Refs #585 / #706).
 *
 * POST /api/reception/sensor-trigger targets BACKEND_API_URL directly (no Next.js proxy route).
 * The kiosk polls /api/reception/sensor-status via the frontend and dispatches device-detection.
 */

test.describe.configure({ mode: 'serial' });

const RECEPTION_START_URL = '/api/reception/start';
const QA_CHAT_URL = '/api/qa';

function backendTriggerUrl(): string {
  const base = (process.env.BACKEND_API_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '');
  return `${base}/api/reception/sensor-trigger`;
}

function backendRequestHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  const key = process.env.BACKEND_API_KEY;
  if (key) {
    headers['X-API-Key'] = key;
  }
  return headers;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function dismissInitialModal(page: import('@playwright/test').Page) {
  const modal = page.getByRole('dialog');
  const closeButton = page.getByTestId('initial-settings-close');
  if (await closeButton.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await page.waitForTimeout(1_500);
    const deadline = Date.now() + 30_000;
    while (Date.now() < deadline && !(await modal.isHidden().catch(() => false))) {
      await closeButton.click({ timeout: 1_000, force: true }).catch(() => {});
      if (!(await modal.isHidden().catch(() => false))) {
        await closeButton.evaluate((button) => {
          if (button instanceof HTMLButtonElement) {
            button.click();
          }
        }).catch(() => {});
      }
      await page.waitForTimeout(250);
    }
    await expect(modal).toBeHidden({ timeout: 10_000 });
  }
  await expect(page.getByTestId('kiosk-voice-button')).toBeVisible({ timeout: 5_000 });
}

function mockReceptionStart(page: import('@playwright/test').Page) {
  return page.route(`**${RECEPTION_START_URL}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        reception_session_id: 'mock-reception-m5stack-e2e',
        greeting: 'エンジニアカフェへようこそ！ご用件をお聞かせください。',
        stage: 'greeting',
      }),
    });
  });
}

async function keepOcrCameraPending(page: import('@playwright/test').Page) {
  await page.addInitScript(() => {
    const mediaDevices = navigator.mediaDevices;
    if (!mediaDevices) {
      return;
    }
    mediaDevices.getUserMedia = async () =>
      new Promise<MediaStream>(() => {
        /* keep OCR from opening a real camera */
      });
  });
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

test.describe('M5Stack reception sensor webhook (API + kiosk polling)', () => {
  test('happy path: sensor-trigger accepted then Welcome narration appears', async ({
    page,
    request,
  }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem('engineer_cafe_kiosk_trigger_mode', 'device');
    });
    await installDeterministicVoiceRecorder(page);
    await keepOcrCameraPending(page);
    await mockReceptionStart(page);
    await page.route(`**${QA_CHAT_URL}`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ answer: 'テスト応答', emotion: 'neutral', metadata: {} }),
      });
    });
    await page.route('**/api/voice', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true }),
      });
    });

    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await dismissInitialModal(page);

    const triggerUrl = backendTriggerUrl();
    const res = await request.post(triggerUrl, {
      data: m5stackPayloads.tofClose,
      headers: backendRequestHeaders(),
    });
    expect(res.status(), await res.text()).toBe(200);
    const body = (await res.json()) as { success: boolean; action: string };
    expect(body.success).toBe(true);
    expect(body.action).toBe('trigger_received');

    await expect(page.getByTestId('kiosk-welcome-ocr-overlay')).toBeHidden({ timeout: 8_000 });
    await expect(page.getByTestId('response-text')).toContainText('エンジニアカフェへようこそ', {
      timeout: 15_000,
    });
  });

  test('schema validation: missing sensor_type and too-long sensor_type return 422', async ({
    request,
  }) => {
    const headers = backendRequestHeaders();
    const url = backendTriggerUrl();

    const missingType = await request.post(url, {
      data: { distance_mm: 350, device_id: 'm5stack-schema-missing-type' },
      headers,
    });
    expect(missingType.status()).toBe(422);

    const longType = await request.post(url, {
      data: m5stackPayloads.invalidLongSensorType,
      headers,
    });
    expect(longType.status()).toBe(422);
  });

  test('rate limit: rapid same-device triggers then success after cooldown', async ({
    request,
  }) => {
    const headers = backendRequestHeaders();
    const url = backendTriggerUrl();
    const payload = m5stackPayloads.rateLimitDevice;

    const first = await request.post(url, { data: payload, headers });
    expect(first.status(), await first.text()).toBe(200);
    expect((await first.json()) as { success: boolean }).toEqual(
      expect.objectContaining({ success: true, action: 'trigger_received' }),
    );

    await sleep(100);

    const second = await request.post(url, { data: payload, headers });
    expect(second.status(), await second.text()).toBe(200);
    const secondJson = (await second.json()) as { success: boolean; action: string };
    expect(secondJson.success).toBe(false);
    expect(secondJson.action).toBe('rate_limited');

    await sleep(6_000);

    const third = await request.post(url, { data: payload, headers });
    expect(third.status(), await third.text()).toBe(200);
    expect((await third.json()) as { success: boolean }).toEqual(
      expect.objectContaining({ success: true, action: 'trigger_received' }),
    );
  });
});
