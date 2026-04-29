import fs from 'node:fs';
import path from 'node:path';

import { expect, test, type Page, type Request } from '@playwright/test';

const welcomeLive = process.env.PLAYWRIGHT_WELCOME_LIVE === '1';
const voiceDelays = (process.env.PLAYWRIGHT_WELCOME_VOICE_DELAYS ?? '0,5,10')
  .split(',')
  .map((value) => Number.parseInt(value.trim(), 10))
  .filter((value) => Number.isFinite(value) && value >= 0);

interface ObservedCall {
  action?: string;
  durationMs?: number;
  method: string;
  startedAt: number;
  status?: number;
  url: string;
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

async function installDeterministicVoiceRecorder(page: Page): Promise<void> {
  const sampleAudioBase64 = fs
    .readFileSync(path.resolve(__dirname, 'fixtures/voice/sample.wav'))
    .toString('base64');

  await page.addInitScript(({ audioBase64 }) => {
    (
      window as Window & { __PLAYWRIGHT_VOICE_AUDIO_BASE64__?: string }
    ).__PLAYWRIGHT_VOICE_AUDIO_BASE64__ = audioBase64;
  }, { audioBase64: sampleAudioBase64 });
}

async function keepOcrCameraPending(page: Page): Promise<void> {
  await page.addInitScript(() => {
    window.localStorage.setItem('engineer_cafe_kiosk_mic_mode', 'toggle');
    window.localStorage.setItem('engineer_cafe_kiosk_trigger_mode', 'screen');
    if (!navigator.mediaDevices) {
      return;
    }
    navigator.mediaDevices.getUserMedia = async (constraints?: MediaStreamConstraints) => {
      if (constraints?.video) {
        return new Promise<MediaStream>(() => {});
      }
      return new MediaStream();
    };
  });
}

async function closeInitialSettings(page: Page): Promise<void> {
  const closeButton = page.getByTestId('initial-settings-close');
  if (await closeButton.isVisible({ timeout: 15_000 }).catch(() => false)) {
    await closeButton.click();
  }
  await expect(page.getByRole('button', { name: 'Welcome' })).toBeVisible({ timeout: 15_000 });
}

function observeApiCalls(page: Page): ObservedCall[] {
  const calls: ObservedCall[] = [];
  const byRequest = new WeakMap<Request, ObservedCall>();

  page.on('request', (request) => {
    const method = request.method();
    const url = request.url();
    if (method !== 'POST') return;
    if (!(url.includes('/api/voice') || url.includes('/api/reception/start') || url.includes('/api/qa'))) {
      return;
    }
    const call: ObservedCall = {
      action: parseAction(request),
      method,
      startedAt: Date.now(),
      url,
    };
    calls.push(call);
    byRequest.set(request, call);
  });

  page.on('response', (response) => {
    const request = response.request();
    const call = byRequest.get(request);
    if (!call) return;
    call.status = response.status();
    call.durationMs = Date.now() - call.startedAt;
  });

  return calls;
}

async function setupWelcomeLivePage(page: Page): Promise<ObservedCall[]> {
  await keepOcrCameraPending(page);
  await installDeterministicVoiceRecorder(page);
  const calls = observeApiCalls(page);
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await closeInitialSettings(page);
  return calls;
}

function firstCall(calls: ObservedCall[], predicate: (call: ObservedCall) => boolean) {
  return calls.find(predicate);
}

async function triggerVoiceTurn(page: Page): Promise<void> {
  const voiceButton = page.getByTestId('kiosk-voice-button');
  await expect(voiceButton).toBeVisible({ timeout: 15_000 });
  await expect(voiceButton).toBeEnabled({ timeout: 15_000 });
  await voiceButton.scrollIntoViewIfNeeded();
  const voiceStatus = page.getByTestId('kiosk-voice-status');

  await voiceButton.click();
  await expect(voiceStatus).toHaveAttribute('data-session-state', 'listening', {
    timeout: 15_000,
  });
  await page.waitForTimeout(1_400);
  await voiceButton.click();
  await expect(voiceStatus).toHaveAttribute('data-session-state', /processing|speaking|idle/, {
    timeout: 15_000,
  });
}

test.describe('Welcome live (Welcome → OCR → STT warmup → first voice)', () => {
  test.skip(
    !welcomeLive || !process.env.BACKEND_API_URL || !process.env.BACKEND_API_KEY,
    'Set PLAYWRIGHT_WELCOME_LIVE=1 + BACKEND_API_URL + BACKEND_API_KEY to run welcome live E2E.',
  );

  test('Welcome starts STT warmup while greeting TTS and OCR sidecar are active', async ({
    page,
  }) => {
    test.setTimeout(180_000);
    const calls = await setupWelcomeLivePage(page);

    const warmupResponse = page.waitForResponse(
      (response) =>
        response.url().includes('/api/voice') &&
        parseAction(response.request()) === 'warmup',
      { timeout: 90_000 },
    );
    const ttsResponse = page.waitForResponse(
      (response) =>
        response.url().includes('/api/voice') &&
        parseAction(response.request()) === 'text_to_speech',
      { timeout: 120_000 },
    );
    const receptionResponse = page.waitForResponse(
      (response) => response.url().includes('/api/reception/start'),
      { timeout: 90_000 },
    );

    await page.getByRole('button', { name: 'Welcome' }).click();

    const [warmup, reception, tts] = await Promise.all([
      warmupResponse,
      receptionResponse,
      ttsResponse,
    ]);
    expect(warmup.ok(), 'warmup response').toBeTruthy();
    expect(reception.ok(), 'reception start response').toBeTruthy();
    expect(tts.ok(), 'greeting TTS response').toBeTruthy();
    await expect(page.getByTestId('kiosk-welcome-ocr-overlay')).toBeVisible({
      timeout: 15_000,
    });

    const warmupCall = firstCall(calls, (call) => call.action === 'warmup');
    const ttsCall = firstCall(calls, (call) => call.action === 'text_to_speech');
    const receptionCall = firstCall(calls, (call) => call.url.includes('/api/reception/start'));
    expect(warmupCall, 'warmup request missing').toBeTruthy();
    expect(ttsCall, 'greeting TTS request missing').toBeTruthy();
    expect(receptionCall, 'reception request missing').toBeTruthy();
    expect(warmupCall!.startedAt).toBeLessThanOrEqual(ttsCall!.startedAt);
  });

  for (const delaySeconds of voiceDelays.length > 0 ? voiceDelays : [0]) {
    test(`first voice turn after Welcome + ${delaySeconds}s reaches STT → QA → TTS`, async ({
      page,
    }) => {
      test.setTimeout(240_000 + delaySeconds * 1000);
      const calls = await setupWelcomeLivePage(page);

      const warmupResponse = page.waitForResponse(
        (response) =>
          response.url().includes('/api/voice') &&
          parseAction(response.request()) === 'warmup',
        { timeout: 90_000 },
      );

      await page.getByRole('button', { name: 'Welcome' }).click();
      const warmup = await warmupResponse;
      expect(warmup.ok(), 'warmup response').toBeTruthy();
      await expect(page.getByTestId('kiosk-welcome-ocr-overlay')).toBeVisible({
        timeout: 15_000,
      });

      if (delaySeconds > 0) {
        await page.waitForTimeout(delaySeconds * 1000);
      }

      const sttResponse = page.waitForResponse(
        (response) =>
          response.url().includes('/api/voice') &&
          parseAction(response.request()) === 'speech_to_text',
        { timeout: 120_000 },
      );
      const qaResponse = page.waitForResponse(
        (response) => response.url().includes('/api/qa') && response.request().method() === 'POST',
        { timeout: 120_000 },
      );
      const ttsResponse = page.waitForResponse(
        (response) =>
          response.url().includes('/api/voice') &&
          parseAction(response.request()) === 'text_to_speech',
        { timeout: 120_000 },
      );

      await triggerVoiceTurn(page);

      const [stt, qa, tts] = await Promise.all([sttResponse, qaResponse, ttsResponse]);
      expect(stt.ok(), 'speech_to_text response').toBeTruthy();
      expect(qa.ok(), 'QA response').toBeTruthy();
      expect(tts.ok(), 'answer TTS response').toBeTruthy();

      const sttPayload = (await stt.json().catch(() => null)) as {
        transcript?: unknown;
        success?: unknown;
      } | null;
      expect(sttPayload?.success ?? true).not.toBe(false);
      expect(typeof sttPayload?.transcript === 'string' && sttPayload.transcript.length > 5).toBe(
        true,
      );

      const sttCall = firstCall(calls, (call) => call.action === 'speech_to_text');
      const qaCall = firstCall(calls, (call) => call.url.includes('/api/qa'));
      const warmupCall = firstCall(calls, (call) => call.action === 'warmup');
      expect(warmupCall, 'warmup request missing').toBeTruthy();
      expect(sttCall, 'speech_to_text request missing').toBeTruthy();
      expect(qaCall, 'QA request missing').toBeTruthy();
      expect(sttCall!.startedAt).toBeGreaterThanOrEqual(warmupCall!.startedAt);
    });
  }
});
