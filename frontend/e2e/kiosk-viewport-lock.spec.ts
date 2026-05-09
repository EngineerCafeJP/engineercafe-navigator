import { expect, test } from '@playwright/test';

async function dismissInitialModal(page: import('@playwright/test').Page) {
  const closeButton = page.getByTestId('initial-settings-close');
  if (await closeButton.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await closeButton.click();
  }
  await expect(page.getByRole('button', { name: 'Welcome' })).toBeVisible({ timeout: 5_000 });
}

async function collectViewportMetrics(page: import('@playwright/test').Page) {
  return page.evaluate(() => {
    const root = document.querySelector<HTMLElement>('[data-testid="kiosk-viewport-root"]');
    const rect = root?.getBoundingClientRect();
    const avatar = document.querySelector<HTMLElement>('[data-testid="character-avatar-root"]');
    const avatarRect = avatar?.getBoundingClientRect();
    const avatarCanvasRect = avatar?.querySelector('canvas')?.getBoundingClientRect();
    const htmlStyle = getComputedStyle(document.documentElement);
    const bodyStyle = getComputedStyle(document.body);
    return {
      avatar: avatarRect
        ? {
            height: avatarRect.height,
            width: avatarRect.width,
          }
        : null,
      avatarCanvas: avatarCanvasRect
        ? {
            height: avatarCanvasRect.height,
            width: avatarCanvasRect.width,
          }
        : null,
      bodyOverflowY: bodyStyle.overflowY,
      bodyPosition: bodyStyle.position,
      docScrollHeight: document.documentElement.scrollHeight,
      htmlHasLock: document.documentElement.classList.contains('kiosk-viewport-lock'),
      htmlOverflowY: htmlStyle.overflowY,
      innerHeight: window.innerHeight,
      innerWidth: window.innerWidth,
      root: rect
        ? {
            bottom: rect.bottom,
            height: rect.height,
            left: rect.left,
            right: rect.right,
            top: rect.top,
            width: rect.width,
          }
        : null,
      scrollX: window.scrollX,
      scrollY: window.scrollY,
    };
  });
}

test.describe('Kiosk viewport lock', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await dismissInitialModal(page);
  });

  test('keeps the kiosk root fixed to the viewport through orientation-sized resizes', async ({
    page,
  }) => {
    await expect(page.locator('meta[name="viewport"]')).toHaveAttribute(
      'content',
      /user-scalable=no/,
    );
    await expect(page.locator('meta[name="viewport"]')).toHaveAttribute(
      'content',
      /viewport-fit=cover/,
    );

    for (const size of [
      { width: 390, height: 844 },
      { width: 844, height: 390 },
      { width: 390, height: 844 },
    ]) {
      await page.setViewportSize(size);
      await page.waitForTimeout(900);
      await page.evaluate(() => window.scrollTo(0, 240));
      await page.waitForTimeout(100);

      const metrics = await collectViewportMetrics(page);
      expect(metrics.htmlHasLock).toBe(true);
      expect(metrics.htmlOverflowY).toBe('hidden');
      expect(metrics.bodyOverflowY).toBe('hidden');
      expect(metrics.bodyPosition).toBe('fixed');
      expect(metrics.scrollX).toBe(0);
      expect(metrics.scrollY).toBe(0);
      expect(metrics.root).not.toBeNull();
      expect(metrics.root?.top).toBeGreaterThanOrEqual(-1);
      expect(metrics.root?.left).toBeGreaterThanOrEqual(-1);
      expect(Math.abs((metrics.root?.width ?? 0) - metrics.innerWidth)).toBeLessThanOrEqual(1);
      expect(Math.abs((metrics.root?.height ?? 0) - metrics.innerHeight)).toBeLessThanOrEqual(1);
      expect(Math.abs((metrics.avatar?.height ?? 0) - metrics.innerHeight)).toBeLessThanOrEqual(1);
      if (metrics.avatarCanvas) {
        expect(Math.abs(metrics.avatarCanvas.height - metrics.innerHeight)).toBeLessThanOrEqual(1);
      }
      expect(metrics.docScrollHeight).toBeLessThanOrEqual(metrics.innerHeight + 1);
    }
  });

  test('prevents native vertical panning on the slide surface after rotating', async ({ page }) => {
    await page.route('**/api/reception/start', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          reception_session_id: 'mock-viewport-lock',
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

    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByTestId('kiosk-slides-button').click();
    await page.getByTestId('slide-language-ja').click();
    await expect(page.getByTestId('reception-pdf-rotate-hint')).toBeVisible({ timeout: 8_000 });

    await page.setViewportSize({ width: 844, height: 390 });
    await expect(page.getByTestId('reception-pdf-landscape-panel')).toBeVisible({
      timeout: 15_000,
    });

    const touchAction = await page
      .getByTestId('reception-pdf-landscape-panel')
      .evaluate((node) => getComputedStyle(node).touchAction);
    expect(touchAction).toBe('none');
  });
});
