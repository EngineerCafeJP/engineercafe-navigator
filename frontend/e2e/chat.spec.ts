import { expect, test } from '@playwright/test';

const backendUrl = process.env.BACKEND_API_URL;
const backendKey = process.env.BACKEND_API_KEY;
const hasChatBackend = Boolean(backendUrl && backendKey);
const defaultPrompt = 'マイクを押して、エンジニアカフェについて聞いてください。';

test.describe('Chat flow', () => {
  test.skip(!hasChatBackend, 'Chat E2E requires BACKEND_API_URL and BACKEND_API_KEY in frontend/.env.local');

  test('submits a text question and renders the assistant response', async ({ page }) => {
    await page.goto('/');

    await page.getByTestId('text-input-toggle').click();

    const textarea = page.getByLabel('ここに質問を入力します');
    await expect(textarea).toBeVisible();
    await textarea.fill('営業時間を教えてください');

    const sendButton = page.getByRole('button', { name: '送信' });
    await expect(sendButton).toBeEnabled();
    await sendButton.click();

    await expect(textarea).toHaveValue('');
    await expect(sendButton).toBeDisabled();
    await expect(sendButton).toBeEnabled({ timeout: 60_000 });
    await expect(page.getByTestId('response-text')).not.toHaveText(defaultPrompt);
    await expect
      .poll(
        async () => ((await page.getByTestId('response-text').textContent()) ?? '').trim().length,
        { timeout: 5_000 },
      )
      .toBeGreaterThan(0);
    await expect(page.getByText('Internal server error')).toHaveCount(0);
  });
});
