import { expect, test } from '@playwright/test';
import {
  MOCK_EDITOR_CONFIG,
  MOCK_KNOWLEDGE_ENTRY,
  MOCK_KNOWLEDGE_LIST,
} from './helpers/mocks';
import {
  acceptDialog,
  dismissDialog,
  fillKnowledgeForm,
  gotoKnowledgeDetail,
  gotoKnowledgeList,
  gotoKnowledgeNew,
  waitForToast,
} from './helpers/knowledge';

test.describe('Knowledge 一覧ページ', () => {
  test.beforeEach(async ({ page }) => {
    await page.route(/\/api\/admin\/knowledge(\?|$)/, async (route) => {
      return route.fulfill({ json: MOCK_KNOWLEDGE_LIST });
    });
    await page.route('/api/admin/knowledge/editor-config', async (route) => {
      return route.fulfill({ json: MOCK_EDITOR_CONFIG });
    });
    await page.route(/\/api\/admin\/knowledge\/entry-[^/]+($|\?)/, async (route) => {
      const method = route.request().method();
      if (method === 'GET') {
        return route.fulfill({ json: MOCK_KNOWLEDGE_ENTRY });
      }
      if (method === 'DELETE') {
        return route.fulfill({ json: { success: true } });
      }
      return route.continue();
    });
  });

  test('エントリ一覧が表示される', async ({ page }) => {
    await gotoKnowledgeList(page);

    await expect(page.getByText(MOCK_KNOWLEDGE_ENTRY.title)).toBeVisible();
    await expect(page.getByRole('link', { name: '詳細' })).toBeVisible();
    await expect(page.getByRole('button', { name: '削除' })).toBeVisible();
  });

  test('新規作成リンクが /admin/knowledge/new に遷移する', async ({ page }) => {
    await gotoKnowledgeList(page);

    await page.getByRole('link', { name: /新規作成|新規登録/ }).click();
    await expect(page).toHaveURL(/\/admin\/knowledge\/new$/);
  });

  test('言語フィルタで絞り込める', async ({ page }) => {
    await gotoKnowledgeList(page);

    const languageSelect = page.getByLabel('言語');
    await expect(languageSelect).toBeVisible();
    await languageSelect.selectOption('ja');
    await page.getByRole('button', { name: /検索|適用|更新/ }).click();
    await expect(page.getByRole('table')).toBeVisible();
  });

  test('削除ダイアログを承認すると削除される', async ({ page }) => {
    acceptDialog(page);

    await gotoKnowledgeList(page);
    await page.getByRole('button', { name: '削除' }).first().click();

    await waitForToast(page, '削除');
  });

  test('削除ダイアログをキャンセルすると削除されない', async ({ page }) => {
    dismissDialog(page);

    let deleteRequestMade = false;
    await page.route(/\/api\/admin\/knowledge\/entry-[^/]+($|\?)/, async (route) => {
      if (route.request().method() === 'DELETE') {
        deleteRequestMade = true;
        return route.fulfill({ json: { success: true } });
      }
      return route.continue();
    });

    await gotoKnowledgeList(page);
    await page.getByRole('button', { name: '削除' }).first().click();

    await expect(page.getByText(MOCK_KNOWLEDGE_ENTRY.title)).toBeVisible();
    expect(deleteRequestMade).toBe(false);
  });
});

test.describe('Knowledge 新規作成ページ', () => {
  test.beforeEach(async ({ page }) => {
    await page.route(/\/api\/admin\/knowledge(\?|$)/, async (route) => {
      const method = route.request().method();
      if (method === 'GET') {
        return route.fulfill({ json: MOCK_KNOWLEDGE_LIST });
      }
      if (method === 'POST') {
        return route.fulfill({ status: 201, json: { ...MOCK_KNOWLEDGE_ENTRY, id: 'new-001' } });
      }
      return route.continue();
    });
    await page.route('/api/admin/knowledge/editor-config', async (route) => {
      return route.fulfill({ json: MOCK_EDITOR_CONFIG });
    });
  });

  test('フォームが表示されてカテゴリ選択肢が読み込まれる', async ({ page }) => {
    await gotoKnowledgeNew(page);

    await expect(page.locator('#title')).toBeVisible();
    await expect(page.locator('#category')).toBeVisible();
    await expect(
      page.locator('#category option', { hasText: MOCK_EDITOR_CONFIG.categories[0] }),
    ).toBeAttached();
  });

  test('タイトルが空だと保存できない', async ({ page }) => {
    await gotoKnowledgeNew(page);
    let postCount = 0;
    page.on('request', (request) => {
      if (request.method() === 'POST' && request.url().includes('/api/admin/knowledge')) {
        postCount += 1;
      }
    });

    const mdEditorTextarea = page.locator('.w-md-editor-text-input');
    await expect(mdEditorTextarea).toBeVisible({ timeout: 5_000 });
    await mdEditorTextarea.fill('テストコンテンツ');

    await page.getByRole('button', { name: /作成|保存/ }).click();
    await expect(page).toHaveURL(/\/admin\/knowledge\/new$/);
    expect(postCount).toBe(0);
  });

  test('コンテンツが空だと保存できない', async ({ page }) => {
    await gotoKnowledgeNew(page);

    await page.locator('#title').fill('テストタイトル');
    await page.getByRole('button', { name: /作成|保存/ }).click();

    await expect(
      page.locator('[role="status"]').filter({ hasText: /コンテンツ.*必須/ }).first(),
    ).toBeVisible({ timeout: 3_000 });
  });

  test('カテゴリを選択するとサブカテゴリが有効になる', async ({ page }) => {
    await gotoKnowledgeNew(page);

    const subcategorySelect = page.locator('#subcategory');
    await expect(subcategorySelect).toBeDisabled();

    await page.locator('#category').selectOption(MOCK_EDITOR_CONFIG.categories[0]);
    await expect(subcategorySelect).toBeEnabled({ timeout: 3_000 });
  });

  test('正常に作成して一覧に遷移する', async ({ page }) => {
    await gotoKnowledgeNew(page);

    await fillKnowledgeForm(page, {
      title: '新しいエントリ',
      category: MOCK_EDITOR_CONFIG.categories[0],
      content: '新しいコンテンツ',
      language: 'ja',
    });

    await page.getByRole('button', { name: /作成|保存/ }).click();
    await expect(page).toHaveURL(/\/admin\/knowledge$/, { timeout: 5_000 });
  });

  test('キャンセルで一覧に戻る', async ({ page }) => {
    await gotoKnowledgeNew(page);

    await page.getByRole('button', { name: /キャンセル|戻る/ }).click();
    await expect(page).toHaveURL(/\/admin\/knowledge$/);
  });
});

test.describe('Knowledge 詳細ページ', () => {
  test.beforeEach(async ({ page }) => {
    await page.route(/\/api\/admin\/knowledge\/entry-[^/]+($|\?)/, async (route) => {
      const method = route.request().method();
      if (method === 'GET') {
        return route.fulfill({ json: MOCK_KNOWLEDGE_ENTRY });
      }
      if (method === 'DELETE') {
        return route.fulfill({ json: { success: true } });
      }
      return route.continue();
    });
    await page.route('/api/admin/knowledge/editor-config', async (route) => {
      return route.fulfill({ json: MOCK_EDITOR_CONFIG });
    });
  });

  test('エントリ詳細が表示される', async ({ page }) => {
    await gotoKnowledgeDetail(page, MOCK_KNOWLEDGE_ENTRY.id);

    await expect(page.getByText(MOCK_KNOWLEDGE_ENTRY.title)).toBeVisible();
    await expect(page.getByText(MOCK_KNOWLEDGE_ENTRY.category!)).toBeVisible();
    await expect(page.getByRole('button', { name: '編集' })).toBeVisible();
    await expect(page.getByRole('button', { name: '削除' })).toBeVisible();
  });

  test('編集ボタンで編集モードに切り替わる', async ({ page }) => {
    await gotoKnowledgeDetail(page, MOCK_KNOWLEDGE_ENTRY.id);

    await page.getByRole('button', { name: '編集' }).click();
    await expect(page.locator('#title')).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('heading', { name: /編集|修正|更新/ })).toBeVisible();
  });

  test('削除確認で一覧にリダイレクトされる', async ({ page }) => {
    acceptDialog(page);

    await gotoKnowledgeDetail(page, MOCK_KNOWLEDGE_ENTRY.id);
    await page.getByRole('button', { name: '削除' }).click();

    await expect(page).toHaveURL(/\/admin\/knowledge$/, { timeout: 5_000 });
  });

  test('「一覧に戻る」リンクで一覧に遷移する', async ({ page }) => {
    await gotoKnowledgeDetail(page, MOCK_KNOWLEDGE_ENTRY.id);

    await page.getByRole('link', { name: /一覧に戻る|一覧/ }).first().click();
    await expect(page).toHaveURL(/\/admin\/knowledge$/);
  });
});

test.describe('Knowledge アップロードページ', () => {
  test.beforeEach(async ({ page }) => {
    await page.route(/\/api\/admin\/knowledge(\?|$)/, async (route) => {
      return route.fulfill({ json: MOCK_KNOWLEDGE_LIST });
    });
    await page.route('/api/admin/knowledge/editor-config', async (route) => {
      return route.fulfill({ json: MOCK_EDITOR_CONFIG });
    });
  });

  test('ページが表示されてファイル選択エリアがある', async ({ page }) => {
    await page.goto('/admin/knowledge/upload');

    await expect(page.getByRole('heading', { name: /アップロード|ファイル/ })).toBeVisible();
    await expect(page.getByText('☁ ファイルをドラッグ&ドロップ')).toBeVisible();
  });

  test('Markdownファイルを選択するとプレビューが表示される', async ({ page }) => {
    await page.goto('/admin/knowledge/upload');

    const fileContent = '# テスト\nこれはテストコンテンツです';
    const fileInput = page.locator('input[type="file"]').first();

    await fileInput.setInputFiles({
      name: 'test.md',
      mimeType: 'text/markdown',
      buffer: Buffer.from(fileContent),
    });

    await expect(page.getByText('test.md', { exact: true })).toBeVisible({ timeout: 3_000 });
    await expect(page.getByText('# テスト')).toBeVisible({ timeout: 3_000 });
  });

  test('キャンセルで一覧に戻る', async ({ page }) => {
    await page.goto('/admin/knowledge/upload');

    await page.getByRole('button', { name: /キャンセル|戻る/ }).click();
    await expect(page).toHaveURL(/\/admin\/knowledge$/);
  });
});
