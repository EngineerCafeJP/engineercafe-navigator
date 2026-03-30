import { expect, test } from '@playwright/test';
import { dismissInitialSettingsModal } from './helpers/home';
import { gotoGuide } from './helpers/marp';

test.describe('Navigation', () => {
  test('opens the onboarding guide and returns to the reception screen', async ({ page }) => {
    await gotoGuide(page, 'ja');
    await Promise.all([
      page.waitForURL(/\/$/, { timeout: 60_000, waitUntil: 'domcontentloaded' }),
      page.getByTestId('guide-back-button').click(),
    ]);

    await dismissInitialSettingsModal(page);
    await expect(page.getByTestId('response-bubble')).toBeVisible();
  });

  test('switches onboarding language without leaving the page', async ({ page }) => {
    await page.goto('/onboarding?lang=en');
    await expect(page.getByRole('heading', { name: 'First Visit Registration Guide' })).toBeVisible();

    await Promise.all([
      page.waitForURL(/\/onboarding\?lang=ja$/, { timeout: 30_000 }),
      page.getByTestId('guide-language-toggle').click(),
    ]);

    await expect(page).toHaveURL(/\/onboarding\?lang=ja$/);
    await expect(page.getByTestId('customer-guide-shell')).toBeVisible();
  });

  test('shows a 404 response for an unknown route', async ({ page }) => {
    const response = await page.goto('/this-page-does-not-exist-139');

    expect(response).not.toBeNull();
    expect(response?.status()).toBe(404);
    await expect(page.locator('body')).not.toBeEmpty();
  });
});
