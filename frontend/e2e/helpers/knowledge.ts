import { type Page, expect } from '@playwright/test';

export async function gotoKnowledgeList(page: Page) {
  await page.goto('/admin/knowledge');
  await expect(page.getByRole('table')).toBeVisible({ timeout: 10_000 });
}

export async function gotoKnowledgeNew(page: Page) {
  await page.goto('/admin/knowledge/new');
  await expect(page.locator('#title')).toBeVisible({ timeout: 10_000 });
}

export async function gotoKnowledgeDetail(page: Page, id: string) {
  await page.goto(`/admin/knowledge/${id}`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible({ timeout: 10_000 });
}

export async function fillKnowledgeForm(
  page: Page,
  data: {
    title?: string;
    category?: string;
    subcategory?: string;
    content?: string;
    language?: string;
  },
) {
  if (data.title) {
    await page.locator('#title').fill(data.title);
  }

  if (data.category) {
    const categorySelect = page.locator('#category');
    const options = await categorySelect.locator('option').count();
    let categoryExists = false;

    for (let i = 0; i < options; i++) {
      const text = await categorySelect.locator('option').nth(i).textContent();
      if (text === data.category) {
        categoryExists = true;
        break;
      }
    }

    if (categoryExists) {
      await categorySelect.selectOption(data.category);
    }
  }

  if (data.subcategory && data.category) {
    await page.locator('#subcategory').selectOption(data.subcategory);
  }

  if (data.content) {
    const mdEditorTextarea = page.locator('.w-md-editor-text-input');
    await expect(mdEditorTextarea).toBeVisible({ timeout: 5_000 });
    await mdEditorTextarea.fill(data.content);
  }

  if (data.language) {
    await page.locator('#language').selectOption(data.language);
  }
}

export function acceptDialog(page: Page) {
  page.on('dialog', (dialog) => {
    void dialog.accept();
  });
}

export function dismissDialog(page: Page) {
  page.on('dialog', (dialog) => {
    void dialog.dismiss();
  });
}

export async function waitForToast(page: Page, text: string, timeout = 5_000) {
  await expect(page.locator('[role="status"]').filter({ hasText: text }).first()).toBeVisible({
    timeout,
  });
}
