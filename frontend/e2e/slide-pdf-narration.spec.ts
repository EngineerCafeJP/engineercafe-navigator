import { expect, test } from '@playwright/test';
import { MOCK_VOICE_RESPONSE, setupWebAudioMock } from './helpers/mocks';

declare global {
  interface Window {
    __SLIDE_AUDIO_COUNTERS__?: {
      active: number;
      starts: number;
      maxActive: number;
    };
    __PLAYWRIGHT_AUDIO_STARTS__?: number;
  }
}

async function setupSlideAudioElementMock(
  page: import('@playwright/test').Page,
  options: { staticAudioReady: boolean; endAfterMs?: number; duration?: number } = {
    staticAudioReady: true,
  },
) {
  await page.addInitScript(({ staticAudioReady, endAfterMs, duration }) => {
    type Listener = {
      callback: EventListenerOrEventListenerObject;
      once: boolean;
    };

    const counters = {
      active: 0,
      starts: 0,
      maxActive: 0,
    };
    Object.defineProperty(window, '__SLIDE_AUDIO_COUNTERS__', {
      configurable: true,
      value: counters,
    });

    const isSlideAudio = (url: string) => url.includes('/reception/audio/');

    class MockAudioElement extends EventTarget {
      public preload = '';
      public volume = 1;
      public paused = true;
      public ended = false;
      public currentTime = 0;
      public duration = duration ?? 30;
      public readyState = staticAudioReady ? 4 : 0;
      public src = '';
      private readonly listeners = new Map<string, Set<Listener>>();
      private endTimer: number | null = null;

      constructor(url?: string) {
        super();
        this.src = url ?? '';
      }

      setAttribute() {}

      removeAttribute(name: string) {
        if (name === 'src') {
          this.src = '';
        }
      }

      load() {
        if (!staticAudioReady) {
          return;
        }
        this.readyState = 4;
        setTimeout(() => {
          this.emit('canplay');
          this.emit('canplaythrough');
        }, 0);
      }

      async play() {
        if (!this.paused) {
          return;
        }
        if (this.endTimer !== null) {
          clearTimeout(this.endTimer);
          this.endTimer = null;
        }
        this.paused = false;
        this.ended = false;
        if (isSlideAudio(this.src)) {
          counters.active += 1;
          counters.starts += 1;
          counters.maxActive = Math.max(counters.maxActive, counters.active);
        }
        this.emit('play');
        if (typeof endAfterMs === 'number') {
          this.endTimer = window.setTimeout(() => {
            this.endTimer = null;
            if (this.paused) {
              return;
            }
            this.paused = true;
            this.ended = true;
            if (isSlideAudio(this.src)) {
              counters.active = Math.max(0, counters.active - 1);
            }
            this.emit('ended');
          }, Math.max(0, endAfterMs));
        }
      }

      pause() {
        if (this.endTimer !== null) {
          clearTimeout(this.endTimer);
          this.endTimer = null;
        }
        if (this.paused) {
          return;
        }
        this.paused = true;
        if (isSlideAudio(this.src) && !this.ended) {
          counters.active = Math.max(0, counters.active - 1);
        }
        this.emit('pause');
      }

      addEventListener(
        event: string,
        callback: EventListenerOrEventListenerObject,
        options?: boolean | AddEventListenerOptions,
      ) {
        const listeners = this.listeners.get(event) ?? new Set<Listener>();
        listeners.add({ callback, once: typeof options === 'object' && options.once === true });
        this.listeners.set(event, listeners);
      }

      removeEventListener(event: string, callback: EventListenerOrEventListenerObject) {
        const listeners = this.listeners.get(event);
        if (!listeners) {
          return;
        }
        for (const listener of Array.from(listeners)) {
          if (listener.callback === callback) {
            listeners.delete(listener);
          }
        }
      }

      private emit(event: string) {
        const listeners = this.listeners.get(event);
        if (!listeners) {
          return;
        }
        const evt = new Event(event);
        for (const listener of Array.from(listeners)) {
          if (typeof listener.callback === 'function') {
            listener.callback.call(this, evt);
          } else {
            listener.callback.handleEvent(evt);
          }
          if (listener.once) {
            listeners.delete(listener);
          }
        }
      }
    }

    Object.defineProperty(window, 'Audio', {
      configurable: true,
      value: MockAudioElement,
    });
  }, options);
}

async function mockReceptionStart(page: import('@playwright/test').Page, sessionId: string) {
  await page.route('**/api/reception/start', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        reception_session_id: sessionId,
        greeting: 'テストです。',
        stage: 'greeting',
      }),
    });
  });
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

test.describe('Slide PDF narration deck (#624)', () => {
  test.describe.configure({ mode: 'serial' });

  test('autoplay uses static slide audio and does not call Piper TTS', async ({ page }) => {
    await setupWebAudioMock(page);
    await setupSlideAudioElementMock(page, { staticAudioReady: true });
    await mockReceptionStart(page, 'mock-slide-narration');

    let piperHits = 0;

    await page.route('**/api/voice', async (route) => {
      const req = route.request();
      if (req.method() !== 'POST') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
        return;
      }
      let body: Record<string, unknown> = {};
      try {
        body = req.postDataJSON() as Record<string, unknown>;
      } catch {
        body = {};
      }
      if (body.action === 'text_to_speech') {
        piperHits++;
        await route.fulfill({ status: 500, contentType: 'application/json', body: '{}' });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true }),
      });
    });

    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await dismissInitialModal(page);

    await page.setViewportSize({ width: 960, height: 540 });
    await page.getByTestId('kiosk-slides-button').click();
    await page.getByTestId('slide-language-ja').click();

    await expect(page.getByTestId('reception-pdf-counter')).toHaveText('1 / 5', {
      timeout: 15_000,
    });
    await expect(page.getByTestId('reception-pdf-play')).toHaveAttribute('data-state', 'playing', {
      timeout: 15_000,
    });

    await page.waitForTimeout(3_000);
    expect(piperHits).toBe(0);
  });

  test('autoplay does not fast-forward while static audio and narration markdown are not ready', async ({ page }) => {
    await setupWebAudioMock(page);
    await setupSlideAudioElementMock(page, { staticAudioReady: false });
    await mockReceptionStart(page, 'mock-pending-assets-narration');
    await page.route('**/reception/engineer-cafe-narration-ja.md', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 3_000));
      await route.fulfill({
        status: 200,
        contentType: 'text/markdown',
        body: '## スライド 1\n\nテスト案内です。\n',
      });
    });
    await page.route('**/api/voice', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });

    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await dismissInitialModal(page);

    await page.setViewportSize({ width: 960, height: 540 });
    await page.getByTestId('kiosk-slides-button').click();
    await page.getByTestId('slide-language-ja').click();

    await expect(page.getByTestId('reception-pdf-counter')).toHaveText('1 / 5', {
      timeout: 15_000,
    });
    await expect(page.getByTestId('reception-pdf-play')).toHaveAttribute('data-state', 'playing', {
      timeout: 15_000,
    });

    await page.waitForTimeout(2_000);
    await expect(page.getByTestId('reception-pdf-counter')).toHaveText('1 / 5');
  });

  test('zero-duration static audio ending immediately does not cascade through slides', async ({ page }) => {
    await setupWebAudioMock(page);
    await setupSlideAudioElementMock(page, {
      staticAudioReady: true,
      duration: 0,
      endAfterMs: 0,
    });
    await mockReceptionStart(page, 'mock-immediate-ended-narration');
    await page.route('**/api/voice', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });

    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await dismissInitialModal(page);

    await page.setViewportSize({ width: 960, height: 540 });
    await page.getByTestId('kiosk-slides-button').click();
    await page.getByTestId('slide-language-ja').click();

    await expect(page.getByTestId('reception-pdf-counter')).toHaveText('1 / 5', {
      timeout: 15_000,
    });
    await page.waitForFunction(() => window.__SLIDE_AUDIO_COUNTERS__?.starts === 1);

    await page.waitForTimeout(2_000);
    await expect(page.getByTestId('reception-pdf-counter')).toHaveText('1 / 5');

    const counters = await page.evaluate(() => window.__SLIDE_AUDIO_COUNTERS__);
    expect(counters?.active).toBe(0);
    expect(counters?.maxActive).toBe(1);
  });

  test('short generated narration audio does not fast-forward the deck', async ({ page }) => {
    await setupWebAudioMock(page);
    await setupSlideAudioElementMock(page, { staticAudioReady: false });
    await mockReceptionStart(page, 'mock-short-generated-narration');
    await page.route('**/reception/engineer-cafe-narration-ja.md', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/markdown',
        body: [
          '# test',
          '',
          '## スライド1：テスト',
          '',
          '短い生成音声のテストナレーションです。',
          '',
          '---',
          '',
          '## スライド2：テスト',
          '',
          '二枚目のテストナレーションです。',
        ].join('\n'),
      });
    });
    await page.route('**/api/voice', async (route) => {
      const req = route.request();
      if (req.method() === 'POST') {
        let body: Record<string, unknown> = {};
        try {
          body = req.postDataJSON() as Record<string, unknown>;
        } catch {
          body = {};
        }
        if (body.action === 'text_to_speech') {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(MOCK_VOICE_RESPONSE),
          });
          return;
        }
      }
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });

    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await dismissInitialModal(page);

    await page.setViewportSize({ width: 960, height: 540 });
    await page.getByTestId('kiosk-slides-button').click();
    await page.getByTestId('slide-language-ja').click();

    await expect(page.getByTestId('reception-pdf-counter')).toHaveText('1 / 5', {
      timeout: 15_000,
    });
    await page.waitForFunction(() => (window.__PLAYWRIGHT_AUDIO_STARTS__ ?? 0) >= 1);

    await page.waitForTimeout(2_000);
    await expect(page.getByTestId('reception-pdf-counter')).toHaveText('1 / 5');
  });

  test('rapid slide changes stop current narration before another slide can play', async ({ page }) => {
    await setupWebAudioMock(page);
    await setupSlideAudioElementMock(page, { staticAudioReady: true });
    await mockReceptionStart(page, 'mock-rapid-slide-narration');
    await page.route('**/api/voice', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });

    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await dismissInitialModal(page);

    await page.setViewportSize({ width: 960, height: 540 });
    await page.getByTestId('kiosk-slides-button').click();
    await page.getByTestId('slide-language-ja').click();

    await expect(page.getByTestId('reception-pdf-counter')).toHaveText('1 / 5', {
      timeout: 15_000,
    });
    await page.waitForFunction(() => window.__SLIDE_AUDIO_COUNTERS__?.active === 1);

    await page.getByTestId('reception-pdf-next').click();
    await expect(page.getByTestId('reception-pdf-counter')).toHaveText('2 / 5');
    await page.waitForFunction(() => window.__SLIDE_AUDIO_COUNTERS__?.active === 0);
    await expect(page.getByTestId('reception-pdf-play')).toHaveAttribute('data-state', 'paused');

    await page.getByTestId('reception-pdf-next').click();
    await expect(page.getByTestId('reception-pdf-counter')).toHaveText('3 / 5');
    await page.getByTestId('reception-pdf-play').click();
    await page.waitForFunction(() => window.__SLIDE_AUDIO_COUNTERS__?.active === 1);

    const counters = await page.evaluate(() => window.__SLIDE_AUDIO_COUNTERS__);
    expect(counters?.starts).toBe(2);
    expect(counters?.maxActive).toBe(1);
  });

  test('autoplay waits for narration markdown instead of fast-advancing without audio', async ({
    page,
  }) => {
    await setupWebAudioMock(page);
    await setupSlideAudioElementMock(page, { staticAudioReady: false });
    await mockReceptionStart(page, 'mock-delayed-narration-assets');

    let releaseNarration!: () => void;
    const narrationGate = new Promise<void>((resolve) => {
      releaseNarration = resolve;
    });
    await page.route('**/reception/engineer-cafe-narration-ja.md', async (route) => {
      await narrationGate;
      await route.fulfill({
        status: 200,
        contentType: 'text/markdown',
        body: [
          '# test',
          '',
          '## スライド1：テスト',
          '',
          'スライド一枚目のテストナレーションです。',
          '',
          '---',
          '',
          '## スライド2：テスト',
          '',
          'スライド二枚目のテストナレーションです。',
        ].join('\n'),
      });
    });

    let ttsRequests = 0;
    await page.route('**/api/voice', async (route) => {
      const req = route.request();
      if (req.method() === 'POST') {
        let body: Record<string, unknown> = {};
        try {
          body = req.postDataJSON() as Record<string, unknown>;
        } catch {
          body = {};
        }
        if (body.action === 'text_to_speech') {
          ttsRequests += 1;
        }
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_VOICE_RESPONSE),
      });
    });

    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await dismissInitialModal(page);

    await page.setViewportSize({ width: 960, height: 540 });
    await page.getByTestId('kiosk-slides-button').click();
    await page.getByTestId('slide-language-ja').click();

    await expect(page.getByTestId('reception-pdf-counter')).toHaveText('1 / 5', {
      timeout: 15_000,
    });
    await page.waitForTimeout(1_300);
    await expect(page.getByTestId('reception-pdf-counter')).toHaveText('1 / 5');
    expect(ttsRequests).toBe(0);

    releaseNarration();
    await expect.poll(() => ttsRequests, { timeout: 5_000 }).toBeGreaterThan(0);
  });

  test('closing slides during pending generated narration prevents stale audio playback', async ({ page }) => {
    await setupWebAudioMock(page);
    await setupSlideAudioElementMock(page, { staticAudioReady: false });
    await mockReceptionStart(page, 'mock-close-pending-narration');
    let ttsRequests = 0;
    await page.route('**/api/voice', async (route) => {
      const req = route.request();
      if (req.method() === 'POST') {
        let body: Record<string, unknown> = {};
        try {
          body = req.postDataJSON() as Record<string, unknown>;
        } catch {
          body = {};
        }
        if (body.action === 'text_to_speech') {
          ttsRequests += 1;
          await new Promise((resolve) => setTimeout(resolve, 900));
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(MOCK_VOICE_RESPONSE),
          });
          return;
        }
      }
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });

    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await dismissInitialModal(page);

    await page.setViewportSize({ width: 960, height: 540 });
    await page.getByTestId('kiosk-slides-button').click();
    await page.getByTestId('slide-language-ja').click();

    await expect(page.getByTestId('reception-pdf-counter')).toHaveText('1 / 5', {
      timeout: 15_000,
    });
    await expect.poll(() => ttsRequests, { timeout: 5_000 }).toBe(1);

    await page.getByRole('button', { name: /スライドを閉じる|Close slides/ }).click();
    await expect(page.getByRole('button', { name: 'Welcome' })).toBeVisible({ timeout: 5_000 });
    await page.waitForTimeout(1_200);

    const staticAudioCounters = await page.evaluate(() => window.__SLIDE_AUDIO_COUNTERS__);
    const webAudioStarts = await page.evaluate(() => window.__PLAYWRIGHT_AUDIO_STARTS__ ?? 0);
    expect(staticAudioCounters?.active).toBe(0);
    expect(staticAudioCounters?.maxActive).toBe(0);
    expect(webAudioStarts).toBe(0);
  });
});
