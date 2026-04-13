import fs from 'node:fs';
import path from 'node:path';

import { expect, test, type Page, type Request } from '@playwright/test';

const voiceLive = process.env.PLAYWRIGHT_VOICE_LIVE === '1';

interface ObservedCall {
  url: string;
  action?: string;
  method: string;
}

function normalizeText(value: string | null | undefined): string {
  return (value ?? '')
    .replace(/\[\/?[a-zA-Z_]+(?::\d*\.?\d+)?\]/g, '')
    .replace(/^(応答|Response)\s*:\s*/i, '')
    .replace(/\s+/g, ' ')
    .trim();
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

async function selectEnglishAndClose(page: Page, timeout = 15_000): Promise<void> {
  const dialog = page.getByRole('dialog', { name: /初期設定|Initial Settings/i });
  await expect(dialog).toBeVisible({ timeout });
  await page.waitForTimeout(500);
  const closeButton = dialog.getByTestId('initial-settings-close');
  await expect(closeButton).toBeVisible({ timeout });
  await closeButton.click();
  await expect(dialog).toBeHidden({ timeout });
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

const ENGINEER_CAFE_PATTERN = /engineer\s*cafe|エンジニア\s*カフェ/i;

test.describe('Voice live (browser voice round-trip against live backend)', () => {
  test.skip(
    !voiceLive || !process.env.BACKEND_API_URL || !process.env.BACKEND_API_KEY,
    'Set PLAYWRIGHT_VOICE_LIVE=1 + BACKEND_API_URL + BACKEND_API_KEY to run live voice E2E.',
  );

  test('mic click drives STT → QA → TTS with live backend', async ({ page, context, baseURL }) => {
    test.setTimeout(240_000);

    await context.grantPermissions(['microphone'], {
      origin: baseURL ?? 'http://127.0.0.1:3000',
    });
    await installDeterministicVoiceRecorder(page);

    const apiCalls: ObservedCall[] = [];
    page.on('request', (request) => {
      const url = request.url();
      const method = request.method();
      if (method !== 'POST') return;
      if (!(url.includes('/api/voice') || url.includes('/api/qa'))) return;
      apiCalls.push({ url, method, action: parseAction(request) });
    });

    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await selectEnglishAndClose(page);

    const voiceButton = page.getByTestId('kiosk-voice-button');
    await expect(voiceButton).toBeVisible({ timeout: 15_000 });
    await expect(voiceButton).toBeEnabled();

    const responseText = page.getByTestId('response-text');
    await expect(responseText).toBeVisible();
    const baselineText = ((await responseText.textContent()) ?? '').trim();

    // Pre-arm the response waiters BEFORE clicking so fast backends can't race
    // us to the timeout threshold. Each promise resolves on the first matching
    // response; they must be awaited in order after the stop-click fires.
    const sttResponsePromise = page.waitForResponse(
      (response) =>
        response.url().includes('/api/voice') &&
        response.request().method() === 'POST' &&
        parseAction(response.request()) === 'speech_to_text',
      { timeout: 120_000 },
    );
    const qaResponsePromise = page.waitForResponse(
      (response) =>
        response.url().includes('/api/qa') && response.request().method() === 'POST',
      { timeout: 120_000 },
    );
    const ttsResponsePromise = page.waitForResponse(
      (response) =>
        response.url().includes('/api/voice') &&
        response.request().method() === 'POST' &&
        parseAction(response.request()) === 'text_to_speech',
      { timeout: 120_000 },
    );

    await voiceButton.click();
    await expect(page.getByTestId('kiosk-voice-status')).toHaveAttribute(
      'data-session-state',
      'listening',
      {
        timeout: 15_000,
      },
    );
    await expect(page.getByRole('button', { name: 'Welcome' })).toBeDisabled({
      timeout: 15_000,
    });
    const voiceStatus = page.getByTestId('kiosk-voice-status');
    await page.waitForTimeout(250);
    await voiceButton.click();

    const sttResponse = await sttResponsePromise;
    expect(sttResponse.ok()).toBeTruthy();
    const sttPayload = (await sttResponse.json().catch(() => null)) as {
      transcript?: unknown;
      success?: unknown;
    } | null;
    expect(sttPayload).not.toBeNull();
    expect(sttPayload?.success ?? true).not.toBe(false);
    const transcript = typeof sttPayload?.transcript === 'string' ? sttPayload.transcript : '';
    expect(transcript.length).toBeGreaterThan(5);
    expect(transcript).toMatch(ENGINEER_CAFE_PATTERN);

    const qaResponse = await qaResponsePromise;
    expect(qaResponse.ok()).toBeTruthy();
    const qaPayload = (await qaResponse.json().catch(() => null)) as {
      answer?: unknown;
      success?: unknown;
    } | null;
    expect(qaPayload).not.toBeNull();
    expect(qaPayload?.success ?? true).not.toBe(false);
    expect(typeof qaPayload?.answer === 'string' && qaPayload.answer.length > 0).toBe(true);
    const qaAnswer = normalizeText(typeof qaPayload?.answer === 'string' ? qaPayload.answer : '');
    expect(qaAnswer.length).toBeGreaterThan(20);
    expect(qaAnswer).toMatch(ENGINEER_CAFE_PATTERN);

    const ttsResponse = await ttsResponsePromise;
    expect(ttsResponse.ok()).toBeTruthy();
    const ttsPayload = (await ttsResponse.json().catch(() => null)) as {
      audioResponse?: unknown;
      success?: unknown;
    } | null;
    expect(ttsPayload).not.toBeNull();
    const audioResponse = ttsPayload?.audioResponse;
    expect(
      typeof audioResponse === 'string' && audioResponse.length > 0,
    ).toBe(true);

    await expect
      .poll(async () => ((await responseText.textContent()) ?? '').trim(), {
        timeout: 60_000,
      })
      .not.toBe(baselineText);

    const finalText = normalizeText((await responseText.textContent()) ?? '');
    expect(finalText.length).toBeGreaterThan(20);
    expect(finalText).toMatch(/[A-Za-z\u3040-\u30ff\u4e00-\u9fff]/);
    expect(finalText.toLowerCase()).not.toContain('internal server error');
    expect(finalText).not.toMatch(/stack trace|500 internal/i);
    expect(finalText).toMatch(ENGINEER_CAFE_PATTERN);
    expect(finalText).toBe(qaAnswer);

    // Session must return to idle after speaking. Unlike kioskVoiceLocked
    // (which is user-driven — it drops immediately on the stop click),
    // data-session-state reflects the VoiceInterface's actual lifecycle
    // and only flips back to 'idle' after STT → QA → TTS → playback
    // completes.
    await expect(voiceStatus).toHaveAttribute('data-session-state', 'idle', {
      timeout: 90_000,
    });
    await expect(voiceButton).toBeEnabled();

    const sttHit = apiCalls.find((call) => call.action === 'speech_to_text');
    const qaHit = apiCalls.find((call) => call.url.includes('/api/qa'));
    const ttsHit = apiCalls.find((call) => call.action === 'text_to_speech');
    expect(sttHit, 'speech_to_text request missing').toBeTruthy();
    expect(qaHit, '/api/qa request missing').toBeTruthy();
    expect(ttsHit, 'text_to_speech request missing').toBeTruthy();
  });
});
