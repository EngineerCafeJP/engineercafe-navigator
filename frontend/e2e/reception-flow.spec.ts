import fs from 'node:fs';
import path from 'node:path';

import { expect, test } from '@playwright/test';

/**
 * Reception Flow E2E Tests (Issue #381)
 *
 * These tests verify the kiosk reception workflow visible to visitors at
 * Engineer Cafe Fukuoka.  The kiosk page.tsx renders phase-dependent UI:
 *
 *   notice  -> idle  -> voice / ocr / slides
 *
 * Welcome triggers (button press or device-detection custom event) call
 * `startReception` and play a greeting, then enter the voice-first reception flow.
 *
 * Backend APIs are mocked via route intercepts so these tests can run
 * without a live backend.
 */

const RECEPTION_START_URL = '/api/reception/start';
const QA_CHAT_URL = '/api/qa';

// These tests exercise one kiosk app shell and are sensitive to browser
// hydration / WebGL startup timing on CI runners. Keep this spec serial so
// modal dismissal and localStorage state cannot compete across workers.
test.describe.configure({ mode: 'serial' });

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Dismiss the initial-settings modal so the kiosk reaches the idle phase. */
async function dismissInitialModal(page: import('@playwright/test').Page) {
  const modal = page.getByRole('dialog');
  const closeButton = page.getByTestId('initial-settings-close');
  if (await closeButton.isVisible({ timeout: 3_000 }).catch(() => false)) {
    // The page can reach DOMContentLoaded before the app is fully hydrated.
    // Clicking the modal button too early is a no-op, so give React a moment
    // before starting the retry loop.
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
  // Wait for the idle phase — the Welcome button should be visible.
  await expect(page.getByRole('button', { name: 'Welcome' })).toBeVisible({ timeout: 5_000 });
}

/**
 * Intercept the reception/start API and return a mock response so the test
 * does not depend on a live backend.
 */
function mockReceptionStart(page: import('@playwright/test').Page, greeting?: string) {
  return page.route(`**${RECEPTION_START_URL}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        reception_session_id: 'mock-reception-001',
        greeting: greeting ?? 'エンジニアカフェへようこそ！ご用件をお聞かせください。',
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
        // Keep OCR overlays mounted without depending on real camera access.
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

async function rejectMicrophonePermission(page: import('@playwright/test').Page) {
  await page.addInitScript(() => {
    const existingMediaDevices = navigator.mediaDevices ?? {};
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        ...existingMediaDevices,
        getUserMedia: async () => {
          throw new DOMException('Permission denied', 'NotAllowedError');
        },
      },
    });
  });
}

// ---------------------------------------------------------------------------
// A. Welcome button triggers reception greeting
// ---------------------------------------------------------------------------

test.describe('Reception flow — Welcome button', () => {
  test.beforeEach(async ({ page }) => {
    await keepOcrCameraPending(page);
    await mockReceptionStart(page);
    // Stub QA endpoint to prevent real backend calls during voice flow.
    await page.route(`**${QA_CHAT_URL}`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ answer: 'テスト応答', emotion: 'neutral', metadata: {} }),
      });
    });
    // Stub TTS/voice endpoints to prevent audio errors.
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

  test('Welcome button is visible on idle screen', async ({ page }) => {
    const welcomeButton = page.getByRole('button', { name: 'Welcome' });
    await expect(welcomeButton).toBeVisible();
    await expect(welcomeButton).toBeEnabled();
  });

  test('clicking Welcome button triggers voice-first reception greeting flow', async ({ page }) => {
    const welcomeButton = page.getByRole('button', { name: 'Welcome' });
    await welcomeButton.click();

    // Welcome must not open camera/OCR. It should greet and move into the voice lane.
    await expect(page.getByTestId('kiosk-welcome-ocr-overlay')).toBeHidden({ timeout: 5_000 });
    await expect(page.getByTestId('response-text')).toContainText(
      'エンジニアカフェへようこそ',
      { timeout: 5_000 },
    );
  });

  test('kiosk phase buttons are all present on idle screen', async ({ page }) => {
    // All five kiosk action buttons should be visible in screen trigger mode.
    await expect(page.getByRole('button', { name: 'Welcome' })).toBeVisible();
    await expect(page.getByRole('button', { name: /音声応対|Voice chat/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /会員証|Member card/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /筆談|Handwriting/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /スライド案内|Slide guide/ })).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// B. Device sensor triggers welcome flow
// ---------------------------------------------------------------------------

test.describe('Reception flow — device sensor trigger', () => {
  test.beforeEach(async ({ page }) => {
    await installDeterministicVoiceRecorder(page);
    await keepOcrCameraPending(page);
    await mockReceptionStart(page);
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

  test('dispatching device-detection custom event triggers welcome when idle', async ({
    page,
  }) => {
    // Dispatch the same CustomEvent that M5Stack / NFC readers use.
    await page.evaluate(() => {
      window.dispatchEvent(
        new CustomEvent('device-detection', {
          detail: {
            type: 'sensor_triggered',
            device_id: 'e2e-test-sensor',
            timestamp: new Date().toISOString(),
          },
        }),
      );
    });

    // The welcome flow should activate without opening camera/OCR.
    await expect(page.getByTestId('kiosk-welcome-ocr-overlay')).toBeHidden({ timeout: 5_000 });
    await expect(page.getByTestId('response-text')).toContainText(
      'エンジニアカフェへようこそ',
      { timeout: 5_000 },
    );
  });

  test('device-detection is ignored when kiosk is not in idle phase', async ({ page }) => {
    // First, enter voice mode.
    const voiceButton = page.getByRole('button', { name: /音声応対|Voice chat/ });
    await voiceButton.click();

    // Now dispatch device-detection — it should be ignored.
    await page.evaluate(() => {
      window.dispatchEvent(
        new CustomEvent('device-detection', {
          detail: {
            type: 'sensor_triggered',
            device_id: 'e2e-test-sensor',
            timestamp: new Date().toISOString(),
          },
        }),
      );
    });

    // The kiosk should still be in voice mode, not welcome.
    // A short wait confirms no unexpected transition happened.
    await page.waitForTimeout(1_000);
    // The Welcome button should not have been re-triggered (no new OCR overlay).
    // The voice button label changes while recording, so assert via the stable test id.
    await expect(page.getByTestId('kiosk-voice-button')).toBeVisible();
    await expect(page.getByTestId('kiosk-voice-button')).toContainText(/録音中|Recording/);
  });
});

// ---------------------------------------------------------------------------
// C. Member card OCR during welcome
// ---------------------------------------------------------------------------

test.describe('Reception flow — member card OCR', () => {
  test.beforeEach(async ({ page }) => {
    await keepOcrCameraPending(page);
    await mockReceptionStart(page);
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

  test('member card OCR overlay does not appear after Welcome click', async ({ page }) => {
    await page.getByRole('button', { name: 'Welcome' }).click();

    await expect(page.getByTestId('kiosk-welcome-ocr-overlay')).toBeHidden({ timeout: 5_000 });
    await expect(page.getByTestId('response-text')).toContainText(
      'エンジニアカフェへようこそ',
      { timeout: 5_000 },
    );
  });

  test('dedicated member card button opens full OCR view', async ({ page }) => {
    const memberCardButton = page.getByRole('button', { name: /会員証|Member card/ });
    await memberCardButton.click();

    // Full OCR view opens with a "back to menu" button.
    await expect(page.getByRole('button', { name: /メニューに戻る|Back to menu/ })).toBeVisible({
      timeout: 5_000,
    });
  });

  test('back-to-menu button returns from OCR to idle', async ({ page }) => {
    await page.getByRole('button', { name: /会員証|Member card/ }).click();

    const backButton = page.getByRole('button', { name: /メニューに戻る|Back to menu/ });
    await expect(backButton).toBeVisible({ timeout: 5_000 });
    await backButton.click();

    // Should return to idle — Welcome button visible again.
    await expect(page.getByRole('button', { name: 'Welcome' })).toBeVisible({ timeout: 5_000 });
  });
  test('back-to-menu clears the anonymous visitor id', async ({ page }) => {
    await dismissInitialModal(page);
    await page.waitForFunction(
      () => window.localStorage.getItem('engineer_cafe_visitor_id') !== null,
    );
    const initialVisitorId = await page.evaluate(() =>
      window.localStorage.getItem('engineer_cafe_visitor_id'),
    );
    expect(initialVisitorId).toBeTruthy();

    await page.getByRole('button', { name: /会員証|Member card/ }).click();
    await page.getByRole('button', { name: /メニューに戻る|Back to menu/ }).click();

    await page.waitForFunction(
      () => window.localStorage.getItem('engineer_cafe_visitor_id') === null,
    );
    const visitorIdAfterReturn = await page.evaluate(() =>
      window.localStorage.getItem('engineer_cafe_visitor_id'),
    );

    expect(visitorIdAfterReturn).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// D. Voice mode transitions
// ---------------------------------------------------------------------------

test.describe('Reception flow — voice mode', () => {
  test.beforeEach(async ({ page }) => {
    await installDeterministicVoiceRecorder(page);
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
  });

  test('voice button transitions kiosk to voice mode', async ({ page }) => {
    const voiceButton = page.getByRole('button', { name: /音声応対|Voice chat/ });
    await voiceButton.click();

    // In voice mode the button remains visible but its label changes to recording.
    await expect(page.getByTestId('kiosk-voice-button')).toBeVisible();
    await expect(page.getByTestId('kiosk-voice-button')).toContainText(/録音中|Recording/);
  });
});

test.describe('Reception flow — microphone errors', () => {
  test.beforeEach(async ({ page }) => {
    await rejectMicrophonePermission(page);
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
  });

  test('permission denial shows a microphone error and does not stay recording', async ({ page }) => {
    await page.getByRole('button', { name: /音声応対|Voice chat/ }).click();

    // Anchor on actual error strings from error-messages.ts (MIC_PERMISSION_DENIED /
    // MICROPHONE_PERMISSION_DENIED / MIC_SECURITY_ERROR) so the assertion still falsifies
    // when the denial UI is silently swallowed and only the default prompt is shown.
    await expect(page.getByTestId('kiosk-voice-status')).toContainText(
      /マイクの許可|マイクへのアクセス|Microphone permission|HTTPS/i,
      { timeout: 5_000 },
    );
    await expect(page.getByTestId('kiosk-voice-button')).not.toContainText(/録音中|Recording/);
  });
});

// ---------------------------------------------------------------------------
// E. Welcome cooldown prevents rapid re-triggering
// ---------------------------------------------------------------------------

test.describe('Reception flow — welcome cooldown', () => {
  test.beforeEach(async ({ page }) => {
    await mockReceptionStart(page);
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

  test('Welcome button is disabled during cooldown after first click', async ({ page }) => {
    const welcomeButton = page.getByRole('button', { name: 'Welcome' });
    await expect(welcomeButton).toBeEnabled();

    await welcomeButton.click();

    // After clicking, the cooldown activates. The Welcome button should
    // become disabled (cursor-not-allowed styling via the disabled attribute
    // or the class change).
    await expect(welcomeButton).toBeDisabled({ timeout: 2_000 });
  });
});

// ---------------------------------------------------------------------------
// F. Settings button accessibility
// ---------------------------------------------------------------------------

test.describe('Reception flow — settings', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await dismissInitialModal(page);
  });

  test('settings button opens settings panel', async ({ page }) => {
    const settingsButton = page.getByRole('button', { name: /設定|Settings/ });
    await expect(settingsButton).toBeVisible();
    await settingsButton.click();

    await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible({
      timeout: 3_000,
    });
  });
});

// ---------------------------------------------------------------------------
// G. STT warmup fires on Welcome and voice button
// ---------------------------------------------------------------------------

test.describe('Reception flow — STT warmup', () => {
  test.beforeEach(async ({ page }) => {
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
  });

  test('Welcome click fires warmup request to /api/voice', async ({ page }) => {
    const warmupRequests: Array<Record<string, unknown>> = [];
    await page.route('**/api/voice', async (route) => {
      const body = route.request().postDataJSON();
      if (body && body.action === 'warmup') {
        warmupRequests.push(body);
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true }),
      });
    });

    await page.getByRole('button', { name: 'Welcome' }).click();

    await expect
      .poll(() => warmupRequests.length, { timeout: 5_000 })
      .toBeGreaterThanOrEqual(1);
    expect(warmupRequests[0]!.action).toBe('warmup');
    expect(typeof warmupRequests[0]!.sessionId).toBe('string');
  });

  test('voice button click fires warmup request to /api/voice', async ({ page }) => {
    const warmupRequests: Array<Record<string, unknown>> = [];
    await page.route('**/api/voice', async (route) => {
      const body = route.request().postDataJSON();
      if (body && body.action === 'warmup') {
        warmupRequests.push(body);
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true }),
      });
    });

    await page.getByRole('button', { name: /音声応対|Voice chat/ }).click();

    await expect
      .poll(() => warmupRequests.length, { timeout: 5_000 })
      .toBeGreaterThanOrEqual(1);
    expect(warmupRequests[0]!.action).toBe('warmup');
    expect(typeof warmupRequests[0]!.sessionId).toBe('string');
  });

  test('OCR overlay is not opened during welcome flow', async ({ page }) => {
    await page.getByRole('button', { name: 'Welcome' }).click();
    await expect(page.getByTestId('kiosk-welcome-ocr-overlay')).toBeHidden({ timeout: 5_000 });
    await expect(page.getByTestId('response-text')).toContainText(
      'エンジニアカフェへようこそ',
      { timeout: 5_000 },
    );
  });

  test('warmup does not block greeting TTS playback', async ({ page }) => {
    let warmupStarted = false;
    let ttsRequests = 0;
    let releaseWarmup: (() => void) | null = null;
    await page.route('**/api/voice', async (route) => {
      const body = route.request().postDataJSON();
      if (body && body.action === 'warmup') {
        warmupStarted = true;
        await new Promise<void>((resolve) => {
          releaseWarmup = resolve;
        });
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ success: true, sttWarmupStatus: 'ready' }),
        });
        return;
      }
      if (body && body.action === 'text_to_speech') {
        ttsRequests += 1;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true }),
      });
    });

    await page.getByRole('button', { name: 'Welcome' }).click();

    await expect(page.getByTestId('kiosk-welcome-ocr-overlay')).toBeHidden({ timeout: 5_000 });
    await expect
      .poll(() => warmupStarted, { timeout: 5_000 })
      .toBe(true);
    await expect
      .poll(() => ttsRequests, { timeout: 5_000 })
      .toBeGreaterThanOrEqual(1);
    releaseWarmup?.();
  });
});
