import { expect, test, type Page, type Route } from '@playwright/test';

import { MOCK_VOICE_RESPONSE } from './helpers/mocks';
import {
  dismissInitialModal,
  failUnexpectedVoiceAction,
  installDeterministicVoiceRecorder,
  parseVoiceAction,
} from './helpers/voice';

interface AudioProofCounters {
  starts: number;
  ended: number;
  playbackStartFailures: number;
  fallbackSpeech: number;
  interactionRequired: number;
  contexts: number;
  resumes: number;
}

interface VoiceCallCounts {
  stt: number;
  qa: number;
  tts: number;
}

type TtsMode = 'success' | 'tts-error' | 'invalid-audio';

declare global {
  interface Window {
    __THEME_B_AUDIO_PROOF__?: AudioProofCounters;
    __THEME_B_AUDIO_FAIL_NEXT_PLAYBACK_START__?: number;
  }
}

async function installThemeBAudioHarness(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const counters: AudioProofCounters = {
      starts: 0,
      ended: 0,
      playbackStartFailures: 0,
      fallbackSpeech: 0,
      interactionRequired: 0,
      contexts: 0,
      resumes: 0,
    };

    window.__THEME_B_AUDIO_PROOF__ = counters;

    window.addEventListener('engineer-cafe:audio-interaction-required', () => {
      counters.interactionRequired += 1;
    });

    class MockAudioBuffer {
      duration = 0.01;
      length: number;
      numberOfChannels = 1;
      sampleRate = 44100;

      constructor(length = 441) {
        this.length = length;
      }

      getChannelData() {
        return new Float32Array(this.length);
      }

      copyFromChannel() {}
      copyToChannel() {}
    }

    class MockBufferSource {
      buffer: MockAudioBuffer | null = null;
      onended: (() => void) | null = null;

      connect() {
        return this;
      }

      start() {
        const isSilentWarmupBuffer = this.buffer?.length === 1;
        const pendingFailures = window.__THEME_B_AUDIO_FAIL_NEXT_PLAYBACK_START__ ?? 0;
        if (!isSilentWarmupBuffer && pendingFailures > 0) {
          window.__THEME_B_AUDIO_FAIL_NEXT_PLAYBACK_START__ = pendingFailures - 1;
          counters.playbackStartFailures += 1;
          throw new Error('Theme B forced playback start failure');
        }

        if (!isSilentWarmupBuffer) {
          counters.starts += 1;
        }
        window.setTimeout(() => {
          if (!isSilentWarmupBuffer) {
            counters.ended += 1;
          }
          this.onended?.();
        }, 50);
      }

      stop() {}
      disconnect() {}

      addEventListener(event: string, cb: () => void) {
        if (event === 'ended') {
          this.onended = cb;
        }
      }

      removeEventListener() {}
    }

    class MockGainNode {
      gain = { value: 1, setValueAtTime() {}, linearRampToValueAtTime() {} };

      connect() {
        return this;
      }

      disconnect() {}
    }

    class MockOscillatorNode {
      type: OscillatorType = 'sine';
      frequency = { value: 440 };

      connect() {
        return this;
      }

      start() {}
      stop() {}
    }

    class MockAudioContext {
      state: AudioContextState = 'running';
      sampleRate = 44100;
      currentTime = 0;
      destination = { connect() {} };

      constructor() {
        counters.contexts += 1;
      }

      createBuffer(_channels: number, length: number) {
        return new MockAudioBuffer(length);
      }

      createBufferSource() {
        return new MockBufferSource();
      }

      createGain() {
        return new MockGainNode();
      }

      createOscillator() {
        return new MockOscillatorNode();
      }

      decodeAudioData(_arrayBuffer: ArrayBuffer, success?: (buffer: MockAudioBuffer) => void) {
        const buffer = new MockAudioBuffer();
        if (success) {
          window.setTimeout(() => success(buffer), 0);
        }
        return Promise.resolve(buffer);
      }

      async resume() {
        counters.resumes += 1;
        this.state = 'running';
      }

      async close() {
        this.state = 'closed';
      }

      addEventListener() {}
      removeEventListener() {}
    }

    class MockSpeechSynthesisUtterance {
      lang = '';
      volume = 1;
      text: string;

      constructor(text: string) {
        this.text = text;
      }
    }

    Object.defineProperty(window, 'AudioContext', {
      configurable: true,
      value: MockAudioContext,
    });
    Object.defineProperty(window, 'webkitAudioContext', {
      configurable: true,
      value: MockAudioContext,
    });
    Object.defineProperty(window, 'SpeechSynthesisUtterance', {
      configurable: true,
      value: MockSpeechSynthesisUtterance,
    });
    Object.defineProperty(window, 'speechSynthesis', {
      configurable: true,
      value: {
        cancel() {},
        speak() {
          counters.fallbackSpeech += 1;
        },
      },
    });
  });
}

async function getAudioCounters(page: Page): Promise<AudioProofCounters> {
  return page.evaluate(() => {
    return (
      window.__THEME_B_AUDIO_PROOF__ ?? {
        starts: 0,
        ended: 0,
        playbackStartFailures: 0,
        fallbackSpeech: 0,
        interactionRequired: 0,
        contexts: 0,
        resumes: 0,
      }
    );
  });
}

async function fulfillJson(route: Route, body: unknown, status = 200): Promise<void> {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

async function setupCommonVoiceRoutes(
  page: Page,
  calls: VoiceCallCounts,
  ttsModeForTurn: (turn: number) => TtsMode = () => 'success',
): Promise<void> {
  await page.route('**/api/reception/start', async (route) => {
    await fulfillJson(route, {
      reception_session_id: 'theme-b-audio-reliability',
      greeting: 'Theme B audio reliability greeting.',
      stage: 'greeting',
    });
  });

  await page.route('**/api/voice/filler', async (route) => {
    await fulfillJson(route, { success: true });
  });

  await page.route('**/api/character**', async (route) => {
    await fulfillJson(route, { success: true, vrm_control: null });
  });

  await page.route('**/api/voice', async (route) => {
    const action = parseVoiceAction(route.request());

    if (action === 'speech_to_text') {
      calls.stt += 1;
      await fulfillJson(route, {
        success: true,
        transcript: `Theme B audio reliability turn ${calls.stt}`,
      });
      return;
    }

    if (action === 'text_to_speech') {
      calls.tts += 1;
      const mode = ttsModeForTurn(calls.tts);
      if (mode === 'tts-error') {
        await fulfillJson(
          route,
          { success: false, error: 'text_to_speech upstream failed' },
          503,
        );
        return;
      }
      if (mode === 'invalid-audio') {
        await fulfillJson(route, { success: true, audioResponse: '%%%not-base64%%%' });
        return;
      }
      await fulfillJson(route, MOCK_VOICE_RESPONSE);
      return;
    }

    if (action === 'warmup' || action === 'interrupt' || action === 'client_telemetry') {
      await fulfillJson(route, { success: true, sttWarmupStatus: 'ready' });
      return;
    }

    await failUnexpectedVoiceAction(route, action, [
      'speech_to_text',
      'text_to_speech',
      'warmup',
      'interrupt',
      'client_telemetry',
    ]);
  });

  await page.route('**/api/qa', async (route) => {
    calls.qa += 1;
    await fulfillJson(route, {
      success: true,
      answer: `Theme B answer ${calls.qa}: audio reliability remains ready.`,
      emotion: 'neutral',
      metadata: {},
    });
  });
}

async function openKiosk(page: Page): Promise<void> {
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await dismissInitialModal(page, {
    closeButtonTimeoutMs: 10_000,
    closeDelayMs: 0,
    welcomeTimeoutMs: 15_000,
  });
}

async function captureVoiceTurn(page: Page): Promise<void> {
  const voiceButton = page.getByTestId('kiosk-voice-button');
  const voiceStatus = page.getByTestId('kiosk-voice-status');

  await expect(voiceButton).toBeVisible({ timeout: 15_000 });
  await expect(voiceButton).toBeEnabled();
  await voiceButton.click();
  await expect(voiceStatus).toHaveAttribute('data-session-state', 'listening', {
    timeout: 10_000,
  });

  await page.waitForTimeout(200);
  await voiceButton.dispatchEvent('click');
}

async function completeVoiceTurn(page: Page, turn: number): Promise<void> {
  await captureVoiceTurn(page);

  const voiceButton = page.getByTestId('kiosk-voice-button');
  const voiceStatus = page.getByTestId('kiosk-voice-status');

  await expect(page.getByTestId('response-text')).toContainText(`Theme B answer ${turn}:`, {
    timeout: 20_000,
  });
  await expect(voiceStatus).toHaveAttribute('data-session-state', 'idle', {
    timeout: 20_000,
  });
  await expect(voiceButton).toBeEnabled();
  await expect(voiceButton).not.toContainText(/録音中|Recording/);
  await page.waitForTimeout(500);
}

test.describe('Theme B audio reliability', () => {
  test.beforeEach(async ({ page }) => {
    await installThemeBAudioHarness(page);
    await installDeterministicVoiceRecorder(page);
  });

  test('completes three consecutive assistant turns with one TTS playback per turn', async ({
    page,
  }) => {
    const calls: VoiceCallCounts = { stt: 0, qa: 0, tts: 0 };
    await setupCommonVoiceRoutes(page, calls);
    await openKiosk(page);

    const baseline = await getAudioCounters(page);
    for (let turn = 1; turn <= 3; turn += 1) {
      const beforeTurn = await getAudioCounters(page);
      await completeVoiceTurn(page, turn);
      await expect
        .poll(async () => (await getAudioCounters(page)).starts, { timeout: 5_000 })
        .toBeGreaterThanOrEqual(baseline.starts + turn);
      const afterTurn = await getAudioCounters(page);
      expect(afterTurn.starts - beforeTurn.starts).toBe(1);
    }

    expect(calls).toEqual({ stt: 3, qa: 3, tts: 3 });
    expect((await getAudioCounters(page)).interactionRequired).toBe(0);
  });

  test('falls back cleanly when TTS synthesis or audio decoding fails, then recovers', async ({
    page,
  }) => {
    const calls: VoiceCallCounts = { stt: 0, qa: 0, tts: 0 };
    await setupCommonVoiceRoutes(page, calls, (turn) => {
      if (turn === 1) return 'tts-error';
      if (turn === 2) return 'invalid-audio';
      return 'success';
    });
    await openKiosk(page);

    await completeVoiceTurn(page, 1);
    await expect(page.getByTestId('kiosk-voice-status')).toContainText(
      /音声の再生に失敗|Audio playback failed|音声の生成|Voice generation/i,
      { timeout: 5_000 },
    );

    await completeVoiceTurn(page, 2);
    await expect
      .poll(async () => (await getAudioCounters(page)).fallbackSpeech, { timeout: 5_000 })
      .toBeGreaterThanOrEqual(2);

    await completeVoiceTurn(page, 3);

    const counters = await getAudioCounters(page);
    expect(calls).toEqual({ stt: 3, qa: 3, tts: 3 });
    expect(counters.fallbackSpeech).toBeGreaterThanOrEqual(2);
    expect(counters.interactionRequired).toBe(0);
  });

  test('settles an AudioQueue playback failure and allows the next assistant turn', async ({
    page,
  }) => {
    const calls: VoiceCallCounts = { stt: 0, qa: 0, tts: 0 };
    await setupCommonVoiceRoutes(page, calls);
    await openKiosk(page);

    await page.evaluate(() => {
      window.__THEME_B_AUDIO_FAIL_NEXT_PLAYBACK_START__ = 1;
    });

    await captureVoiceTurn(page);
    await expect.poll(() => calls.qa, { timeout: 20_000 }).toBe(1);
    await expect(page.getByTestId('kiosk-voice-status')).toHaveAttribute(
      'data-session-state',
      'idle',
      { timeout: 20_000 },
    );
    await expect
      .poll(async () => (await getAudioCounters(page)).playbackStartFailures, { timeout: 5_000 })
      .toBe(1);
    await expect(page.getByTestId('kiosk-voice-button')).toBeEnabled();
    await page.waitForTimeout(500);

    const afterFailure = await getAudioCounters(page);
    await completeVoiceTurn(page, 2);
    await expect
      .poll(async () => (await getAudioCounters(page)).starts, { timeout: 5_000 })
      .toBeGreaterThan(afterFailure.starts);

    expect(calls).toEqual({ stt: 2, qa: 2, tts: 2 });
    expect((await getAudioCounters(page)).interactionRequired).toBe(0);
  });
});
