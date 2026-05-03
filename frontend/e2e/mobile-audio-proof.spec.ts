import { expect, test } from '@playwright/test';

import { MOCK_VOICE_RESPONSE, setupMarpMocks, setupWebAudioMock } from './helpers/mocks';
import { clickPlayPause, gotoGuide, waitForSlide } from './helpers/marp';

test.describe('mobile audio proof harness (#697/#698)', () => {
  test.beforeEach(async ({ page }) => {
    await setupWebAudioMock(page);
    await setupMarpMocks(page);
  });

  test('mobile WebKit-style slide narration survives delayed TTS before playback', async ({
    page,
  }) => {
    const voiceRequests: Array<Record<string, unknown>> = [];

    await page.route('/api/voice', async (route) => {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      voiceRequests.push(body);
      await new Promise((resolve) => setTimeout(resolve, 750));
      await route.fulfill({ json: MOCK_VOICE_RESPONSE });
    });

    await gotoGuide(page, 'ja');
    await waitForSlide(page, 1, 3);

    await clickPlayPause(page);

    await expect
      .poll(() => voiceRequests.filter((body) => body.action === 'text_to_speech').length, {
        timeout: 10_000,
      })
      .toBeGreaterThan(0);
    await waitForSlide(page, 2, 3);
  });
});
