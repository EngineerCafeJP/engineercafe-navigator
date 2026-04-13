import { expect, test } from '@playwright/test';
import { dismissInitialSettingsModal } from './helpers/home';

test.describe('WebGL fallback', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      const orig = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = function (
        this: HTMLCanvasElement,
        contextId: unknown,
        ...args: unknown[]
      ) {
        if (
          contextId === 'webgl' ||
          contextId === 'webgl2' ||
          contextId === 'experimental-webgl'
        ) {
          return null;
        }
        return (orig as (this: HTMLCanvasElement, ...a: unknown[]) => unknown).apply(this, [
          contextId,
          ...args,
        ]);
      };
    });
  });

  test('shows static avatar when WebGL is unavailable', async ({ page }) => {
    const response = await page.goto('/');
    expect(response).not.toBeNull();
    expect(response?.status()).toBe(200);
    await dismissInitialSettingsModal(page);
    await expect(page.getByTestId('character-avatar-root')).toHaveAttribute(
      'data-avatar-render-mode',
      'fallback',
    );
    await expect(page.getByTestId('character-avatar-fallback')).toBeVisible();
    await expect(page.getByTestId('response-bubble')).toBeVisible();
    await expect(page.getByTestId('kiosk-voice-button')).toBeVisible();
    await expect(page.getByTestId('kiosk-settings-button')).toBeVisible();
    await expect(page.getByTestId('kiosk-slides-button')).toBeVisible();
  });
});
