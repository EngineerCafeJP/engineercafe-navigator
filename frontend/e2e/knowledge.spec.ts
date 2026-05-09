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

function extractMultipartField(body: string, name: string): string {
  const match = body.match(new RegExp(`name="${name}"\\r\\n\\r\\n([\\s\\S]*?)\\r\\n--`));
  return match?.[1] ?? '';
}

function extractMultipartFilename(body: string): string {
  const match = body.match(/name="file"; filename="([^"]+)"/);
  return match?.[1] ?? '';
}

function buildChunkTitles(baseTitle: string, chunkCount: number): string[] {
  if (chunkCount === 1) {
    return [baseTitle];
  }

  return [
    baseTitle,
    ...Array.from({ length: chunkCount - 1 }, (_, index) => `${baseTitle} [chunk ${index + 1}]`),
  ];
}

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
    await expect(page.getByLabel('アップロードするファイル')).toBeAttached();
    await expect(page.getByLabel(/カテゴリ/)).toBeVisible();
    await expect(page.getByRole('group', { name: '言語' })).toBeVisible();
    await expect(page.getByLabel('タイトル（任意）')).toBeVisible();
  });

  test('Markdownファイルを選択すると解析プレビューが表示される', async ({ page }) => {
    let previewRequests = 0;
    await page.route('/api/admin/knowledge/preview', async (route) => {
      previewRequests += 1;
      return route.fulfill({
        json: {
          file_type: 'markdown',
          extracted_preview: 'サーバーで抽出したMarkdownプレビュー本文です',
          estimated_chunks: 2,
          chunk_titles: ['test', 'test [chunk 1]'],
          total_chars: 1234,
        },
      });
    });

    await page.goto('/admin/knowledge/upload');

    const fileContent = '# テスト\nこれはテストコンテンツです';
    const fileInput = page.getByLabel('アップロードするファイル');

    await fileInput.setInputFiles({
      name: 'test.md',
      mimeType: 'text/markdown',
      buffer: Buffer.from(fileContent),
    });

    await expect(page.getByText('test.md', { exact: true })).toBeVisible({ timeout: 3_000 });
    await expect(page.getByText('# テスト')).toBeVisible({ timeout: 3_000 });
    await expect(page.getByText('サーバーで抽出したMarkdownプレビュー本文です')).toBeVisible();
    await expect(page.getByText('登録予定タイトル（2件）')).toBeVisible();
    await expect(page.getByText('test', { exact: true })).toBeVisible();
    await expect(page.getByText('test [chunk 1]')).toBeVisible();
    expect(previewRequests).toBe(1);
  });

  test('カテゴリ・言語・タイトル変更で解析プレビューを再取得して表示タイトルを更新する', async ({
    page,
  }) => {
    const previewRequests: Array<{
      category: string;
      filename: string;
      language: string;
      title: string;
    }> = [];

    await page.route('/api/admin/knowledge/preview', async (route) => {
      const body = route.request().postDataBuffer()?.toString('utf8') ?? '';
      const request = {
        category: extractMultipartField(body, 'category'),
        filename: extractMultipartFilename(body),
        language: extractMultipartField(body, 'language') || 'ja',
        title: extractMultipartField(body, 'title'),
      };
      previewRequests.push(request);

      const baseTitle = request.filename.replace(/\.[^.]+$/, '');
      const estimatedChunks =
        request.language === 'en' ? 2 : request.category === 'イベント' ? 3 : 1;

      return route.fulfill({
        json: {
          file_type: 'markdown',
          extracted_preview: `${request.category || '未分類'}:${request.language}`,
          estimated_chunks: estimatedChunks,
          chunk_titles: buildChunkTitles(baseTitle, estimatedChunks),
          total_chars: 100 + estimatedChunks,
        },
      });
    });

    await page.goto('/admin/knowledge/upload');

    await page.getByLabel('アップロードするファイル').setInputFiles({
      name: 'refresh.md',
      mimeType: 'text/markdown',
      buffer: Buffer.from('# Refresh\npreview refresh test'),
    });

    await expect(page.getByText('登録予定タイトル（1件）')).toBeVisible({ timeout: 5_000 });
    await expect.poll(() => previewRequests.at(-1)?.filename).toBe('refresh.md');
    await expect.poll(() => previewRequests.at(-1)?.title).toBe('refresh');

    await page.getByLabel(/カテゴリ/).selectOption('イベント');
    await expect(page.getByText('登録予定タイトル（3件）')).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText('refresh [chunk 2]')).toBeVisible();
    await expect.poll(() => previewRequests.at(-1)?.category).toBe('イベント');

    await page.getByRole('radio', { name: 'English' }).check();
    await expect(page.getByText('登録予定タイトル（2件）')).toBeVisible({ timeout: 5_000 });
    await expect.poll(() => previewRequests.at(-1)?.language).toBe('en');

    await page.getByLabel('タイトル（任意）').fill('Custom Preview');
    await expect.poll(() => previewRequests.at(-1)?.title).toBe('Custom Preview');
    await expect(page.getByText('Custom Preview', { exact: true })).toBeVisible({
      timeout: 5_000,
    });
    await expect(page.getByText('Custom Preview [chunk 1]')).toBeVisible();
  });

  test('PDFファイルを選択するとPDF解析プレビューが表示される', async ({ page }) => {
    await page.route('/api/admin/knowledge/preview', async (route) => {
      return route.fulfill({
        json: {
          file_type: 'pdf',
          extracted_preview: 'PDFから抽出した本文プレビューです',
          estimated_chunks: 1,
          chunk_titles: ['report'],
          total_chars: 456,
        },
      });
    });

    await page.goto('/admin/knowledge/upload');

    const fileInput = page.getByLabel('アップロードするファイル');

    await fileInput.setInputFiles({
      name: 'report.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from('%PDF-1.4\nmock pdf'),
    });

    await expect(page.getByText('report.pdf', { exact: true })).toBeVisible({ timeout: 3_000 });
    await expect(page.getByText('PDFから抽出した本文プレビューです')).toBeVisible();
    await expect(page.getByText('PDF', { exact: true })).toBeVisible();
    await expect(page.getByText('登録予定タイトル（1件）')).toBeVisible();
    await expect(page.getByText('report', { exact: true })).toBeVisible();
  });

  test('プレビュー後にキャンセルしてもアップロードしない', async ({ page }) => {
    let uploadRequests = 0;
    await page.route('/api/admin/knowledge/preview', async (route) => {
      return route.fulfill({
        json: {
          file_type: 'markdown',
          extracted_preview: 'キャンセル確認用プレビュー',
          estimated_chunks: 1,
          chunk_titles: ['cancel-check'],
          total_chars: 20,
        },
      });
    });
    await page.route('/api/admin/knowledge/upload', async (route) => {
      uploadRequests += 1;
      return route.fulfill({ json: { success: true } });
    });

    await page.goto('/admin/knowledge/upload');

    await page.getByLabel('アップロードするファイル').setInputFiles({
      name: 'cancel-check.md',
      mimeType: 'text/markdown',
      buffer: Buffer.from('# キャンセル確認'),
    });
    await expect(page.getByText('キャンセル確認用プレビュー')).toBeVisible();

    await page.getByRole('button', { name: /キャンセル|戻る/ }).click();
    await expect(page).toHaveURL(/\/admin\/knowledge$/);
    expect(uploadRequests).toBe(0);
  });
});
