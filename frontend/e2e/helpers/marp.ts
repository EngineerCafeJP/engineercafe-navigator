import { type Page, expect } from '@playwright/test';

export async function gotoGuide(
  page: Page,
  lang: 'ja' | 'en' = 'ja',
  options?: { autoplay?: boolean },
) {
  const params = new URLSearchParams({ lang });
  if (options?.autoplay) {
    params.set('autoplay', '1');
  }

  await page.goto(`/guide?${params.toString()}`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('customer-guide-shell')).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId('marp-viewer')).toBeVisible({ timeout: 15_000 });
}

export async function waitForSlide(
  page: Page,
  slideNumber: number,
  totalSlides: number,
  timeout = 15_000,
) {
  const expectedText = `${slideNumber} / ${totalSlides}`;
  await expect(page.getByTestId('marp-slide-counter')).toBeVisible({ timeout });
  await expect(page.getByTestId('marp-slide-counter')).toHaveText(expectedText, { timeout });
}

export async function clickPrevSlide(page: Page) {
  await page.getByTestId('marp-prev-button').click();
}

export async function clickPlayPause(page: Page) {
  await page.getByTestId('marp-play-pause-button').click();
}

export async function clickReset(page: Page) {
  await page.getByTestId('marp-reset-button').click();
}

export async function clickSwitchToEnglish(page: Page) {
  await page.getByTestId('guide-language-toggle').click();
}

export async function waitForVoiceRequest(page: Page, expectedCount = 1, timeout = 5_000) {
  const voiceRequests: string[] = [];

  await page.route('/api/voice', (route) => {
    voiceRequests.push(route.request().url());
    return route.continue();
  });

  await expect.poll(() => voiceRequests.length, { timeout }).toBe(expectedCount);
}
