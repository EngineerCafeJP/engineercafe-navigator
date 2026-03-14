# Knowledge Base ファイルアップロード機能 - 実装ガイド

**実装日**: 2026-03-14
**ブランチ**: `feat/new-knowledge-ui`
**対応フロント機能**: Knowledge Base 管理画面に専用アップロードページを追加

---

## 📋 概要

Knowledge Base 管理画面（`/admin/knowledge`）に、PDFまたはMarkdownファイルをアップロードしてナレッジを登録できる専用ページを実装しました。

**主な特徴**:
- ドラッグ&ドロップ対応
- ファイルプレビュー表示（Markdown）
- 自動タイトル生成
- バリデーション（Zod）
- エラーハンドリング

---

## 🔄 変更内容

### 1. API クライアント更新: `frontend/src/lib/api/knowledge.ts`

#### 変更: `uploadKnowledgeFile` 関数のシグネチャ

**Before**:
```typescript
export async function uploadKnowledgeFile(
  file: File
): Promise<{ filename: string; url: string }>
```

**After**:
```typescript
export async function uploadKnowledgeFile(params: {
  file: File;
  category: string;
  language: string;
  title?: string;
}): Promise<KnowledgeItem>
```

**変更点**:
- `category` と `language` を FormData で送信
- 戻り値を `KnowledgeItem` に変更（バックエンドの実際のレスポンス構造に合わせる）

---

### 2. リストページ更新: `frontend/src/app/(admin)/admin/knowledge/page.tsx`

#### 追加: ヘッダーにアップロードボタン

```tsx
<div className="flex gap-3">
  <Link
    href="/admin/knowledge/upload"
    className="bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700 transition-colors"
  >
    ファイルアップロード
  </Link>
  <Link href="/admin/knowledge/new" className="bg-blue-600 ...">
    新規作成
  </Link>
</div>
```

**設計**:
- 「ファイルアップロード」ボタンを緑色で区別
- 「新規作成」ボタンと隣り合わせで配置

---

### 3. アップロードページ: `frontend/src/app/(admin)/admin/knowledge/upload/page.tsx` (新規)

#### アーキテクチャ: オーケストレーター パターン

vosk-settings の create/page.tsx パターンに準拠。

**責務**:
- State 管理（file, category, language, title, preview, uploading, isDragOver）
- エディタ設定の読み込み（`getKnowledgeEditorConfig()`）
- ファイル検証とプレビュー生成
- エラーハンドリング
- ナビゲーション制御

**State フロー**:
```
User selects file
  ↓
handleFileSelect()
  ├─ 拡張子チェック (.pdf, .md, .markdown)
  ├─ サイズチェック (10MB超はエラー)
  ├─ Markdown: file.text() → テキストプレビュー取得
  ├─ PDF: textPreview = null（ブラウザ抽出非対応）
  └─ title が空の場合、ファイル名から自動入力

User fills form & clicks Upload
  ↓
handleUpload()
  ├─ バリデーション（file, category）
  ├─ uploadKnowledgeFile() API呼び出し
  └─ router.push('/admin/knowledge') リダイレクト
```

---

### 4. UI コンポーネント: `frontend/src/app/(admin)/admin/knowledge/components/KnowledgeUploadForm.tsx` (新規)

#### 特徴: 純粋 UI コンポーネント

**Props**:
```typescript
interface KnowledgeUploadFormProps {
  // State
  file: File | null;
  preview: Preview | null;
  isDragOver: boolean;
  category: string;
  language: 'ja' | 'en';
  title: string;
  editorConfig: KnowledgeEditorConfig | null;
  configLoading: boolean;
  uploading: boolean;

  // Handlers
  onFileSelect: (file: File) => void;
  onDragOver: () => void;
  onDragLeave: () => void;
  onDrop: (e: React.DragEvent<HTMLDivElement>) => void;
  onCategoryChange: (category: string) => void;
  onLanguageChange: (language: 'ja' | 'en') => void;
  onTitleChange: (title: string) => void;
  onUpload: () => void;
  onCancel: () => void;
}
```

**レイアウト**:
1. ドロップゾーン（dashed border、isDragOver で青くハイライト）
2. プレビューパネル（ファイル選択後のみ表示）
   - Markdown: テキストプレビュー＋文字数
   - PDF: "非対応" メッセージ
3. カテゴリ select（configLoading 中はスケルトン）
4. 言語 radio（日本語 / English）
5. タイトル input（maxLength=200）
6. [キャンセル] [アップロード] ボタン

---

### 5. バリデーション: `frontend/src/app/(admin)/admin/knowledge/utils/validation.ts` (新規)

#### Zod スキーマ

vosk のパターンに準拠。

```typescript
const uploadSchema = z.object({
  file: z.instanceof(File)
    .refine(
      (file) => {
        const ext = file.name.split('.').pop()?.toLowerCase();
        return ext && ['pdf', 'md', 'markdown'].includes(ext);
      },
      'PDF または Markdown ファイルのみ対応'
    )
    .refine(
      (file) => file.size <= 10 * 1024 * 1024,
      'ファイルサイズは 10MB 以内'
    ),
  category: z.string().min(1, 'カテゴリは必須'),
  language: z.enum(['ja', 'en']),
  title: z.string().max(200).optional(),
});
```

#### 関数

- `validateKnowledgeUploadForm()`: フィールド単位のエラーを返す
- `transformKnowledgeUploadData()`: API送信用にデータを変換

---

### 6. テンプレート: `public/templates/knowledge-template.md` (新規)

ユーザー向けのダウンロード可能なテンプレート。

**内容**:
- 複数エントリのサンプル（会議室予約、Wi-Fi設定）
- 記入例と説明
- カテゴリ一覧

**用途**:
- アップロードページから `<a href="/templates/knowledge-template.md">` でダウンロード提供
- ユーザーがテンプレートをコピーして複数登録

---

## 📊 影響範囲

| ファイル | 変更種別 | 用途 |
|---------|---------|------|
| `frontend/src/lib/api/knowledge.ts` | 修正 | API クライアント - uploadKnowledgeFile 更新 |
| `frontend/src/app/(admin)/admin/knowledge/page.tsx` | 修正 | リストページ - アップロードボタン追加 |
| `frontend/src/app/(admin)/admin/knowledge/upload/page.tsx` | **新規** | アップロードページ（オーケストレーター） |
| `frontend/src/app/(admin)/admin/knowledge/components/KnowledgeUploadForm.tsx` | **新規** | UI コンポーネント |
| `frontend/src/app/(admin)/admin/knowledge/utils/validation.ts` | **新規** | Zod バリデーション |
| `public/templates/knowledge-template.md` | **新規** | ユーザー向けテンプレート |

**合計**: 5 新規ファイル、2 ファイル修正

---

## ✅ 検証チェックリスト

### フロントエンド
- [x] TypeScript typecheck パス
- [x] ESLint lint パス
- [x] Next.js build パス
- [x] ページアクセス動作確認
- [x] ドラッグ&ドロップ機能
- [x] ファイルプレビュー表示
- [x] エラーハンドリング

### バックエンド
- [x] `/api/knowledge/upload` エンドポイント既存（既実装）
- [x] FormData パラメータ対応（category, language, title）

### 統合
- [x] API クライアント連携
- [x] エディタ設定の動的読み込み
- [x] アップロード成功後のリダイレクト

---

## 🎯 ユーザー向けワークフロー

### 単一ファイルアップロード
1. `/admin/knowledge/upload` にアクセス
2. ファイルをドラッグ&ドロップまたは「ファイルを選択」
3. カテゴリ・言語を選択
4. （オプション）タイトルを入力
5. 「アップロード」ボタンをクリック
6. リストページへ自動リダイレクト

### 複数ファイル登録テンプレート
1. `/templates/knowledge-template.md` をダウンロード
2. テンプレートをコピーして複数エントリを記入
3. 各ファイルを順番にアップロード

---

## 🔧 トラブルシューティング

### Q. ファイルアップロード時に 500 エラー
**A.** ブラウザキャッシュをクリア（Ctrl+Shift+Delete）してから再試行してください。

### Q. Markdown プレビューが表示されない
**A.** ファイルが 10MB 以上ではないか確認してください。サイズチェック後にプレビュー生成されます。

### Q. PDF ファイルのテキスト抽出ができない
**A.** 意図的な制限です。ブラウザでの PDF テキスト抽出は複雑なため、PDF は metadata のみを保存します。テキスト抽出が必要な場合はバックエンド処理を追加してください。

---

## 📝 今後の予定

1. **テンプレートダウンロード UI**: アップロードページに「テンプレートをダウンロード」ボタンを追加
2. **バルク登録**: 複数ファイルを一度にアップロードする機能
3. **CSV インポート**: CSV ファイルから一括登録機能
4. **プレビュー改善**: PDF テキスト抽出（`pdf.js` 導入検討）

---

## 参考リンク

- ブランチ: `feat/new-knowledge-ui`
- テンプレート: `public/templates/knowledge-template.md`
- 検証スキーマ: `frontend/src/app/(admin)/admin/knowledge/utils/validation.ts`
- 開発ガイド: `docs/development/DEVELOPER-GUIDE.md`
