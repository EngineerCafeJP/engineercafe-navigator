import { expect, test } from '@playwright/test';
import {
  MOCK_VOICE_RESPONSE,
  setupMarpMocks,
  setupWebAudioMock,
} from './helpers/mocks';
import {
  clickPlayPause,
  clickPrevSlide,
  clickReset,
  clickSwitchToEnglish,
  gotoGuide,
  waitForSlide,
} from './helpers/marp';

test.describe('MarpViewer — 基本表示', () => {
  test.beforeEach(async ({ page }) => {
    await setupWebAudioMock(page);
    await setupMarpMocks(page);
  });

  test('/guide?lang=ja でシェルとスライドが読み込まれる', async ({ page }) => {
    await gotoGuide(page, 'ja');

    await expect(page.getByTestId('customer-guide-shell')).toBeVisible();
    await expect(page.getByTestId('marp-viewer')).toBeVisible();
    await expect(page.locator('main h1')).toBeVisible();
  });

  test('スライドカウンターが「1 / 3」と表示される', async ({ page }) => {
    await gotoGuide(page, 'ja');
    await waitForSlide(page, 1, 3);
  });

  test('最初のスライドでは前へボタンが無効', async ({ page }) => {
    await gotoGuide(page, 'ja');
    await waitForSlide(page, 1, 3);
    await expect(page.getByTestId('marp-prev-button')).toBeDisabled();
  });
});

test.describe('MarpViewer — スライドナビゲーション', () => {
  test.beforeEach(async ({ page }) => {
    await setupWebAudioMock(page);
    await setupMarpMocks(page);
  });

  test('スライド2にいるとき前へボタンでスライド1に戻る', async ({ page }) => {
    await gotoGuide(page, 'ja');
    await waitForSlide(page, 1, 3);
    await clickPlayPause(page);
    await waitForSlide(page, 2, 3);

    await expect(page.getByTestId('marp-prev-button')).toBeEnabled();
    await clickPrevSlide(page);

    await waitForSlide(page, 1, 3);
  });

  test('リセットボタンでスライド1に戻る', async ({ page }) => {
    await gotoGuide(page, 'ja', { autoplay: true });
    await waitForSlide(page, 2, 3);

    await clickPlayPause(page);
    await clickReset(page);

    await waitForSlide(page, 1, 3);
  });
});

test.describe('MarpViewer — 再生制御', () => {
  test.beforeEach(async ({ page }) => {
    await setupWebAudioMock(page);
    await setupMarpMocks(page);
  });

  test('再生ボタンをクリックするとナレーションAPIが呼ばれる', async ({ page }) => {
    const voiceRequests: string[] = [];
    await page.route('/api/voice', (route) => {
      voiceRequests.push(route.request().url());
      return route.fulfill({ json: MOCK_VOICE_RESPONSE });
    });

    await gotoGuide(page, 'ja');
    await waitForSlide(page, 1, 3);

    await clickPlayPause(page);

    await expect
      .poll(() => voiceRequests.length, { timeout: 5_000 })
      .toBeGreaterThan(0);
  });

  test('一時停止ボタンで再生が止まる', async ({ page }) => {
    await gotoGuide(page, 'ja', { autoplay: true });
    await waitForSlide(page, 1, 3);

    const counterBefore = await page.getByTestId('marp-slide-counter').textContent();

    await clickPlayPause(page);

    await page.waitForTimeout(500);
    const counterAfter = await page.getByTestId('marp-slide-counter').textContent();

    expect(counterBefore).toBe(counterAfter);
  });
});

test.describe('MarpViewer — CustomerGuideShell 言語切り替え', () => {
  test.beforeEach(async ({ page }) => {
    await setupWebAudioMock(page);
    await setupMarpMocks(page);
  });

  test('/guide?lang=ja で日本語タイトルが表示される', async ({ page }) => {
    await gotoGuide(page, 'ja');

    await expect(page.locator('main h1')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'First Visit Registration Guide' })).toHaveCount(0);
    await expect(page.getByTestId('guide-language-toggle')).toBeVisible();
  });

  test('英語切り替えボタンで /onboarding?lang=en に遷移する', async ({ page }) => {
    await gotoGuide(page, 'ja');
    await page.request.get('/onboarding?lang=en');

    await clickSwitchToEnglish(page);

    await expect(page).toHaveURL(/\/onboarding\?lang=en$/, { timeout: 30_000 });
    await expect(page.getByRole('heading', { name: 'First Visit Registration Guide' })).toBeVisible({
      timeout: 30_000,
    });
  });
});
