import fs from 'node:fs';
import path from 'node:path';

import { expect, test } from '@playwright/test';

async function dismissInitialModal(page: import('@playwright/test').Page) {
  const modal = page.getByRole('dialog');
  const closeButton = page.getByTestId('initial-settings-close');
  if (await closeButton.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await closeButton.click({ force: true }).catch(() => {});
    await expect(modal).toBeHidden({ timeout: 10_000 });
  }
  await expect(page.getByRole('button', { name: 'Welcome' })).toBeVisible({ timeout: 5_000 });
}

test.describe('Slide PDF narration deck (#624)', () => {
  test('five-page autoplay triggers Piper TTS per slide', async ({ page }) => {
    test.skip(
      process.env.NEXT_PUBLIC_RECEPTION_SLIDE_RENDERER === 'marp',
      'PDF narration tests require PDF renderer',
    );

    await page.route('**/api/reception/start', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          reception_session_id: 'mock-slide-narration',
          greeting: 'テストです。',
          stage: 'greeting',
        }),
      });
    });

    const wavB64 = fs.readFileSync(path.resolve(__dirname, 'fixtures/voice/sample.wav')).toString('base64');

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
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ success: true, audioResponse: wavB64 }),
        });
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

    await expect(page.getByTestId('reception-pdf-counter')).toHaveText('1 / 5', {
      timeout: 15_000,
    });
    await expect(page.getByTestId('reception-pdf-play')).toHaveAttribute('data-state', 'playing', {
      timeout: 15_000,
    });

    await expect.poll(() => piperHits, { timeout: 45_000 }).toBeGreaterThanOrEqual(5);
  });
});
