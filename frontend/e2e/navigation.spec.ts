import { expect, test } from '@playwright/test';

test.describe('Navigation', () => {
  test('opens the onboarding guide and returns to the reception screen', async ({ page }) => {
    await page.goto('/guide?lang=ja');

    await expect(page.getByTestId('customer-guide-shell')).toBeVisible();
    await expect(page.getByRole('heading', { name: '初回登録ガイド' })).toBeVisible();

    await page.getByRole('button', { name: '受付画面に戻る' }).click();

    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByTestId('response-bubble')).toBeVisible();
  });

  test('switches onboarding language without leaving the page', async ({ page }) => {
    await page.goto('/onboarding?lang=en');

    await expect(page.getByRole('heading', { name: 'First Visit Registration Guide' })).toBeVisible();

    await page.getByRole('button', { name: 'Switch to Japanese' }).click();

    await expect(page).toHaveURL(/\/onboarding\?lang=ja$/);
    await expect(page.getByRole('heading', { name: '初回登録ガイド' })).toBeVisible();
  });

  test('shows a 404 response for an unknown route', async ({ page }) => {
    const response = await page.goto('/this-page-does-not-exist-139');

    expect(response).not.toBeNull();
    expect(response?.status()).toBe(404);
    await expect(page.locator('body')).not.toBeEmpty();
  });
});
