import { expect, test, type Page } from '@playwright/test';

import {
  dismissInitialModal,
  installDeterministicVoiceRecorder,
  parseVoiceAction,
} from './helpers/voice';

const voiceLive = process.env.PLAYWRIGHT_VOICE_LIVE === '1';

interface ObservedCall {
  url: string;
  action?: string;
  method: string;
}

interface SttWarmupPayload {
  sttWarmupError?: unknown;
  sttWarmupProvider?: unknown;
  sttWarmupStatus?: unknown;
  success?: unknown;
}

function normalizeText(value: string | null | undefined): string {
  return (value ?? '')
    .replace(/\[\/?[a-zA-Z_]+(?::\d*\.?\d+)?\]/g, '')
    .replace(/^(応答|Response)\s*:\s*/i, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function parsePositiveInteger(value: string | undefined, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

async function warmupSttForLiveVoice(
  page: Page,
  baseURL: string | undefined,
  language: string,
): Promise<void> {
  const warmupTimeoutMs = parsePositiveInteger(
    process.env.PLAYWRIGHT_VOICE_LIVE_WARMUP_TIMEOUT_MS,
    60_000,
  );
  const requestTimeoutMs = Math.min(60_000, Math.max(10_000, warmupTimeoutMs));
  const deadline = Date.now() + warmupTimeoutMs;
  const voiceUrl = new URL('/api/voice', baseURL ?? 'http://127.0.0.1:3000').toString();
  const sessionId = `voice-live-warmup-${Date.now()}`;
  let lastStatus = 'not-started';
  let lastProvider = 'unknown';
  let lastError = '';

  while (Date.now() < deadline) {
    const response = await page.request.post(voiceUrl, {
      data: { action: 'warmup', language, sessionId },
      timeout: requestTimeoutMs,
    });
    expect(response.ok(), `STT warmup request failed with HTTP ${response.status()}`).toBeTruthy();

    const payload = (await response.json().catch(() => null)) as SttWarmupPayload | null;
    expect(payload, 'STT warmup response must be JSON').not.toBeNull();
    lastStatus =
      typeof payload?.sttWarmupStatus === 'string' ? payload.sttWarmupStatus : 'unknown';
    lastProvider =
      typeof payload?.sttWarmupProvider === 'string' ? payload.sttWarmupProvider : 'unknown';
    lastError = typeof payload?.sttWarmupError === 'string' ? payload.sttWarmupError : '';

    if (lastStatus === 'ready' || lastStatus === 'skipped') {
      return;
    }
    if (lastStatus === 'failed') {
      throw new Error(
        `STT warmup failed before voice-live test (provider=${lastProvider}, error=${lastError})`,
      );
    }

    await page.waitForTimeout(2_000);
  }

  throw new Error(
    `STT warmup did not become ready before voice-live test ` +
      `(lastStatus=${lastStatus}, provider=${lastProvider}, timeoutMs=${warmupTimeoutMs})`,
  );
}

async function readResponseText(page: Page): Promise<string> {
  const responseText = page.getByTestId('response-text');
  if ((await responseText.count()) === 0) {
    return '';
  }

  try {
    return ((await responseText.first().textContent({ timeout: 1_000 })) ?? '').trim();
  } catch {
    return '';
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
    await warmupSttForLiveVoice(page, baseURL, 'en');

    const apiCalls: ObservedCall[] = [];
    page.on('request', (request) => {
      const url = request.url();
      const method = request.method();
      if (method !== 'POST') return;
      if (!(url.includes('/api/voice') || url.includes('/api/qa'))) return;
      apiCalls.push({ url, method, action: parseVoiceAction(request) });
    });

    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await dismissInitialModal(page, {
      closeButtonTimeoutMs: 15_000,
      closeDelayMs: 500,
      hiddenTimeoutMs: 15_000,
      welcomeTimeoutMs: 15_000,
    });

    const voiceButton = page.getByTestId('kiosk-voice-button');
    await expect(voiceButton).toBeVisible({ timeout: 15_000 });
    await expect(voiceButton).toBeEnabled();

    await expect(page.getByTestId('response-text')).toBeVisible();
    const baselineText = await readResponseText(page);

    // Pre-arm the response waiters BEFORE clicking so fast backends can't race
    // us to the timeout threshold. Each promise resolves on the first matching
    // response; they must be awaited in order after the stop-click fires.
    const sttResponsePromise = page.waitForResponse(
      (response) =>
        response.url().includes('/api/voice') &&
        response.request().method() === 'POST' &&
        parseVoiceAction(response.request()) === 'speech_to_text',
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
        parseVoiceAction(response.request()) === 'text_to_speech',
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

    let finalText = '';
    await expect
      .poll(
        async () => {
          const currentText = await readResponseText(page);
          finalText = normalizeText(currentText);
          return currentText && currentText !== baselineText ? finalText : '';
        },
        { timeout: 90_000 },
      )
      .toBe(qaAnswer);

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
