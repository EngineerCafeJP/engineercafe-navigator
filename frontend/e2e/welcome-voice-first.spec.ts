import { expect, test, type Page } from '@playwright/test';

import { MOCK_VOICE_RESPONSE } from './helpers/mocks';
import {
  failUnexpectedVoiceAction,
  installDeterministicVoiceRecorder,
  installIOSUserAgent,
  parseVoiceAction,
} from './helpers/voice';

const RECEPTION_START_URL = '/api/reception/start';

interface MediaRequestCounts {
  audio: number;
  video: number;
}

async function dismissInitialModal(page: import('@playwright/test').Page) {
  const modal = page.getByRole('dialog');
  const closeButton = page.getByTestId('initial-settings-close');
  await expect
    .poll(async () => {
      if (await modal.isHidden().catch(() => true)) {
        return true;
      }
      if (await closeButton.isVisible({ timeout: 1_000 }).catch(() => false)) {
        await closeButton.click({ force: true }).catch(() => {});
      }
      return modal.isHidden().catch(() => true);
    }, { timeout: 10_000 })
    .toBe(true);
  await expect(page.getByRole('button', { name: 'Welcome' })).toBeVisible({ timeout: 5_000 });
}

async function installMediaRequestProbe(page: import('@playwright/test').Page) {
  await page.addInitScript(() => {
    const counts = { audio: 0, video: 0 };
    const existingMediaDevices = navigator.mediaDevices ?? {};

    Object.defineProperty(window, '__welcomeMediaRequestCounts', {
      configurable: true,
      value: counts,
    });

    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        ...existingMediaDevices,
        getUserMedia: async (constraints?: MediaStreamConstraints) => {
          const wantsVideo = Boolean(
            constraints &&
              typeof constraints === 'object' &&
              'video' in constraints &&
              constraints.video,
          );
          const wantsAudio = Boolean(
            constraints &&
              typeof constraints === 'object' &&
              'audio' in constraints &&
              constraints.audio,
          );

          if (wantsVideo) {
            counts.video += 1;
            return new Promise<MediaStream>(() => {
              // Keep OCR mounted without requiring real camera access.
            });
          }
          if (wantsAudio) {
            counts.audio += 1;
          }
          return new MediaStream();
        },
      },
    });
  });
}

async function installSuspendedAudioContext(page: Page) {
  await page.addInitScript(() => {
    class MockAudioBuffer {
      duration = 0.01;
      length = 441;
      numberOfChannels = 1;
      sampleRate = 44100;

      getChannelData() {
        return new Float32Array(441);
      }
    }

    class MockBufferSource {
      buffer: unknown = null;
      onended: (() => void) | null = null;

      connect() {
        return this;
      }

      start() {
        setTimeout(() => {
          this.onended?.();
        }, 25);
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

    class MockAudioContext {
      state: AudioContextState = 'suspended';
      sampleRate = 44100;
      currentTime = 0;
      destination = { connect() {} };

      createBuffer() {
        return new MockAudioBuffer();
      }

      createBufferSource() {
        return new MockBufferSource();
      }

      createGain() {
        return new MockGainNode();
      }

      decodeAudioData() {
        return Promise.resolve(new MockAudioBuffer());
      }

      async resume() {}

      async close() {
        this.state = 'closed';
      }

      addEventListener() {}
      removeEventListener() {}
    }

    Object.defineProperty(window, 'AudioContext', {
      configurable: true,
      value: MockAudioContext,
    });
    Object.defineProperty(window, 'webkitAudioContext', {
      configurable: true,
      value: MockAudioContext,
    });
  });
}

async function getMediaRequestCounts(
  page: import('@playwright/test').Page,
): Promise<MediaRequestCounts> {
  return page.evaluate(() => {
    const windowWithCounts = window as Window & {
      __welcomeMediaRequestCounts?: MediaRequestCounts;
    };
    return windowWithCounts.__welcomeMediaRequestCounts ?? { audio: 0, video: 0 };
  });
}

function mockReceptionStart(page: import('@playwright/test').Page) {
  return page.route(`**${RECEPTION_START_URL}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        reception_session_id: 'mock-welcome-voice-first',
        greeting: 'エンジニアカフェへようこそ！ご用件をお聞かせください。',
        stage: 'greeting',
      }),
    });
  });
}

test.describe('Welcome voice-first (#616)', () => {
  test.beforeEach(async ({ page }) => {
    await installMediaRequestProbe(page);
    await mockReceptionStart(page);
    await page.route('**/api/qa', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, answer: 'OK', emotion: 'neutral', metadata: {} }),
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
  });

  test('idle kiosk shows session mode badge without OCR overlay', async ({ page }) => {
    await expect(page.getByTestId('kiosk-voice-mode-badge')).toBeVisible({ timeout: 5_000 });
    await expect(page.getByTestId('kiosk-welcome-ocr-overlay')).toBeHidden();
  });

  test('Welcome opens reception voice lane without welcome OCR overlay', async ({ page }) => {
    await page.getByRole('button', { name: 'Welcome' }).click();
    await expect(page.getByTestId('kiosk-welcome-ocr-overlay')).toBeHidden({ timeout: 5_000 });
    await expect(page.getByTestId('response-text')).toContainText('エンジニアカフェへようこそ', {
      timeout: 8_000,
    });
  });

  test('Welcome does not request camera; member card button does', async ({ page }) => {
    expect((await getMediaRequestCounts(page)).video).toBe(0);

    await page.getByRole('button', { name: 'Welcome' }).click();
    await expect(page.getByTestId('kiosk-welcome-ocr-overlay')).toBeHidden({ timeout: 5_000 });
    await expect
      .poll(async () => (await getMediaRequestCounts(page)).video, { timeout: 2_000 })
      .toBe(0);

    await page.reload({ waitUntil: 'domcontentloaded' });
    await dismissInitialModal(page);

    await page.getByRole('button', { name: /会員証|Member card/ }).click();
    await expect
      .poll(async () => (await getMediaRequestCounts(page)).video, { timeout: 5_000 })
      .toBeGreaterThanOrEqual(1);
  });
});

test.describe('Welcome voice button recovery (#817)', () => {
  test('voice button starts recording instead of replaying pending Welcome TTS', async ({ page }) => {
    let sttCount = 0;

    await installIOSUserAgent(page);
    await installSuspendedAudioContext(page);
    await installDeterministicVoiceRecorder(page);

    await page.route(`**${RECEPTION_START_URL}`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          reception_session_id: 'mock-welcome-pending-audio',
          greeting: 'エンジニアカフェへようこそ！ご用件をお聞かせください。',
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
      const action = parseVoiceAction(route.request());

      if (action === 'text_to_speech') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_VOICE_RESPONSE),
        });
        return;
      }

      if (action === 'speech_to_text') {
        sttCount += 1;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            transcript: 'エンジニアカフェの営業時間を教えてください。',
          }),
        });
        return;
      }

      if (action === 'warmup' || action === 'interrupt' || action === 'client_telemetry') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ success: true, sttWarmupStatus: 'ready' }),
        });
        return;
      }

      await failUnexpectedVoiceAction(route, action, [
        'text_to_speech',
        'speech_to_text',
        'warmup',
        'interrupt',
        'client_telemetry',
      ]);
    });

    await page.route('**/api/qa', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          answer: 'エンジニアカフェの営業時間は10時から22時です。',
          emotion: 'neutral',
          metadata: {},
        }),
      });
    });

    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await dismissInitialModal(page);

    await page.getByRole('button', { name: 'Welcome' }).click();
    await expect(page.getByTestId('response-text')).toContainText('エンジニアカフェへようこそ', {
      timeout: 8_000,
    });
    await expect(page.getByTestId('kiosk-voice-status')).toContainText(
      /音声を有効|enable audio/i,
      { timeout: 8_000 },
    );

    const voiceButton = page.getByTestId('kiosk-voice-button');
    const voiceStatus = page.getByTestId('kiosk-voice-status');

    await voiceButton.click();
    await expect(voiceStatus).toHaveAttribute('data-session-state', 'listening', {
      timeout: 8_000,
    });

    await voiceButton.dispatchEvent('click');
    await expect.poll(() => sttCount, { timeout: 15_000 }).toBe(1);
  });
});
