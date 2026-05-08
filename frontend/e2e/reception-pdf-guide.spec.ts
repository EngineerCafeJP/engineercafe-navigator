import { expect, test } from '@playwright/test';

/**
 * Reception PDF slide guide (ReceptionPdfGuide + autoStartPresentation).
 */

async function dismissInitialModal(page: import('@playwright/test').Page) {
  const modal = page.getByRole('dialog');
  const closeButton = page.getByTestId('initial-settings-close');
  if (await closeButton.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await closeButton.click();
    await expect(modal).toBeHidden({ timeout: 5_000 });
  }
  await expect(page.getByRole('button', { name: 'Welcome' })).toBeVisible({ timeout: 5_000 });
}

async function mockReceptionApis(page: import('@playwright/test').Page) {
  await page.route('**/api/reception/start', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        reception_session_id: 'mock-reception-pdf',
        greeting: 'テストです。',
        stage: 'greeting',
      }),
    });
  });
  await page.route('**/api/qa', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ answer: 'ok', emotion: 'neutral', metadata: {} }),
    });
  });
  await page.route('**/api/voice', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  });
}

async function dragOnSlidePanel(
  page: import('@playwright/test').Page,
  deltaX: number,
  deltaY: number,
) {
  const box = await page.getByTestId('reception-pdf-landscape-panel').boundingBox();
  expect(box).not.toBeNull();
  if (!box) {
    return;
  }
  const startX = box.x + box.width / 2;
  const startY = box.y + box.height / 2;
  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.mouse.move(startX + deltaX, startY + deltaY, { steps: 6 });
  await page.mouse.up();
}

test.describe('Reception PDF guide', () => {
  test.beforeEach(async ({ page }) => {
    await mockReceptionApis(page);
    await page.goto('/');
    await dismissInitialModal(page);
  });

  test('portrait viewport shows rotate hint before landscape panel', async ({ page }) => {
    await page.setViewportSize({ width: 600, height: 900 });
    await page.getByTestId('kiosk-slides-button').click();
    await expect(page.getByTestId('slide-language-ja')).toBeVisible({ timeout: 5_000 });
    await page.getByTestId('slide-language-ja').click();

    await expect(page.getByTestId('reception-pdf-rotate-hint')).toBeVisible({ timeout: 8_000 });
    await expect(page.getByTestId('reception-pdf-landscape-panel')).toHaveCount(0);
  });

  test('landscape shows PDF counter 1/5 and auto-starts playback', async ({ page }) => {
    await page.setViewportSize({ width: 960, height: 540 });
    await page.getByTestId('kiosk-slides-button').click();
    await page.getByTestId('slide-language-ja').click();

    await expect(page.getByTestId('reception-pdf-counter')).toHaveText('1 / 5', {
      timeout: 15_000,
    });
    await expect(page.getByTestId('reception-pdf-canvas')).toBeVisible();
    await expect(page.getByTestId('reception-pdf-play')).toHaveAttribute('data-state', 'playing', {
      timeout: 15_000,
    });
    await expect(page.getByTestId('kiosk-settings-button')).toHaveCount(0);
  });

  test('close slides returns to Welcome', async ({ page }) => {
    await page.setViewportSize({ width: 960, height: 540 });
    await page.getByTestId('kiosk-slides-button').click();
    await page.getByTestId('slide-language-ja').click();
    await expect(page.getByTestId('reception-pdf-guide')).toBeVisible({ timeout: 15_000 });

    await page.getByRole('button', { name: /スライドを閉じる|Close slides/ }).click();
    await expect(page.getByRole('button', { name: 'Welcome' })).toBeVisible({ timeout: 5_000 });
  });

  test('slide button lets visitors choose English guide', async ({ page }) => {
    await page.setViewportSize({ width: 960, height: 540 });
    await page.getByTestId('kiosk-slides-button').click();
    await page.getByTestId('slide-language-en').click();

    await expect(page.getByTestId('reception-pdf-counter')).toHaveText('1 / 5', {
      timeout: 15_000,
    });
    await expect(page.getByTestId('reception-pdf-controls')).toBeVisible();
    await expect(page.getByText('Auto-advance')).toHaveCount(0);
  });

  test('horizontal swipes navigate slides while short or vertical drags are ignored', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 960, height: 540 });
    await page.getByTestId('kiosk-slides-button').click();
    await page.getByTestId('slide-language-ja').click();

    await expect(page.getByTestId('reception-pdf-counter')).toHaveText('1 / 5', {
      timeout: 15_000,
    });
    await expect(page.getByTestId('reception-pdf-play')).toHaveAttribute('data-state', 'playing', {
      timeout: 15_000,
    });
    await page.getByTestId('reception-pdf-play').click();
    await expect(page.getByTestId('reception-pdf-play')).toHaveAttribute('data-state', 'paused');

    await dragOnSlidePanel(page, -180, 8);
    await expect(page.getByTestId('reception-pdf-counter')).toHaveText('2 / 5');

    await dragOnSlidePanel(page, -32, 0);
    await expect(page.getByTestId('reception-pdf-counter')).toHaveText('2 / 5');

    await dragOnSlidePanel(page, -180, 170);
    await expect(page.getByTestId('reception-pdf-counter')).toHaveText('2 / 5');

    await dragOnSlidePanel(page, 180, 6);
    await expect(page.getByTestId('reception-pdf-counter')).toHaveText('1 / 5');
  });
});
