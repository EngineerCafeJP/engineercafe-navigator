# 音声認識語彙管理ページ 要件ドキュメント

**作成日**: 2026-02-22
**最終更新**: 2026-02-23（v6: §2.3・§2.6・§2.7・§3.2・§4.1・§7・§8.1・§9 をサーバーサイドフィルタリングに更新）
**対象ブランチ**: feat/vosk-settign-list-page
**ステータス**: 確定（v6）

---

## 変更履歴

| バージョン | 変更内容 |
|-----------|---------|
| v1 | 初版作成 |
| v2 | レビューフィードバック反映：検索方針明確化、バックエンド拡張順序、プロキシURL、統計情報、空状態、未実装リンクUX |
| v3 | API アクセス方針変更：Next.js API Route を使わず、フロントエンドから FastAPI を直接呼び出す |
| v4 | §2.4 削除フローのエンドポイントを v2 の名残から修正、§4.2 に CORS 注記追加 |
| v5 | §1.3 実装順序の「フロントエンド API Route 実装」を「API クライアント関数実装」に修正 |
| v6 | フィルタリング方針をサーバーサイドに変更（ユーザー確認済み）：§2.3・§2.6・§2.7・§3.2・§4.1・§7・§8.1・§9 を更新 |

---

## 1. 概要

### 1.1 目的

Engineer Cafe Navigator の受付 AI が使用する Vosk（ローカル音声認識）の語彙を、管理者が GUI で管理できるようにする。

現状、認識精度向上のためのドメイン固有語彙は `backend/agents/stt_agent.py` の `ENGINEER_CAFE_GRAMMAR` および `STAGE_GRAMMARS` にハードコードされている。このページは以下の 2 つの目的を達成するための第一歩となる：

1. **固有名詞管理**: 施設名・人名・組織名など、Vosk が誤認識しやすい固有名詞を管理
2. **会話シナリオ最適化**: ステージ別文法（greeting / service_selection / confirmation）に対応する語彙を動的に管理

### 1.2 今回の実装スコープ

**リストページのみ**を実装する。以下は今回実装しない（リンクのみ配置）：

| 機能 | 今回の扱い |
|------|----------|
| 新規作成フォーム | 無効化ボタン表示のみ（遷移先未実装のため disabled） |
| 編集フォーム | 無効化ボタン表示のみ（遷移先未実装のため disabled） |
| インポート画面 | 無効化ボタン表示のみ（遷移先未実装のため disabled） |
| 認識テスト画面 | 無効化ボタン表示のみ（遷移先未実装のため disabled） |
| **削除** | **このページ上のモーダルで完全実装** |

> **注意**: 未実装機能のボタンは `disabled` スタイルを適用し、404 ページに遷移しないようにする。ツールチップで「この機能は準備中です」を表示する。

### 1.3 実装順序（ブロッカー）

**バックエンドのカテゴリ型拡張はフロントエンド実装の前提条件（Day 1）。**

```
1. backend/api/stt_vocabulary.py の VocabularyCategory を7種に拡張（ブロッカー）
   ↓
2. フロントエンド API クライアント関数実装（src/lib/api/stt-vocabulary.ts）
   ↓
3. フロントエンド UI コンポーネント実装
```

バックエンドが4カテゴリのままでは `person` / `tech` / `organization` カテゴリの語彙が Pydantic バリデーションエラーを起こすため、必ず先に対応する。

---

## 2. 機能要件

### 2.1 ページ構成

```
/admin/vosk-settings
├── ヘッダー（タイトル + アクションボタン）
├── 検索・フィルターバー
├── メインエリア
│   ├── 語彙テーブル（左 3/4）
│   └── サイドパネル（右 1/4）
└── ページネーション
```

### 2.2 ヘッダー

| 要素 | 内容 |
|------|------|
| ページタイトル | 「音声認識語彙管理」 |
| 「+ 新規追加」ボタン | 青色。遷移先未実装のため `disabled` スタイル +「準備中」ツールチップ |
| 「インポート」ボタン | 緑色。遷移先未実装のため `disabled` スタイル + 「準備中」ツールチップ |

### 2.3 検索・フィルターバー

| 要素 | 仕様 |
|------|------|
| 検索フィールド | プレースホルダー「検索（単語または読み仮名）」 |
| カテゴリドロップダウン | 「すべて」がデフォルト。全 7 カテゴリを選択可能 |
| 「検索」ボタン | 紫色。クリックで検索実行（Enter キーでも実行） |

検索とカテゴリフィルターは AND 条件で動作する。

#### 検索の実装方針（サーバーサイドフィルタリング）

フィルタリングはすべて FastAPI サーバー側で処理する。フロントエンドはクエリパラメータを組み立てて API を呼び出す。

- **カテゴリフィルタ**: `?category=facility` のようにクエリパラメータとして FastAPI に渡す（既存パラメータ）
- **テキスト検索**: `?search=えんじにあ` のようにクエリパラメータとして FastAPI に渡す（**新規追加パラメータ**、`word`・`reading` の部分一致をサーバー側で処理）
- **AND 条件**: `?category=facility&search=えんじにあ` のように組み合わせ可能
- **再取得トリガー**: 検索ボタンクリック / Enter キー押下でリクエストを発行する（入力ごとにリアルタイム検索はしない）
- **SWR キー**: `category` と `search` の値をキーに含め、変更時に自動再フェッチ

> **バックエンド拡張必須**: `GET /stt/vocabulary` に `search` クエリパラメータを追加する必要がある（§7 参照）。

### 2.4 語彙テーブル

#### 列定義

| 列名 | データソース | 表示形式 |
|------|------------|---------|
| 単語 | `word` | テキスト |
| 読み仮名 | `reading` | テキスト（ひらがな） |
| カテゴリ | `category` | バッジ（カテゴリ別に色分け） |
| 更新日時 | `updated_at` | `YYYY/MM/DD HH:mm` 形式 |
| 操作 | - | 「編集」ボタン（緑、disabled）、「削除」ボタン（赤） |

#### 操作ボタン

- **編集ボタン**: 遷移先未実装のため `disabled` スタイル適用。クリック不可。
- **削除ボタン**: 確認モーダルを表示し、確認後 API 経由で削除を実行

#### 空状態の表示

語彙が 0 件の場合（初期状態、または検索・フィルター結果が 0 件）：
- テーブル代わりに「登録されている語彙がありません」メッセージを中央表示
- フィルター適用時は「条件に一致する語彙が見つかりませんでした」メッセージを表示

#### 削除フロー（完全実装）

1. 削除ボタンをクリック
2. 確認モーダルを表示：
   - タイトル: 「語彙を削除しますか？」
   - メッセージ: 「「{word}」を削除します。この操作は元に戻せません。」
   - ボタン: 「キャンセル」（グレー）、「削除する」（赤）
3. 「削除する」クリック → `DELETE {NEXT_PUBLIC_BACKEND_API_URL}/stt/vocabulary/{id}` を呼び出す
4. 成功: トースト通知「削除しました」→ 全件再取得
5. 失敗: トースト通知「削除に失敗しました」

### 2.5 カテゴリ定義（全 7 種、固定）

カテゴリはフロントエンドのコード内に定数として定義する（API からの取得は不要）。

| カテゴリ ID | 表示名 | バッジ色 | 例 |
|-----------|--------|---------|-----|
| `facility` | 施設 | 青 | エンジニアカフェ、地下ミーティングスペース |
| `location` | 場所 | 緑 | 渋谷駅、天神、博多 |
| `service` | サービス | 紫 | ドロップイン利用、コワーキング |
| `event` | イベント | オレンジ | もくもく会、ミートアップ |
| `person` | 人名 | ピンク | スタッフ名、登壇者名（例：ひさじまさん） |
| `tech` | 技術用語 | シアン | React（リアクト）、LangChain（ラングチェーン）、Python（パイソン） |
| `organization` | 組織・団体 | 黄 | Fukuoka.rb、LINE Fukuoka |

### 2.6 サイドパネル

#### クイックアクション

- **「認識テスト」ボタン**: 緑色。遷移先未実装のため `disabled` スタイル + 「準備中」ツールチップ

#### 統計情報

| 項目 | 内容 |
|------|------|
| 総登録数 | API が返したデータの件数（フィルター後の件数） |
| カテゴリ別内訳 | API が返したデータのカテゴリ別件数（カテゴリ名: N件の形式） |

**統計情報の算出方針**:
- 統計情報は **API が返したフィルター済みデータから算出する**
- 別途「全件取得」APIコールは行わない（余分なリクエスト不要）
- カテゴリフィルターや検索を適用中は、フィルター後の件数・内訳を表示する
- 例: 「施設」カテゴリでフィルタ中は「総登録数: 施設カテゴリ件数」「カテゴリ別内訳: 施設: N件」のみ表示される

### 2.7 ページネーション

- 1 ページあたりの表示件数: **20件**
- API から返ってきた結果（サーバーサイドでフィルタ済み）をクライアントサイドで 20 件ずつ切り出して表示
- 表示テキスト: 「全 N 件中 X-Y 件を表示」（N は API レスポンスの `total` または `data.length`）
- ナビゲーション: 前ページ / 次ページ ボタン
- 現在ページのハイライト表示
- 検索・フィルター変更時はページ 1 にリセット

---

## 3. 非機能要件

### 3.1 言語対応

- 日本語・英語両方の語彙を同一テーブルで管理する
- 現バックエンド API に言語フィールドは存在しないが、`word` フィールドに日英どちらも登録可能
- 将来的に言語フィールドの追加が検討されるが、今回は対象外

### 3.2 パフォーマンス

- **サーバーサイドフィルタリング**: カテゴリ絞り込みとテキスト検索は FastAPI 側で処理し、必要なデータのみ返す
- **ページネーション**: API レスポンスをクライアントサイドで 20 件ずつ切り出して表示
- **再取得タイミング**: 検索ボタンクリック / Enter キー押下時のみリクエスト発行（リアルタイム検索なし）
- ローディング状態を表示する（スピナー）

### 3.3 エラーハンドリング

- API エラー時は画面上部にエラーメッセージを表示
- ネットワークエラー時も同様

---

## 4. API 仕様

### 4.1 バックエンド API（既存 + 拡張）

バックエンドの `backend/api/stt_vocabulary.py` に実装済みの API を使用する。

| メソッド | パス | 用途 |
|--------|------|------|
| `GET` | `/stt/vocabulary` | 語彙一覧取得（クエリパラメータでサーバーサイドフィルタリング） |
| `DELETE` | `/stt/vocabulary/{id}` | 語彙削除 |

#### GET /stt/vocabulary クエリパラメータ

| パラメータ | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `category` | string | 任意 | カテゴリ ID で絞り込み（例: `facility`）。省略時は全カテゴリ |
| `search` | string | 任意 | `word`・`reading` フィールドの部分一致テキスト検索（**新規追加**）。省略時はフィルターなし |

> **注意**: `search` パラメータは現在の `backend/api/stt_vocabulary.py` に存在しない。§7 に記載のバックエンド拡張が必要。

### 4.2 フロントエンドからの API 呼び出し方針

**Next.js API Route は使用しない。フロントエンドから FastAPI を直接呼び出す。**

Server Actions も使用しない。クライアントコンポーネント（`'use client'`）内の `fetch` または専用の API クライアント関数から直接 FastAPI エンドポイントを呼び出す。

| メソッド | 呼び出し先（FastAPI） | 用途 |
|--------|-------------------|------|
| `GET` | `{NEXT_PUBLIC_BACKEND_API_URL}/stt/vocabulary?category={cat}&search={q}` | 語彙一覧取得（サーバーサイドフィルタリング） |
| `DELETE` | `{NEXT_PUBLIC_BACKEND_API_URL}/stt/vocabulary/{id}` | 語彙削除 |

#### 環境変数

既存の `.env.example` に `BACKEND_API_URL=http://localhost:8000` が定義されている。ただしこれはサーバーサイド専用（`NEXT_PUBLIC_` prefix なし）。

クライアントコンポーネントから直接 FastAPI を呼び出すため、**`NEXT_PUBLIC_BACKEND_API_URL`** として公開する必要がある。

```
NEXT_PUBLIC_BACKEND_API_URL=http://localhost:8000  # クライアントサイドからの FastAPI 直接アクセス用
```

`.env.example` / `.env.local` に追記が必要。

#### CORS 設定について

`backend/main.py` で CORS は既に設定済みのため、開発環境（`localhost`）では追加対応不要。
**本番環境では `ALLOWED_ORIGINS` に本番ドメインを追加する必要がある**（バックエンド担当者に確認）。

### 4.3 データモデル（VocabularyItem）

```typescript
interface VocabularyItem {
  id: string;          // UUID
  word: string;        // 語彙（日本語 or 英語）
  reading: string;     // 読み仮名（ひらがな）
  category: VocabularyCategory;  // カテゴリ ID
  priority: number;    // 優先度 1-10（UIには表示しない）
  created_at: string;  // ISO 8601
  updated_at: string;  // ISO 8601
}

type VocabularyCategory =
  | 'facility'      // 施設
  | 'location'      // 場所
  | 'service'       // サービス
  | 'event'         // イベント
  | 'person'        // 人名
  | 'tech'          // 技術用語
  | 'organization'; // 組織・団体

interface VocabularyListResponse {
  success: boolean;
  data: VocabularyItem[];
  total: number;
}
```

---

## 5. UI デザイン仕様

### 5.1 レイアウト

既存の知識ベース管理画面（`frontend/src/app/(admin)/admin/knowledge/`）のパターンに従う。

```
┌─────────────────────────────────────────────────────────────┐
│ 音声認識語彙管理    [+ 新規追加 ※準備中] [インポート ※準備中] │
├─────────────────────────────────────────────────────────────┤
│ [検索フィールド] [カテゴリ▼] [検索]                          │
├──────────────────────────────────────┬──────────────────────┤
│ 単語 | 読み仮名 | カテゴリ | 更新日時 | 操作│ クイックアクション  │
│ ─────────────────────────────────────│ [認識テスト ※準備中]│
│ エンジニアカフェ | えんじにあ... | 施設 | ...│ ─────────────────  │
│ 地下MTGスペース | ちかみーてぃ... | 施設 | ...│ 統計情報           │
│ ...                                  │ 総登録数: 5件        │
│                                      │ 施設: 2件           │
│                                      │ 場所: 1件           │
│                                      │ ...                 │
├──────────────────────────────────────┴──────────────────────┤
│ 全5件中 1-5件を表示                [前] [1] [次]            │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 カラーパレット（Tailwind CSS v3）

| 要素 | クラス |
|------|--------|
| 「+ 新規追加」ボタン（disabled） | `bg-blue-300 cursor-not-allowed opacity-60` |
| 「インポート」ボタン（disabled） | `bg-green-300 cursor-not-allowed opacity-60` |
| 「検索」ボタン | `bg-purple-600 hover:bg-purple-700` |
| 「認識テスト」ボタン（disabled） | `bg-green-300 cursor-not-allowed opacity-60` |
| 「編集」ボタン（disabled） | `text-gray-400 cursor-not-allowed` |
| 「削除」ボタン | `text-red-600 hover:text-red-900` |

### 5.3 カテゴリバッジのカラー

| カテゴリ | Tailwind クラス |
|---------|--------------|
| 施設 (facility) | `bg-blue-100 text-blue-800` |
| 場所 (location) | `bg-green-100 text-green-800` |
| サービス (service) | `bg-purple-100 text-purple-800` |
| イベント (event) | `bg-orange-100 text-orange-800` |
| 人名 (person) | `bg-pink-100 text-pink-800` |
| 技術用語 (tech) | `bg-cyan-100 text-cyan-800` |
| 組織・団体 (organization) | `bg-yellow-100 text-yellow-800` |

---

## 6. ファイル構成（実装対象）

```
frontend/src/app/(admin)/admin/vosk-settings/
├── page.tsx                          # リストページ（メイン、'use client'）
└── components/
    ├── VoskVocabularyTable.tsx       # テーブルコンポーネント
    ├── VoskVocabularyFilter.tsx      # 検索・フィルターバー
    ├── VoskVocabularyStats.tsx       # サイドパネル統計情報
    └── DeleteConfirmModal.tsx        # 削除確認モーダル

frontend/src/lib/api/stt-vocabulary.ts  # FastAPI 直接呼び出しの API クライアント関数
```

**Next.js API Route（`app/api/`）は作成しない。**

---

## 7. バックエンド拡張必要事項（フロントエンド実装の前提条件）

### 7.1 カテゴリ型拡張（ブロッカー・Day 1 対応）

現在の `backend/api/stt_vocabulary.py` の `VocabularyCategory` を 4 種類から 7 種類に拡張する。

```python
# 現状（拡張前）
VocabularyCategory = Literal["facility", "location", "service", "event"]

# 拡張後
VocabularyCategory = Literal[
    "facility",      # 施設
    "location",      # 場所
    "service",       # サービス
    "event",         # イベント
    "person",        # 人名（新規追加）
    "tech",          # 技術用語（新規追加）
    "organization",  # 組織・団体（新規追加）
]
```

この変更を行わないと、フロントエンドから `person` / `tech` / `organization` カテゴリの語彙を作成しようとした際に Pydantic バリデーションエラーが発生する。また、既存 JSON データに混在した場合も `VocabularyItem(**v)` がエラーになる可能性がある。

### 7.2 テキスト検索パラメータ追加（ブロッカー・Day 1 対応）

現在の `GET /stt/vocabulary` エンドポイントに `search` クエリパラメータを追加する。

```python
# backend/api/stt_vocabulary.py（現状）
@router.get("/vocabulary")
async def list_vocabulary(category: Optional[VocabularyCategory] = None):
    ...

# 拡張後
@router.get("/vocabulary")
async def list_vocabulary(
    category: Optional[VocabularyCategory] = None,
    search: Optional[str] = None,  # 新規追加: word・reading の部分一致検索
):
    # フィルタリングロジック例
    items = load_all_vocabulary()
    if category:
        items = [v for v in items if v["category"] == category]
    if search:
        items = [v for v in items if search in v.get("word", "") or search in v.get("reading", "")]
    return {"success": True, "data": items, "total": len(items)}
```

この変更を行わないと、フロントエンドのテキスト検索がサーバーサイドで機能しない。

---

## 8. 既存コードとの差分・注意事項

### 8.1 既存の知識ベース管理画面との違い

| 項目 | 知識ベース管理 | Vosk 語彙管理 |
|------|-------------|-------------|
| データソース | Supabase DB（直接アクセス） | JSON ファイル（バックエンド経由） |
| API アクセス | Supabase クライアント直接 | クライアントコンポーネントから FastAPI を直接 fetch（Next.js API Route / Server Actions 不使用） |
| 検索方式 | サーバーサイド全文検索 | クライアントサイド部分一致 |
| ページネーション | サーバーサイド | クライアントサイド |
| インポート | Markdown | CSV or JSON（今回未実装） |
| 言語フィールド | あり（ja/en） | なし（word に直接登録） |
| 詳細表示 | Markdown レンダリング | なし |
| 削除確認 | `window.confirm()` | 専用モーダル（UX 向上） |

### 8.2 stt_agent.py のハードコード語彙との関係

現在 `ENGINEER_CAFE_GRAMMAR` にハードコードされている語彙（エンジニアカフェ、営業時間、会議室 等）は、将来的にこの管理画面から管理される予定。ただし今回の実装スコープでは移行は行わず、GUI 管理の基盤を構築することが目的。

---

## 9. 受け入れ条件

| # | 条件 |
|---|------|
| 1 | `/admin/vosk-settings` にアクセスすると語彙一覧が表示される |
| 2 | 単語または読み仮名で部分一致検索できる（クライアントサイド） |
| 3 | カテゴリドロップダウンで絞り込みできる（クライアントサイド） |
| 4 | 検索とカテゴリフィルターを組み合わせられる |
| 5 | 語彙 0 件時に適切な空状態メッセージが表示される |
| 6 | サイドパネルの統計情報はフィルターに関係なく全件ベースで表示される |
| 7 | 削除ボタンクリック → 確認モーダル → 削除 API 呼び出し → リスト更新 |
| 8 | 削除成功・失敗時にトースト通知が表示される |
| 9 | 「+ 新規追加」「インポート」「認識テスト」「編集」は disabled スタイルで表示される |
| 10 | ページネーションが正しく動作する（クライアントサイド） |
| 11 | TypeScript 型エラーなし、ESLint エラーなし |
| 12 | `pnpm build` が成功する |

---

## 10. 参考リソース

- 既存管理画面: `frontend/src/app/(admin)/admin/knowledge/`
- バックエンド API: `backend/api/stt_vocabulary.py`
- STT エージェント: `backend/agents/stt_agent.py`
- Tailwind CSS v3 使用（v4 不可）
