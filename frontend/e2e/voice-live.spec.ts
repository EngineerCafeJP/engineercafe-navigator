import { expect, test } from '@playwright/test';
import { dismissInitialSettingsModal } from './helpers/home';

const voiceLive = process.env.PLAYWRIGHT_VOICE_LIVE === '1';

test.describe('Voice live (optional)', () => {
  /**
   * Phase 3: full harness (getUserMedia stub + real /api/voice + /api/qa) is not wired here yet.
   * When PLAYWRIGHT_VOICE_LIVE=1, this smoke runs against the dev server (no extra secrets).
   */
  test('kiosk shell loads with PLAYWRIGHT_VOICE_LIVE=1', async ({ page }) => {
    test.skip(
      !voiceLive,
      'Set PLAYWRIGHT_VOICE_LIVE=1 and live backend env for real voice E2E',
    );
    const response = await page.goto('/');
    expect(response?.status()).toBe(200);
    await dismissInitialSettingsModal(page);
    await expect(page.getByTestId('kiosk-voice-button')).toBeVisible();
  });
});
