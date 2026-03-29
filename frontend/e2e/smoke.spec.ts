import { expect, test } from '@playwright/test';
import { dismissInitialSettingsModal } from './helpers/home';

test.describe('Smoke tests', () => {
  test('loads the home page and renders the main UI shell', async ({ page }) => {
    const response = await page.goto('/');

    expect(response).not.toBeNull();
    expect(response?.status()).toBe(200);

    await expect(page).toHaveTitle(/Engineer Cafe Navigator/);
    await expect(page.locator('html')).toHaveAttribute('lang', 'ja');
    await expect(page.locator('main')).toBeVisible();
    await dismissInitialSettingsModal(page);
    await expect(page.getByTestId('response-bubble')).toBeVisible();
    await expect(page.getByTestId('response-text')).toContainText(
      'マイクを押して、エンジニアカフェについて聞いてください。',
    );
    await expect(page.getByTestId('kiosk-voice-button')).toBeVisible();
    await expect(page.getByTestId('kiosk-settings-button')).toBeVisible();
    await expect(page.getByTestId('kiosk-slides-button')).toBeVisible();
  });
});
