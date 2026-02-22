# 音声認識語彙管理ページ アーキテクチャドキュメント

**作成日**: 2026-02-22
**更新日**: 2026-02-23（ユーザー確定：全処理サーバーサイド）
**対象ブランチ**: feat/vosk-settign-list-page
**ステータス**: 確定

---

## 1. 概要

### 1.1 設計方針

既存の知識ベース管理画面（`frontend/src/app/(admin)/admin/knowledge/`）のパターンを踏襲しつつ、Vosk語彙管理の要件に合わせた設計を行う。

**重要な方針**:
- Next.js API Route は作成しない
- Server Actions も使用しない
- `'use client'` コンポーネントから FastAPI を直接 fetch する
- 専用の API クライアント関数を `src/lib/api/stt-vocabulary.ts` に集約する

### 1.2 技術スタック

- フレームワーク: Next.js 15.3.2 (App Router)
- UI: React 19 + TypeScript 5
- スタイリング: Tailwind CSS v3.4.17（v4不可）
- データフェッチ: SWR（既存パターンに合わせる）
- トースト通知: react-hot-toast（既存依存済み）
- バックエンドアクセス: 直接 fetch（`NEXT_PUBLIC_BACKEND_API_URL` 環境変数）

---

## 2. 設計判断

### 2.1 【判断1】全処理サーバーサイド（ユーザー確定）

| 処理 | 実行場所 | 方法 |
|------|---------|------|
| カテゴリフィルタ | **サーバーサイド** | FastAPI `?category=` パラメータ（既存） |
| テキスト検索 | **サーバーサイド** | FastAPI `?search=` パラメータ（**新規追加**） |
| ページネーション | **サーバーサイド** | FastAPI `?page=&limit=` パラメータ（**新規追加**） |
| 統計情報 | **サーバーサイド** | API レスポンスの `stats` プロパティ（**新規追加**） |

**理由**:
- すべてのフィルタリング・ページング・統計をサーバーサイドで処理し、返却データ量を最小化
- SWR キーに `category`・`search`・`page`・`limit` を含めることで変更時に自動再フェッチ
- 統計情報はフィルタ条件に関わらず常に全件ベースの統計を返す（API レスポンスに含める）

**バックエンドAPIの拡張（必須）**:
- `search` クエリパラメータ追加（`word`・`reading` の部分一致をサーバー側で処理）
- `page` クエリパラメータ追加（ページ番号、デフォルト 1）
- `limit` クエリパラメータ追加（1ページあたりの件数、デフォルト 20）
- レスポンスに `stats` プロパティ追加（総件数・カテゴリ別件数、常に全件ベース）

**実装**:
```typescript
const ITEMS_PER_PAGE = 20;

// SWR キー: category + search + page + limit 変更時に自動再フェッチ
const swrKey = useMemo(() => buildVocabularyListKey({
  category: categoryFilter || undefined,
  search: appliedSearch || undefined,
  page,
  limit: ITEMS_PER_PAGE,
}), [categoryFilter, appliedSearch, page]);

const { data, error, isLoading, mutate } = useSWR<VocabularyListResponse>(
  swrKey,
  vocabularyFetcher
);

// API が返したページ分のデータ（サーバーサイドでフィルタ・ページング済み）
const vocabularyData = data?.data ?? [];
// API が返した統計情報（常に全件ベース）
const stats = data?.stats ?? null;
```

---

### 2.2 【判断2】バックエンドの VocabularyCategory 型拡張（必須・ブロッカー）

**背景**: 現在の FastAPI 実装（L33）では4カテゴリのみ定義。フロントエンド実装の前提条件。

`backend/api/stt_vocabulary.py` L33:
```python
# 変更前
VocabularyCategory = Literal["facility", "location", "service", "event"]

# 変更後
VocabularyCategory = Literal[
    "facility",      # 施設（既存）
    "location",      # 場所（既存）
    "service",       # サービス（既存）
    "event",         # イベント（既存）
    "person",        # 人名（新規追加）
    "tech",          # 技術用語（新規追加）
    "organization",  # 組織・団体（新規追加）
]
```

変更は L33 の1箇所のみ。Python の型エイリアスのため、同ファイル内の全参照箇所（L45/L53/L60/L80/L160）に自動反映される。

---

### 2.3 【判断3】未実装機能は disabled スタイル + ツールチップ

遷移先未実装のボタン・リンクは `Link` コンポーネントではなく `disabled` 属性付きの `button` として実装する。

**採用理由**: 404 ページへの遷移を防ぎ、「準備中」であることをユーザーに明示する。

**各ボタンのスタイル**:

| ボタン | 配置 | className |
|--------|------|-----------|
| 「+ 新規追加」 | ヘッダー | `bg-blue-300 cursor-not-allowed opacity-60 text-white px-4 py-2 rounded-lg` |
| 「インポート」 | ヘッダー | `bg-green-300 cursor-not-allowed opacity-60 text-white px-4 py-2 rounded-lg` |
| 「認識テスト」 | サイドパネル | `bg-green-300 cursor-not-allowed opacity-60 text-white px-4 py-2 rounded-lg w-full` |
| 「編集」 | テーブル行 | `text-gray-400 cursor-not-allowed text-sm font-medium` |

**実装例**:
```tsx
{/* ヘッダー: 遷移先未実装ボタン */}
<button
  disabled
  title="この機能は準備中です"
  className="bg-blue-300 cursor-not-allowed opacity-60 text-white px-4 py-2 rounded-lg"
>
  + 新規追加
</button>

<button
  disabled
  title="この機能は準備中です"
  className="bg-green-300 cursor-not-allowed opacity-60 text-white px-4 py-2 rounded-lg"
>
  インポート
</button>

{/* テーブル行: 編集ボタン */}
<button
  disabled
  title="この機能は準備中です"
  className="text-gray-400 cursor-not-allowed text-sm font-medium"
>
  編集
</button>
```

---

### 2.4 【判断4】APIクライアント関数を src/lib/api/stt-vocabulary.ts に集約

**採用理由**: API 呼び出しロジックをページコンポーネントに直書きせず、専用モジュールに集約することで再利用性とテスタビリティを高める。

SWR fetcher は URL 文字列を引数に取る形式で実装し、SWR のキャッシュキー（URL）と fetcher を一致させる。

```typescript
// frontend/src/lib/api/stt-vocabulary.ts

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_API_URL ?? "http://localhost:8000";

/** SWR 用 fetcher（URL を引数に取る） */
export const vocabularyFetcher = (url: string): Promise<VocabularyListResponse> =>
  fetch(url).then((res) => {
    if (!res.ok) throw new Error(`Failed to fetch vocabulary: ${res.status}`);
    return res.json();
  });

export async function deleteVocabulary(id: string): Promise<void> {
  const res = await fetch(`${BACKEND_URL}/stt/vocabulary/${id}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`Failed to delete vocabulary: ${res.status}`);
}
```

page.tsx では SWR の fetcher として `vocabularyFetcher` を使用し、削除処理では `deleteVocabulary` を直接呼び出す。

---

### 2.5 【判断5】直接 FastAPI アクセスと環境変数

**確認済みの CORS 設定**: `backend/main.py` で `localhost:3000` を許可済み。開発環境での直接アクセスに問題なし。

**環境変数**:
```
# frontend/.env.local に追加（現在未設定）
NEXT_PUBLIC_BACKEND_API_URL=http://localhost:8000
```

既存の `BACKEND_API_URL`（プレフィックスなし）はサーバーサイド専用（`/api/voice` 等）。クライアントサイドから参照するには `NEXT_PUBLIC_` プレフィックスが必須。

---

## 3. ファイル構成

```
frontend/src/
├── lib/
│   └── api/
│       └── stt-vocabulary.ts             # FastAPI 直接呼び出しの API クライアント関数（新規）
└── app/
    └── (admin)/admin/vosk-settings/
        ├── page.tsx                       # リストページ（'use client'、メインオーケストレーター）
        └── components/
            ├── VoskVocabularyTable.tsx    # テーブルコンポーネント（'use client'）
            ├── VoskVocabularyFilter.tsx   # 検索・フィルターバー（'use client'）
            ├── VoskVocabularyStats.tsx    # サイドパネル統計情報
            └── DeleteConfirmModal.tsx     # 削除確認モーダル（'use client'）
```

**作成しないもの**:
- `frontend/src/app/api/` 配下のいかなる API Route も不要

バックエンド変更:
```
backend/
└── api/stt_vocabulary.py  [MODIFY] VocabularyCategory 型拡張（L33）＋ search/page/limit パラメータ追加 ＋ stats レスポンス追加
```

---

## 4. 型定義（TypeScript Interfaces）

`src/lib/api/stt-vocabulary.ts` で型定義し、各コンポーネントから import する。

```typescript
// frontend/src/lib/api/stt-vocabulary.ts

export type VocabularyCategory =
  | "facility"      // 施設
  | "location"      // 場所
  | "service"       // サービス
  | "event"         // イベント
  | "person"        // 人名
  | "tech"          // 技術用語
  | "organization"; // 組織・団体

export interface VocabularyItem {
  id: string;
  word: string;
  reading: string;
  category: VocabularyCategory;
  priority: number;        // 1-10（UIには表示しない）
  created_at: string;      // ISO 8601
  updated_at: string;      // ISO 8601
}

export interface VocabularyStats {
  total: number;                                    // 全件数（フィルタ無関係）
  byCategory: Record<VocabularyCategory, number>;   // カテゴリ別件数（フィルタ無関係）
}

export interface VocabularyListResponse {
  success: boolean;
  data: VocabularyItem[];       // 現在ページのデータ（サーバーサイドでフィルタ・ページング済み）
  total: number;                // フィルタ後の総件数（ページネーション計算用）
  page: number;                 // 現在のページ番号
  limit: number;                // 1ページあたりの件数
  stats: VocabularyStats;       // 統計情報（常に全件ベース）
}

export const CATEGORY_METADATA: Record<VocabularyCategory, { label: string; badgeClass: string }> = {
  facility:     { label: "施設",       badgeClass: "bg-blue-100 text-blue-800" },
  location:     { label: "場所",       badgeClass: "bg-green-100 text-green-800" },
  service:      { label: "サービス",   badgeClass: "bg-purple-100 text-purple-800" },
  event:        { label: "イベント",   badgeClass: "bg-orange-100 text-orange-800" },
  person:       { label: "人名",       badgeClass: "bg-pink-100 text-pink-800" },
  tech:         { label: "技術用語",   badgeClass: "bg-cyan-100 text-cyan-800" },
  organization: { label: "組織・団体", badgeClass: "bg-yellow-100 text-yellow-800" },
};

export const CATEGORY_ORDER: VocabularyCategory[] = [
  "facility", "location", "service", "event", "person", "tech", "organization",
];
```

**重要**: `badgeClass` は必ずフルクラス名で定義する（Tailwind CSS v3 のパージ対策）。

---

## 5. APIクライアント設計（src/lib/api/stt-vocabulary.ts）

```typescript
const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_API_URL ?? "http://localhost:8000";

// 開発環境で未設定の場合に警告
if (process.env.NODE_ENV === "development" && !process.env.NEXT_PUBLIC_BACKEND_API_URL) {
  console.warn(
    "[stt-vocabulary] NEXT_PUBLIC_BACKEND_API_URL is not set. " +
    "Falling back to http://localhost:8000. " +
    "Add it to frontend/.env.local to suppress this warning."
  );
}

/** SWR 用 fetcher（URL 文字列を引数に取る） */
export const vocabularyFetcher = (url: string): Promise<VocabularyListResponse> =>
  fetch(url).then((res) => {
    if (!res.ok) throw new Error(`Failed to fetch vocabulary: ${res.status}`);
    return res.json();
  });

/** 語彙削除 */
export async function deleteVocabulary(id: string): Promise<void> {
  const res = await fetch(`${BACKEND_URL}/stt/vocabulary/${id}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`Failed to delete vocabulary: ${res.status}`);
}

/** SWR キー生成ヘルパー（category・search・page・limit パラメータを URL に組み込む） */
export function buildVocabularyListKey(params: {
  category?: string;
  search?: string;
  page?: number;
  limit?: number;
}): string {
  const query = new URLSearchParams();
  if (params.category) query.set("category", params.category);
  if (params.search) query.set("search", params.search);
  query.set("page", String(params.page ?? 1));
  query.set("limit", String(params.limit ?? 20));
  return `${BACKEND_URL}/stt/vocabulary?${query.toString()}`;
}
```

SWR での使用方法:
```typescript
// page.tsx
import { vocabularyFetcher, buildVocabularyListKey } from "@/lib/api/stt-vocabulary";

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

// API が返したページ分のデータ
const vocabularyData = data?.data ?? [];
// API が返した統計情報（常に全件ベース）
const stats = data?.stats ?? null;
```

---

## 6. コンポーネント設計

### 6.1 page.tsx（メインオーケストレーター）

**ディレクティブ**: `'use client'`

**責任**:
- 状態管理（検索・フィルター・ページ・削除対象）
- SWR によるサーバーサイドフィルタ済みデータ取得と再取得
- 削除処理（deleteVocabulary 関数呼び出し）
- トースト通知

**状態**:
```typescript
const [page, setPage] = useState(1);
const [searchInput, setSearchInput] = useState("");      // 入力中（未確定）
const [appliedSearch, setAppliedSearch] = useState("");  // 確定済み（SWR キーに使用）
const [categoryFilter, setCategoryFilter] = useState<VocabularyCategory | "">("");
const [deletingItem, setDeletingItem] = useState<VocabularyItem | null>(null);
const [isDeleting, setIsDeleting] = useState(false);
```

**SWR + サーバーサイド処理**（設計判断 2.1 参照）:
```typescript
const ITEMS_PER_PAGE = 20;

// SWR キーにフィルタ・ページパラメータを含める → 変更時に自動再フェッチ
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

// API が返したページ分のデータ（サーバーサイドでフィルタ・ページング済み）
const vocabularyData = data?.data ?? [];
// API が返した統計情報（常に全件ベース）
const stats = data?.stats ?? null;
// フィルタ後の総件数（ページネーション計算用）
const totalFiltered = data?.total ?? 0;
```

**ハンドラ**:
```typescript
const handleSearch = (e: React.FormEvent) => {
  e.preventDefault();
  setAppliedSearch(searchInput);
  setPage(1);
};

const handleCategoryChange = (cat: VocabularyCategory | "") => {
  setCategoryFilter(cat);
  setPage(1);
};

const handleDeleteConfirm = async () => {
  if (!deletingItem) return;
  setIsDeleting(true);
  try {
    await deleteVocabulary(deletingItem.id);
    toast.success("削除しました");
    setDeletingItem(null);
    mutate();
  } catch {
    toast.error("削除に失敗しました");
  } finally {
    setIsDeleting(false);
  }
};
```

**レイアウト構造**:
```
div.min-h-screen.bg-gray-50.p-8
  Toaster position="top-right"
  div.max-w-7xl.mx-auto
    div.bg-white.rounded-lg.shadow-sm.border
      ヘッダー
        h1: 音声認識語彙管理
        button[disabled] bg-blue-300 cursor-not-allowed opacity-60: + 新規追加（準備中）
        button[disabled] bg-green-300 cursor-not-allowed opacity-60: インポート（準備中）
      div.p-6
        エラー表示（bg-red-50、error が真の場合のみ）
        VoskVocabularyFilter
        div.flex.gap-6
          div.flex-1.min-w-0
            isLoading → スピナー
            vocabularyData.length === 0 → 空状態メッセージ
            それ以外 → VoskVocabularyTable
          div.w-64.flex-shrink-0
            VoskVocabularyStats
    DeleteConfirmModal（deletingItem 非 null 時のみ）
```

**空状態の表示ロジック**:
```tsx
{isLoading ? (
  <Spinner />
) : vocabularyData.length === 0 ? (
  <EmptyState hasFilter={!!(categoryFilter || appliedSearch)} />
) : (
  <VoskVocabularyTable ... />
)}
```

空状態メッセージ:
- フィルタなし（初期状態）: 「登録されている語彙がありません」
- フィルタあり: 「条件に一致する語彙が見つかりませんでした」

---

### 6.2 VoskVocabularyFilter.tsx

**Props**:
```typescript
interface VoskVocabularyFilterProps {
  searchInput: string;
  categoryFilter: VocabularyCategory | "";
  onSearchInputChange: (value: string) => void;
  onCategoryChange: (value: VocabularyCategory | "") => void;
  onSearch: (e: React.FormEvent) => void;
}
```

**実装のポイント**:
- `<form onSubmit={onSearch}>` で Enter キーも対応
- カテゴリは select 要素で全7カテゴリ（CATEGORY_ORDER）+ 「すべて」
- 検索ボタンは `bg-purple-600 hover:bg-purple-700`
- カテゴリ変更は即時適用（`onCategoryChange` 呼び出し）

---

### 6.3 VoskVocabularyTable.tsx

**Props**:
```typescript
interface VoskVocabularyTableProps {
  items: VocabularyItem[];     // vocabularyData（サーバーサイドでページング済み）
  totalItems: number;          // totalFiltered（フィルタ後の総件数）
  page: number;
  itemsPerPage: number;        // ITEMS_PER_PAGE = 20
  onPageChange: (page: number) => void;
  onDeleteClick: (item: VocabularyItem) => void;
}
```

**テーブル列**:
| 列名 | データ | スタイル |
|------|-------|---------|
| 単語 | item.word | テキスト |
| 読み仮名 | item.reading | テキスト |
| カテゴリ | item.category | バッジ（CATEGORY_METADATA から色取得） |
| 更新日時 | item.updated_at | YYYY/MM/DD HH:mm 形式 |
| 操作 | - | 編集ボタン（disabled）+ 削除ボタン |

**操作列**:
```tsx
{/* 編集: 遷移先未実装のため disabled */}
<button
  disabled
  title="この機能は準備中です"
  className="text-gray-400 cursor-not-allowed text-sm font-medium"
>
  編集
</button>
{/* 削除: 機能実装済み */}
<button
  onClick={() => onDeleteClick(item)}
  className="text-red-600 hover:text-red-900 text-sm font-medium"
>
  削除
</button>
```

**ページ情報テキスト**:
```
全{totalItems}件中 {(page - 1) * itemsPerPage + 1}-{Math.min(page * itemsPerPage, totalItems)}件を表示
```

**ページネーション**: 既存 KnowledgeTable と同一パターン（前/ページ番号/次ボタン）

---

### 6.4 VoskVocabularyStats.tsx

**Props**:
```typescript
interface VoskVocabularyStatsProps {
  stats: VocabularyStats | null;  // data.stats（API レスポンスから取得）
}
```

**表示**:
- クイックアクション: 「認識テスト」ボタン（`bg-green-300 cursor-not-allowed opacity-60 w-full disabled`）
- 統計情報: 総登録数（`stats.total`）+ カテゴリ別件数（`stats.byCategory`、0件のカテゴリは表示しない）

統計は API レスポンスの `stats` プロパティから取得。常に全件ベースの統計であり、フィルタ変更の影響を受けない。

---

### 6.5 DeleteConfirmModal.tsx

**Props**:
```typescript
interface DeleteConfirmModalProps {
  item: VocabularyItem;
  isDeleting: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}
```

**実装要点**:
- `fixed inset-0 z-50` でフルスクリーンオーバーレイ
- オーバーレイクリックで `onCancel` 呼び出し
- モーダル内クリックは `e.stopPropagation()` で伝播防止
- `isDeleting` 中はボタン `disabled`

**表示テキスト**:
- タイトル: 「語彙を削除しますか？」
- メッセージ: 「{item.word}を削除します。この操作は元に戻せません。」

---

## 7. データフロー

```
ユーザー操作
    |
    v
page.tsx（状態管理）
    |
    |-- [初回ロード]
    |   SWR key = buildVocabularyListKey({ page: 1, limit: 20 })
    |   vocabularyFetcher(url)
    |       → 直接 FastAPI: GET {BACKEND_URL}/stt/vocabulary?page=1&limit=20
    |           → サーバー側で全件読み込み → ページング → stats 算出
    |           → VocabularyListResponse { success, data[], total, page, limit, stats }
    |
    |-- [カテゴリ変更]
    |   setCategoryFilter + setPage(1)
    |   → swrKey 変更（?category=xxx&page=1&limit=20）
    |   → SWR 自動再フェッチ: GET {BACKEND_URL}/stt/vocabulary?category=xxx&page=1&limit=20
    |
    |-- [検索実行（ボタン or Enter）]
    |   setAppliedSearch + setPage(1)
    |   → swrKey 変更（?search=xxx&page=1&limit=20）
    |   → SWR 自動再フェッチ: GET {BACKEND_URL}/stt/vocabulary?search=xxx&page=1&limit=20
    |
    |-- [ページ変更]
    |   setPage(n)
    |   → swrKey 変更（?page=n&limit=20）
    |   → SWR 自動再フェッチ: GET {BACKEND_URL}/stt/vocabulary?page=n&limit=20
    |
    |-- [削除クリック]
    |   setDeletingItem → DeleteConfirmModal 表示
    |       |
    |       +-- [確認クリック]
    |           deleteVocabulary(id)
    |               → 直接 FastAPI: DELETE {BACKEND_URL}/stt/vocabulary/{id}
    |                   → 成功: toast.success + mutate() + setDeletingItem(null)
    |                   → 失敗: toast.error

データ表示（一方向データフロー）:
    page.tsx → VoskVocabularyFilter（searchInput, categoryFilter）
    page.tsx → VoskVocabularyTable（vocabularyData, totalFiltered, page）
    page.tsx → VoskVocabularyStats（stats ← API レスポンスの stats プロパティ）
    page.tsx → DeleteConfirmModal（deletingItem, isDeleting）
```

---

## 8. バックエンド拡張（必須・フロントエンド実装の前提条件）

### 8.1 VocabularyCategory 型拡張（ブロッカー）

**ファイル**: `backend/api/stt_vocabulary.py`（L33 のみ変更）

```python
# 変更前
VocabularyCategory = Literal["facility", "location", "service", "event"]

# 変更後
VocabularyCategory = Literal[
    "facility",      # 施設（既存）
    "location",      # 場所（既存）
    "service",       # サービス（既存）
    "event",         # イベント（既存）
    "person",        # 人名（新規追加）
    "tech",          # 技術用語（新規追加）
    "organization",  # 組織・団体（新規追加）
]
```

影響箇所（自動反映）: L45, L53, L60, L80, L160

### 8.2 search・page・limit クエリパラメータ追加 + stats レスポンス追加

`GET /stt/vocabulary` を拡張する。

```python
# backend/api/stt_vocabulary.py（拡張後）
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

---

## 9. 既存パターンとの一貫性確認

| 項目 | 知識ベース管理 | Vosk語彙管理（今回） | 判定 |
|------|-------------|--------------|------|
| ページ構造 | use client page.tsx | use client page.tsx | 一致 |
| データフェッチ | SWR + fetcher | SWR + fetcher（FastAPI 直接） | 一致 |
| トースト | react-hot-toast | react-hot-toast | 一致 |
| テーブル | 独立コンポーネント | 独立コンポーネント | 一致 |
| 削除 | confirm() + inline | DeleteConfirmModal（要件拡張） | 拡張 |
| APIアクセス | Supabase 直結（中間層なし） | FastAPI 直接 fetch（中間層なし） | 同方針 |
| APIクライアント | knowledgeBaseUtils | src/lib/api/stt-vocabulary.ts | 同パターン |
| エラー表示 | bg-red-50 div | bg-red-50 div | 一致 |
| ローディング | animate-spin スピナー | animate-spin スピナー | 一致 |
| ページネーション | 前/番号/次ボタン | 前/番号/次ボタン | 一致 |

---

## 10. 状態設計サマリー

```
page.tsx の state:
  searchInput: string          入力中テキスト（未確定）
  appliedSearch: string        確定済み検索テキスト（SWR キーに使用）
  categoryFilter: string       カテゴリフィルタ（SWR キーに使用）
  page: number                 現在ページ番号（初期値 1）
  deletingItem: VocabularyItem | null
  isDeleting: boolean          削除処理中フラグ

SWR（直接 FastAPI）:
  key: buildVocabularyListKey({ category, search, page, limit }) で生成した URL 文字列
  fetcher: vocabularyFetcher(url)
  data: VocabularyListResponse
  error: Error | undefined
  isLoading: boolean
  mutate: () => void（削除後の再フェッチ）

derived state:
  vocabularyData: VocabularyItem[]  data.data（サーバーサイドでフィルタ・ページング済み）
  stats: VocabularyStats | null     data.stats（常に全件ベースの統計情報）
  totalFiltered: number             data.total（フィルタ後の総件数）
```

---

## 11. 受け入れ条件との対応

| # | 受け入れ条件 | 実装箇所 |
|---|------------|---------|
| 1 | /admin/vosk-settings で語彙一覧表示 | page.tsx + SWR |
| 2 | 単語・読み仮名で部分一致検索（サーバーサイド） | swrKey に search 含む → FastAPI `?search=` |
| 3 | カテゴリドロップダウンで絞り込み（サーバーサイド） | swrKey に category 含む → FastAPI `?category=` |
| 4 | 検索とカテゴリフィルターを組み合わせられる | `?category=xxx&search=yyy` で AND 条件 |
| 5 | 語彙 0 件時に適切な空状態メッセージ | page.tsx 条件分岐（vocabularyData.length === 0） |
| 6 | 統計情報はフィルターに関係なく全件ベース | data.stats（API レスポンスプロパティ） |
| 7 | 削除フロー完全動作 | DeleteConfirmModal + deleteVocabulary() |
| 8 | 削除成功・失敗時にトースト通知 | react-hot-toast |
| 9 | 未実装ボタンは disabled スタイル | button[disabled] + title tooltip（§2.3 参照） |
| 10 | ページネーション（サーバーサイド） | swrKey に page/limit 含む → FastAPI `?page=&limit=` |
| 11 | TypeScript 型エラーなし | stt-vocabulary.ts で型を export |
| 12 | pnpm build 成功 | 動的クラス名を避けた実装 |

---

## 12. 実装上の注意事項

### 12.1 環境変数と未定義時のガード処理

```bash
# frontend/.env.local に追加（現在未設定）
NEXT_PUBLIC_BACKEND_API_URL=http://localhost:8000
```

`NEXT_PUBLIC_` なしの `BACKEND_API_URL` はサーバーサイド専用（既存の API Route が使用）。クライアントサイドから参照するには `NEXT_PUBLIC_` プレフィックスが必須。

**未定義時のガード処理**:

`src/lib/api/stt-vocabulary.ts` でモジュール読み込み時に環境変数を検証し、未定義の場合はフォールバック URL を使用しつつ開発環境では警告を出す。

```typescript
// src/lib/api/stt-vocabulary.ts

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_API_URL ?? "http://localhost:8000";

// 開発環境で未設定の場合に警告（本番ビルドでは除去される）
if (process.env.NODE_ENV === "development" && !process.env.NEXT_PUBLIC_BACKEND_API_URL) {
  console.warn(
    "[stt-vocabulary] NEXT_PUBLIC_BACKEND_API_URL is not set. " +
    "Falling back to http://localhost:8000. " +
    "Add it to frontend/.env.local to suppress this warning."
  );
}
```

page.tsx では SWR の `error` を検知してエラーバナーを表示する:

```tsx
{error && (
  <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-4">
    <p className="text-red-700">
      データの取得に失敗しました。バックエンドが起動しているか確認してください。
    </p>
  </div>
)}
```

### 12.2 CORS 設定

**開発環境（確認済み）**: `backend/main.py` で `localhost:3000` をデフォルトで許可済みのため、追加対応不要。

```python
# backend/main.py（現状）
_default_origins = ["http://localhost:3000", "http://localhost:3001"]
_allowed_origins = [
    o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()
] or _default_origins
```

**本番環境（対応必須）**: `NEXT_PUBLIC_BACKEND_API_URL` に本番バックエンドの URL を設定すると同時に、バックエンド側の `ALLOWED_ORIGINS` 環境変数に本番フロントエンドのドメインを追加する必要がある。

### 12.3 Tailwind CSS v3 の動的クラス名問題

`CATEGORY_METADATA` 内の `badgeClass` は必ずフルクラス名で定義する（例: `"bg-blue-100 text-blue-800"`）。
テンプレートリテラルによる動的生成はビルド時にパージされるため使用禁止。

### 12.4 カテゴリフィルタと検索のリセット

カテゴリ変更・検索実行時は必ず `setPage(1)` を呼び出す。SWR キーが変わると自動再フェッチが走るため、ページをリセットしないとページ番号がずれる。

### 12.5 統計情報の取得元

`VoskVocabularyStats` には `data.stats`（API レスポンスの `stats` プロパティ）を渡す。
統計は常に全件ベースでサーバーサイドで算出されるため、フィルタやページ変更の影響を受けない。
