import fs from 'node:fs';
import path from 'node:path';

import { expect, type Page, type Request, type Route } from '@playwright/test';

interface DismissInitialModalOptions {
  closeButtonTimeoutMs?: number;
  closeDelayMs?: number;
  hiddenTimeoutMs?: number;
  welcomeTimeoutMs?: number;
}

export async function dismissInitialModal(
  page: Page,
  {
    closeButtonTimeoutMs = 3_000,
    closeDelayMs = 1_500,
    hiddenTimeoutMs = 10_000,
    welcomeTimeoutMs = 5_000,
  }: DismissInitialModalOptions = {},
) {
  const modal = page.getByRole('dialog');
  const closeButton = page.getByTestId('initial-settings-close');
  if (await closeButton.isVisible({ timeout: closeButtonTimeoutMs }).catch(() => false)) {
    if (closeDelayMs > 0) {
      await page.waitForTimeout(closeDelayMs);
    }
    const deadline = Date.now() + 30_000;
    while (Date.now() < deadline && !(await modal.isHidden().catch(() => false))) {
      await closeButton.click({ timeout: 1_000, force: true }).catch(() => {});
      if (!(await modal.isHidden().catch(() => false))) {
        await closeButton
          .evaluate((button) => {
            if (button instanceof HTMLButtonElement) {
              button.click();
            }
          })
          .catch(() => {});
      }
      await page.waitForTimeout(250);
    }
    await expect(modal).toBeHidden({ timeout: hiddenTimeoutMs });
  }
  await expect(page.getByRole('button', { name: 'Welcome' })).toBeVisible({
    timeout: welcomeTimeoutMs,
  });
}

export async function installDeterministicVoiceRecorder(page: Page): Promise<void> {
  const sampleAudioBase64 = fs
    .readFileSync(path.resolve(__dirname, '../fixtures/voice/sample.wav'))
    .toString('base64');

  await page.addInitScript(({ audioBase64 }) => {
    (window as Window & { __PLAYWRIGHT_VOICE_AUDIO_BASE64__?: string }).__PLAYWRIGHT_VOICE_AUDIO_BASE64__ =
      audioBase64;
  }, { audioBase64: sampleAudioBase64 });
}

export async function installMicDenial(page: Page, errorName: string): Promise<void> {
  await page.addInitScript((name: string) => {
    (window as Window & { __PLAYWRIGHT_VOICE_RECORDER_ERROR_NAME__?: string }).__PLAYWRIGHT_VOICE_RECORDER_ERROR_NAME__ =
      name;
  }, errorName);
}

export async function installIOSUserAgent(page: Page): Promise<void> {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'userAgent', {
      configurable: true,
      value:
        'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
    });
    Object.defineProperty(navigator, 'maxTouchPoints', {
      configurable: true,
      value: 5,
    });
  });
}

export function parseVoiceAction(request: Request): string | undefined {
  const raw = request.postData();
  if (raw) {
    try {
      const parsed = JSON.parse(raw) as { action?: unknown };
      if (typeof parsed.action === 'string') {
        return parsed.action;
      }
    } catch {
      return undefined;
    }
  }

  try {
    const action = new URL(request.url()).searchParams.get('action');
    return action ?? undefined;
  } catch {
    return undefined;
  }
}

export async function failUnexpectedVoiceAction(
  route: Route,
  action: string | undefined,
  allowedActions: readonly string[],
): Promise<never> {
  const printableAction = action ?? '<missing>';
  const message =
    `Unexpected /api/voice action in Playwright mock: ${printableAction}. ` +
    `Allowed actions: ${allowedActions.join(', ')}`;

  await route.fulfill({
    status: 500,
    contentType: 'application/json',
    body: JSON.stringify({ success: false, error: message }),
  });
  throw new Error(message);
}
