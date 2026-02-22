# 音声認識語彙管理ページ 実装計画書

**作成日**: 2026-02-22
**更新日**: 2026-02-23（ユーザー確定：全処理サーバーサイド）
**対象ブランチ**: feat/vosk-settign-list-page
**ステータス**: 確定

---

## 1. 実装概要

### 1.1 実装スコープ

`/admin/vosk-settings` の語彙管理リストページを実装する。

- フロントエンド: Next.js App Router ページ + コンポーネント群
- バックエンド: VocabularyCategory 型の拡張（3カテゴリ追加）+ search/page/limit パラメータ追加 + stats レスポンス追加
- **Next.js API Route は作成しない。フロントエンドから FastAPI を直接呼び出す。**
- **すべてのフィルタリング・ページネーション・統計はサーバーサイドで処理する。**

### 1.2 参照した既存コード

| ファイル | 用途 |
|---------|------|
| frontend/src/app/(admin)/admin/knowledge/page.tsx | ページ構成パターン（useSWR, Toaster, フィルター） |
| frontend/src/app/(admin)/admin/knowledge/components/KnowledgeTable.tsx | テーブル・ページネーションパターン |
| frontend/src/app/api/voice/route.ts | BACKEND_API_URL 環境変数の参照パターン |
| backend/api/stt_vocabulary.py | バックエンド API 仕様・型定義 |

---

## 2. タスク分解（WBS）

### Phase 1: バックエンド拡張（最初に実施）

#### Task 1-1: VocabularyCategory 型拡張【ブロッカー: フロントエンド実装前に必須】

**ファイル**: `backend/api/stt_vocabulary.py`
**難易度**: Low
**工数**: 15分
**依存タスク**: なし

変更内容（L33）:
```python
# 変更前
VocabularyCategory = Literal["facility", "location", "service", "event"]

# 変更後
VocabularyCategory = Literal[
    "facility",
    "location",
    "service",
    "event",
    "person",
    "tech",
    "organization",
]
```

注意点:
- VocabularyCreateRequest, VocabularyUpdateRequest, VocabularyTestRequest の category フィールドも自動更新
- 既存の JSON データに影響なし

#### Task 1-2: search・page・limit パラメータ追加 + stats レスポンス追加【ブロッカー】

**ファイル**: `backend/api/stt_vocabulary.py`
**難易度**: Medium
**工数**: 30分
**依存タスク**: Task 1-1

変更内容: `GET /stt/vocabulary` エンドポイントを拡張

```python
@router.get("/vocabulary")
async def list_vocabulary(
    category: Optional[VocabularyCategory] = None,
    search: Optional[str] = None,      # 新規: word・reading の部分一致検索
    page: int = 1,                      # 新規: ページ番号（1始まり）
    limit: int = 20,                    # 新規: 1ページあたりの件数
):
    all_items = load_all_vocabulary()

    # 統計情報（常に全件ベース、フィルタ前に算出）
    stats = {
        "total": len(all_items),
        "byCategory": {}
    }
    for cat in ["facility", "location", "service", "event", "person", "tech", "organization"]:
        stats["byCategory"][cat] = sum(1 for v in all_items if v.get("category") == cat)

    # フィルタリング
    items = all_items
    if category:
        items = [v for v in items if v["category"] == category]
    if search:
        lower_search = search.lower()
        items = [v for v in items if lower_search in v.get("word", "").lower() or lower_search in v.get("reading", "").lower()]

    total = len(items)

    # ページネーション
    start = (page - 1) * limit
    end = start + limit
    paginated = items[start:end]

    return {
        "success": True,
        "data": paginated,
        "total": total,
        "page": page,
        "limit": limit,
        "stats": stats,
    }
```

> **[Reviewer 指摘対応]** Task 1-1, 1-2 はすべての Phase 2-3 フロントエンド実装のブロッカーです。
> バックエンドが完成していないと、フロントエンドのデータ取得が正しく動作しません。

---

### Phase 2: フロントエンドコンポーネント実装

#### Task 2-0: API クライアント関数実装

**ファイル**: `frontend/src/lib/api/stt-vocabulary.ts`（新規作成）
**難易度**: Low
**工数**: 20分
**依存タスク**: Task 1-2（バックエンド拡張完了後）

実装内容:
- 型定義: `VocabularyCategory`, `VocabularyItem`, `VocabularyStats`, `VocabularyListResponse`
- `vocabularyFetcher(url)`: SWR 用 fetcher
- `deleteVocabulary(id)`: `DELETE {NEXT_PUBLIC_BACKEND_API_URL}/stt/vocabulary/{id}` を呼び出す
- `buildVocabularyListKey(params)`: SWR キー生成ヘルパー（category, search, page, limit を URL に組み込む）
- `CATEGORY_METADATA`: カテゴリ表示名とバッジクラスのマッピング
- `CATEGORY_ORDER`: カテゴリ表示順序
- `NEXT_PUBLIC_BACKEND_API_URL` が未設定の場合は `http://localhost:8000` にフォールバック

型定義:
```typescript
export interface VocabularyStats {
  total: number;
  byCategory: Record<VocabularyCategory, number>;
}

export interface VocabularyListResponse {
  success: boolean;
  data: VocabularyItem[];
  total: number;
  page: number;
  limit: number;
  stats: VocabularyStats;
}
```

---

#### Task 2-1: DeleteConfirmModal コンポーネント

**ファイル**: `frontend/src/app/(admin)/admin/vosk-settings/components/DeleteConfirmModal.tsx`（新規作成）
**難易度**: Low
**工数**: 30分
**依存タスク**: なし（独立）

Props:
```typescript
interface DeleteConfirmModalProps {
  item: VocabularyItem;
  isDeleting: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}
```

実装内容:
- オーバーレイ背景（`fixed inset-0 bg-black bg-opacity-50 z-50`）
- タイトル: 「語彙を削除しますか？」
- メッセージ: 「{item.word}を削除します。この操作は元に戻せません。」
- キャンセルボタン（bg-gray-200）、削除するボタン（bg-red-600）
- 削除中はボタンを disabled

#### Task 2-2: VoskVocabularyFilter コンポーネント

**ファイル**: `frontend/src/app/(admin)/admin/vosk-settings/components/VoskVocabularyFilter.tsx`（新規作成）
**難易度**: Low
**工数**: 30分
**依存タスク**: なし（独立）

Props:
```typescript
interface VoskVocabularyFilterProps {
  searchInput: string;
  categoryFilter: VocabularyCategory | "";
  onSearchInputChange: (value: string) => void;
  onCategoryChange: (value: VocabularyCategory | "") => void;
  onSearch: (e: React.FormEvent) => void;
}
```

カテゴリ選択肢（全8件）:
- `""` : すべて
- `"facility"` : 施設
- `"location"` : 場所
- `"service"` : サービス
- `"event"` : イベント
- `"person"` : 人名
- `"tech"` : 技術用語
- `"organization"` : 組織・団体

検索ボタン: `bg-purple-600 hover:bg-purple-700`

#### Task 2-3: VoskVocabularyStats コンポーネント

**ファイル**: `frontend/src/app/(admin)/admin/vosk-settings/components/VoskVocabularyStats.tsx`（新規作成）
**難易度**: Low
**工数**: 25分
**依存タスク**: なし（独立）

Props:
```typescript
interface VoskVocabularyStatsProps {
  stats: VocabularyStats | null;  // API レスポンスの stats プロパティ
}
```

実装内容:
- クイックアクション: 認識テストボタン（`bg-green-300 cursor-not-allowed opacity-60`）→ `disabled` スタイル + 「準備中」ツールチップ
- 統計情報: 総登録数（`stats.total`）、カテゴリ別件数（`stats.byCategory`）
- 統計は API レスポンスから直接取得（クライアントサイドでの算出不要）

#### Task 2-4: VoskVocabularyTable コンポーネント

**ファイル**: `frontend/src/app/(admin)/admin/vosk-settings/components/VoskVocabularyTable.tsx`（新規作成）
**難易度**: Medium
**工数**: 60分
**依存タスク**: なし（独立）

Props:
```typescript
interface VoskVocabularyTableProps {
  items: VocabularyItem[];     // サーバーサイドでページング済みデータ
  totalItems: number;          // フィルタ後の総件数（data.total）
  page: number;
  itemsPerPage: number;
  onPageChange: (page: number) => void;
  onDeleteClick: (item: VocabularyItem) => void;
}
```

テーブル列: 単語 / 読み仮名 / カテゴリ（バッジ） / 更新日時 / 操作

カテゴリバッジ色（CATEGORY_METADATA 定数で定義、フルクラス名必須）:
- facility: `bg-blue-100 text-blue-800`
- location: `bg-green-100 text-green-800`
- service: `bg-purple-100 text-purple-800`
- event: `bg-orange-100 text-orange-800`
- person: `bg-pink-100 text-pink-800`
- tech: `bg-cyan-100 text-cyan-800`
- organization: `bg-yellow-100 text-yellow-800`

操作ボタン:
- 編集: `disabled` スタイル（`text-gray-400 cursor-not-allowed`）。遷移先未実装のためクリック不可
- 削除（`text-red-600 hover:text-red-900`）→ `onDeleteClick` コールバック

空状態の表示:
- `items.length === 0` かつフィルターなし: 「登録されている語彙がありません」を中央表示
- `items.length === 0` かつフィルターあり: 「条件に一致する語彙が見つかりませんでした」を中央表示

ページネーション: 「全N件中 X-Y件を表示」+ 前/番号/次ボタン

---

### Phase 3: メインページ実装

#### Task 3-1: page.tsx（リストページ本体）

**ファイル**: `frontend/src/app/(admin)/admin/vosk-settings/page.tsx`（新規作成）
**難易度**: Medium
**工数**: 60分
**依存タスク**: Task 2-0, 2-1, 2-2, 2-3, 2-4

状態管理:
| 状態 | 型 | 初期値 | 用途 |
|------|----|---------|------|
| page | number | 1 | 現在ページ |
| searchInput | string | "" | 検索入力値（入力中） |
| appliedSearch | string | "" | 確定した検索値（SWR キーに使用） |
| categoryFilter | VocabularyCategory or "" | "" | カテゴリフィルター（SWR キーに使用） |
| deletingItem | VocabularyItem or null | null | 削除対象アイテム |
| isDeleting | boolean | false | 削除中フラグ |

SWR フック（FastAPI 直接・サーバーサイド処理）:
```typescript
const ITEMS_PER_PAGE = 20;

const swrKey = useMemo(
  () => buildVocabularyListKey({
    category: categoryFilter || undefined,
    search: appliedSearch || undefined,
    page,
    limit: ITEMS_PER_PAGE,
  }),
  [categoryFilter, appliedSearch, page]
);

const { data, error, isLoading, mutate } = useSWR<VocabularyListResponse>(
  swrKey,
  vocabularyFetcher
);

const vocabularyData = data?.data ?? [];
const stats = data?.stats ?? null;
const totalFiltered = data?.total ?? 0;
```

レイアウト:
- ヘッダー: 「音声認識語彙管理」 + [+新規追加]（disabled）+ [インポート]（disabled）
- フィルターバー: VoskVocabularyFilter
- メインエリア: flex gap-6
  - 左 flex-1: VoskVocabularyTable
  - 右 w-64: VoskVocabularyStats
- DeleteConfirmModal（deletingItem 非 null 時のみ）
- Toaster（top-right）

---

## 3. 実装順序と依存関係

> **[Reviewer 指摘対応]** Task 1-1, 1-2 はすべてのフロントエンドタスクのブロッカーです。

実装順序:

```
[Step 1 - 必須・先行実施]
Task 1-1: backend VocabularyCategory 拡張
Task 1-2: backend search/page/limit パラメータ + stats レスポンス追加
    |
    | ruff check / black --check でバックエンドの lint を確認後、以下を開始
    |
[Step 2 - 並行実施可能（Phase 1 完了後）]
Task 2-0: src/lib/api/stt-vocabulary.ts（API クライアント関数）
Task 2-1: DeleteConfirmModal
Task 2-2: VoskVocabularyFilter
Task 2-3: VoskVocabularyStats
Task 2-4: VoskVocabularyTable
    |
    | 全 Phase 2 完了後
    |
[Step 3]
Task 3-1: page.tsx
    |
[Step 4]
CI/CD チェック: pnpm lint / typecheck / build
```

並行実装可能なグループ: Task 2-1, 2-2, 2-3, 2-4（Phase 1 完了が前提）

---

## 4. 各タスクの難易度と工数

| タスクID | ファイル | 難易度 | 工数 |
|---------|---------|--------|------|
| 1-1 | backend/api/stt_vocabulary.py | Low | 15分 |
| 1-2 | backend/api/stt_vocabulary.py | Medium | 30分 |
| 2-0 | src/lib/api/stt-vocabulary.ts | Low | 20分 |
| 2-1 | DeleteConfirmModal.tsx | Low | 30分 |
| 2-2 | VoskVocabularyFilter.tsx | Low | 30分 |
| 2-3 | VoskVocabularyStats.tsx | Low | 25分 |
| 2-4 | VoskVocabularyTable.tsx | Medium | 60分 |
| 3-1 | page.tsx | Medium | 60分 |
| - | CI/CD チェック | Low | 15分 |
| **合計** | | | **285分（約4.75時間）** |

---

## 5. ファイル構成（作成・変更対象）

変更ファイル:
- `backend/api/stt_vocabulary.py` [MODIFY] VocabularyCategory 拡張 + search/page/limit + stats

新規作成ファイル:
- `frontend/src/lib/api/stt-vocabulary.ts` [CREATE] FastAPI 直接呼び出し API クライアント関数
- `frontend/src/app/(admin)/admin/vosk-settings/page.tsx` [CREATE] メインページ
- `frontend/src/app/(admin)/admin/vosk-settings/components/DeleteConfirmModal.tsx` [CREATE]
- `frontend/src/app/(admin)/admin/vosk-settings/components/VoskVocabularyFilter.tsx` [CREATE]
- `frontend/src/app/(admin)/admin/vosk-settings/components/VoskVocabularyStats.tsx` [CREATE]
- `frontend/src/app/(admin)/admin/vosk-settings/components/VoskVocabularyTable.tsx` [CREATE]

合計: 1ファイル変更 + 6ファイル新規作成（API Route なし）

---

## 6. 技術的注意点

### 6.1 FastAPI への直接アクセス

**Next.js API Route を経由しない**。フロントエンドから直接 FastAPI バックエンドを呼び出す。

```typescript
// NEXT_PUBLIC_ プレフィックスが必要（クライアントサイドで参照するため）
const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_API_URL ?? "http://localhost:8000";
```

### 6.2 CORS 設定の確認

ブラウザから直接 FastAPI を呼び出すため、CORS 許可設定が必要。

- **開発環境**: `backend/main.py` で CORS は既に設定済みのため追加対応不要
- **本番環境**: `ALLOWED_ORIGINS` に本番ドメインを追加する必要あり

### 6.3 検索のフィルタリング戦略

**方針**: サーバーサイドフィルタリング

- `GET /stt/vocabulary?search=xxx` でサーバー側で word・reading の部分一致検索を実行
- SWR キーに search パラメータを含めることで、検索実行時に自動再フェッチ

### 6.4 ページネーション実装

**方針**: サーバーサイドページネーション

- `GET /stt/vocabulary?page=1&limit=20` でサーバー側でページング
- SWR キーに page・limit パラメータを含めることで、ページ変更時に自動再フェッチ
- レスポンスの `total` フィールドを使ってページネーション UI を制御

### 6.5 統計情報の取得

API レスポンスの `stats` プロパティから直接取得。クライアントサイドでの算出は不要。
`stats` は常に全件ベース（フィルタ条件に関わらず）で算出される。

### 6.6 react-hot-toast の使用

既存の `knowledge/page.tsx` で使用済み（追加インストール不要）。

### 6.7 TypeScript 型定義

`src/lib/api/stt-vocabulary.ts` で型定義し、各コンポーネントから import。

---

## 7. リスク管理計画

| リスク | 確率 | 影響 | 対策 |
|--------|------|------|------|
| CORS エラー | Medium | High | FastAPI の CORS 設定を事前確認。既存設定で許可済みなら問題なし |
| NEXT_PUBLIC_BACKEND_API_URL 未設定 | Medium | Medium | .env.local に追加。未設定時は localhost:8000 のデフォルト値で動作 |
| バックエンド起動要否 | Medium | High | 開発時はバックエンドを起動する必要あり。pnpm build はバックエンド不要 |
| pnpm build 失敗 | Low | High | typecheck, lint を先に実行して型エラーを早期発見 |
| orange カラーの Tailwind v3 互換性 | Very Low | Low | v3 では orange 利用可能 |

---

## 8. 受け入れ条件チェックリスト

| # | 条件 | 確認方法 |
|---|------|----------|
| 1 | /admin/vosk-settings にアクセスすると語彙一覧が表示される | ブラウザで確認 |
| 2 | 単語または読み仮名で部分一致検索できる（サーバーサイド） | 検索フィールドで確認 |
| 3 | カテゴリドロップダウンで絞り込みできる（サーバーサイド） | ドロップダウンで確認 |
| 4 | 検索とカテゴリフィルターを組み合わせられる | 両方設定して検索 |
| 5 | サイドパネルの統計情報はフィルター非依存で全件ベース表示（APIレスポンス） | フィルター中に確認 |
| 6 | 削除フロー完全動作（モーダル→FastAPI→リスト更新） | 削除ボタンクリック |
| 7 | 削除成功・失敗時にトースト通知が表示される | 削除後確認 |
| 8 | 語彙 0 件時に空状態メッセージが表示される（フィルターあり/なしで文言が異なる） | 0件状態で確認 |
| 9 | 「+新規追加」「インポート」「認識テスト」「編集」が disabled スタイルで表示される | 各ボタンを確認 |
| 10 | ページネーションが正しく動作する（サーバーサイド） | 20件以上のデータで確認 |
| 11 | TypeScript 型エラーなし | pnpm typecheck |
| 12 | ESLint エラーなし | pnpm lint |
| 13 | pnpm build が成功する | ビルド実行 |

---

## 9. CI/CD チェック手順

```bash
# フロントエンド
cd frontend
pnpm lint
pnpm typecheck
pnpm build

# バックエンド
cd backend
ruff check .
black --check .
```

---

## 10. コミット計画

```
コミット1: feat(backend): extend VocabularyCategory and add search/page/limit/stats to vocabulary API
コミット2: feat(frontend): add STT vocabulary admin list page
```
