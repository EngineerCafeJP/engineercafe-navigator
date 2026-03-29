import { expect, type Page } from '@playwright/test';

export async function dismissInitialSettingsModal(page: Page, timeout = 10_000) {
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible({ timeout });
  await page.getByTestId('initial-settings-close').click();
  await expect
    .poll(async () => {
      const isHidden = await dialog.isHidden().catch(() => true);
      const bubbleVisible = await page.getByTestId('response-bubble').isVisible().catch(() => false);
      return isHidden || bubbleVisible;
    }, { timeout })
    .toBe(true);
}
