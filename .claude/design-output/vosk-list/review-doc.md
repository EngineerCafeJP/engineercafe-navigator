# 音声認識語彙管理ページ レビューレポート

**作成日**: 2026-02-22
**最終更新**: 2026-02-23（最終レビュー実施・未修正問題を記録）
**対象**: `requirement-doc.md` v5 / `plan-doc.md` / `architecture-doc.md`
**レビュアー**: Reviewer Agent

---

## 最終レビュー結果（2026-02-23）

team-lead からの依頼を受けて plan-doc.md / architecture-doc.md を再読み込みしてレビューした。

**結論: 前回指摘した 2 件の問題がいずれも未修正のまま残っている。**

| # | 問題 | 重要度 | 修正状況 |
|---|------|--------|---------|
| 1 | カテゴリフィルタが SWR キーに含まれており要件と矛盾 | High | **未修正** |
| 2 | 未実装ボタンの disabled スタイルが設計に未記載 | Medium | **未修正** |

### 未修正問題の詳細

**[High] カテゴリフィルタの SWR キー問題（未修正箇所の一覧）**:

- `architecture-doc.md §3.2`: `GET {BACKEND_URL}/stt/vocabulary?category={cat}` とカテゴリパラメータが表記されている
- `architecture-doc.md §3.3`: `if (categoryFilter) queryParams.set("category", categoryFilter)` のコードが残存
- `architecture-doc.md §5.1` データフェッチ戦略: 「SWRキー: `{BACKEND_URL}/stt/vocabulary?category={categoryFilter}`」と明記
- `architecture-doc.md §5.1` useMemo: カテゴリフィルタが `filteredData` の `useMemo` に含まれていない（`appliedSearch` のみ）
- `architecture-doc.md §6` データフロー図: 「初回/カテゴリ変更: SWR → 直接 FastAPI: GET .../vocabulary?category=...」
- `architecture-doc.md §10` 受け入れ条件対応表: 条件3「SWRキー変更」と記載
- `architecture-doc.md §11.4`: 「カテゴリフィルタ: 変更即時トリガー（SWRキー変更でリクエスト発行）」
- `plan-doc.md Task 3-1` 状態管理表: categoryFilter の用途欄が「SWR key に使用」
- `plan-doc.md Task 3-1` SWR フック: `queryParams.toString()` をキーに使用するコードが残存

**[Medium] disabled スタイル未記載（未修正箇所の一覧）**:

- `plan-doc.md Task 2-3`: 認識テストボタン「（bg-green-600）→ `/admin/vosk-settings/test` リンク」と記載されており disabled 処理なし
- `plan-doc.md Task 2-4` 操作ボタン: 「編集（text-green-600）→ リンク」と記載されており disabled 処理なし
- `plan-doc.md Task 3-1` レイアウト: 「新規追加[bg-blue-600]」「インポート[bg-green-600]」とアクティブ色のみ記載
- `architecture-doc.md §5.1` レイアウト構造: 同様にアクティブ色のみ記載
- `plan-doc.md §8` 受け入れ条件チェックリスト: 条件 #9「disabled スタイルで表示される」が「遷移リンクが正しいパスを指している」に変わっており disabled の確認項目がない

---

## plan-doc / architecture-doc レビュー（初回）

### レビュー概要

plan-doc.md と architecture-doc.md を要件 v5 と照合してレビューした。全体的に整理されており実装可能な品質だが、**要件との矛盾が 1 件（High）**と、未実装ボタンの disabled 処理の漏れが 1 件（Medium）発見された。

---

### [High] カテゴリフィルタが SWR キーに含まれており、要件「カテゴリはクライアントサイドのみでフィルタ」と矛盾

**カテゴリ**: 要件との整合性
**場所**: `architecture-doc.md §5.1`、`plan-doc.md Task 3-1`

**問題**:
要件 §2.3（v5確定版）には以下が明記されている：

> カテゴリフィルタ: バックエンドの `category` クエリパラメータは使用せず、全件取得後にクライアントでフィルタする

しかし architecture-doc §5.1 の実装コードでは `categoryFilter` を SWR キーに含め、バックエンドへ `category` クエリパラメータを送信している：

```typescript
// architecture-doc §5.1 の実装（現状）
const queryParams = new URLSearchParams();
if (categoryFilter) queryParams.set("category", categoryFilter);  // ← バックエンドに送信している

const { data, error, isLoading, mutate } = useSWR<VocabularyListResponse>(
  `${BACKEND_URL}/stt/vocabulary?${queryParams.toString()}`,  // ← category パラメータ付き
  fetcher
);
```

これでは以下の問題が生じる：
1. カテゴリ変更時に新たなネットワークリクエストが発生する（全件取得になっていない）
2. 統計情報の `data.data` がカテゴリフィルタ後のデータになり、全件統計が取れなくなる（要件 §2.6 違反）
3. 「カテゴリ変更即時トリガー（SWRキー変更でリクエスト発行）」という記述（plan-doc §11.4）が要件と矛盾

**正しい実装**:
```typescript
// category パラメータなし、常に全件取得
const { data, error, isLoading, mutate } = useSWR<VocabularyListResponse>(
  `${BACKEND_URL}/stt/vocabulary`,
  fetcher
);

// カテゴリフィルタはクライアントサイドの useMemo で実施
const filteredData = useMemo(() => {
  if (!data?.data) return [];
  let result = data.data;
  if (categoryFilter) result = result.filter((item) => item.category === categoryFilter);
  if (appliedSearch) {
    const lower = appliedSearch.toLowerCase();
    result = result.filter(
      (item) => item.word.toLowerCase().includes(lower) || item.reading.toLowerCase().includes(lower)
    );
  }
  return result;
}, [data, categoryFilter, appliedSearch]);
```

**改善提案**: architecture-doc §5.1 のデータフェッチ戦略・SWRキー・filteredData の useMemo・データフロー図 §6 を修正する。plan-doc §11.4 の「カテゴリ変更即時トリガー（SWRキー変更でリクエスト発行）」も削除する。

---

### [Medium] 未実装ボタン（新規追加・インポート・認識テスト・編集）の disabled 処理が設計に明記されていない

**カテゴリ**: 要件漏れ
**場所**: `architecture-doc.md §5.1 レイアウト構造`、`plan-doc.md Task 2-3・Task 2-4`

**問題**:
要件 §1.2・§2.2・§2.4（v5確定版）では、未実装機能のボタンはすべて `disabled` スタイルを適用することが定義されている：

- 「+ 新規追加」→ `bg-blue-300 cursor-not-allowed opacity-60`
- 「インポート」→ `bg-green-300 cursor-not-allowed opacity-60`
- 「認識テスト」→ `bg-green-300 cursor-not-allowed opacity-60`（クイックアクション）
- 「編集」→ `text-gray-400 cursor-not-allowed`

しかし architecture-doc §5.1 のレイアウト構造では「新規追加[bg-blue-600]」「インポート[bg-green-600]」とアクティブ色のみが記載されており、`disabled` スタイルへの言及がない。plan-doc Task 2-3 でも「認識テストボタン（bg-green-600）→ `/admin/vosk-settings/test` リンク」とあり、disabled 処理が記載されていない。

受け入れ条件 #9「disabled スタイルで表示される」が実装チェックリストにも明示されていない。

**改善提案**: architecture-doc §5.1 のレイアウト記述・plan-doc Task 2-3/2-4 の操作ボタン仕様に、各ボタンの disabled スタイルクラスを明記する。

---

### ポジティブフィードバック

- **YAGNI 遵守**: `src/lib/api/stt-vocabulary.ts` を独立ファイルにする案を採用せず、page.tsx 内にインラインで実装する方針は適切にシンプル
- **Tailwind パージ対策の明記**: `CATEGORY_METADATA` で動的クラス名生成を避け、フルクラス名を定数化する方針が §11.3 / Task 2-4 に明記されており、実装ミスを防ぐ配慮が良い
- **状態設計の明快さ**: `searchInput` と `appliedSearch` の分離（入力中 vs 確定済み）が設計に明記されており、UX 要件（Enter/ボタンで確定）を正しく実現できる
- **依存関係の明確さ**: Phase 1→Phase 2（並行）→Phase 3 の実装順序が明確
- **バックエンド影響範囲の分析**: Literal 型拡張が影響する行番号（L33, L45, L53, L60, L80, L160）まで特定されており、実装者が迷わない

---

### plan-doc / architecture-doc レビューまとめ

| # | 問題 | カテゴリ | 重要度 |
|---|------|---------|--------|
| 1 | カテゴリフィルタが SWR キーに含まれており要件と矛盾（統計情報も不正確になる） | 要件整合性 | High |
| 2 | 未実装ボタンの disabled スタイルが設計に明記されていない | 要件漏れ | Medium |

---

## v5 確認サマリー（要件ドキュメントレビュー完了）

v4 で指摘した §1.3 の名残が修正されていることを確認した。

- `§1.3` 実装順序: 「フロントエンド API Route 実装」→「フロントエンド API クライアント関数実装（`src/lib/api/stt-vocabulary.ts`）」に修正済み ✓
- ドキュメント内の「API Route」の残存記述はすべて意図的な記述（変更履歴・「使用しない」旨の明示・比較表）のみで、誤った名残はなし ✓

**要件ドキュメントのレビューはこれで完了。実装に進める状態。**

---

## v4 確認サマリー

v3 レビューで指摘した 3 件の対応状況を確認した。

| # | v3 指摘 | v4 対応状況 |
|---|---------|-----------|
| 1 | §2.4 削除フローのエンドポイントが v2 の名残 | **解決** `DELETE {NEXT_PUBLIC_BACKEND_API_URL}/stt/vocabulary/{id}` に修正済み |
| 2 | 本番環境の CORS 設定への言及なし | **解決** §4.2 に「CORS 設定について」節を追加 |
| 3 | 環境変数未定義時のガード処理 | **容認** Architect Agent への共有で合意 |

### [Medium] 新たに発見: §1.3 実装順序に v2 の名残

v4 確認時に新たに発見。§1.3 の実装順序フローに v3 以降で廃止された「API Route」の記述が残っている：

```
2. フロントエンド API Route 実装    ← v3 以降は API Route を作らない方針
```

v3 の方針では `src/lib/api/stt-vocabulary.ts`（API クライアント関数）の実装が対応するため、以下に修正が必要：

```
2. フロントエンド API クライアント関数実装（src/lib/api/stt-vocabulary.ts）
```

この箇所は受け入れ条件やコア仕様ではなく実装ガイドなので影響は軽微だが、実装者が混乱する可能性があるため **v5 での修正を推奨**する。

---

## v3 追加レビュー（API アクセス方針変更）

### 変更概要
v3 で「Next.js API Route を使わずクライアントコンポーネントから FastAPI を直接 fetch」する方針に変更された。この変更を中心に追加レビューを実施した。

---

### [High] §2.4 削除フローのエンドポイント表記が v2 の名残（要修正）

**カテゴリ**: ドキュメント整合性
**場所**: 要件 §2.4

**問題**:
v3 では Next.js API Route を使わない方針に変更されたが、削除フロー §2.4 の記述が v2 の API Route パスのまま残っている：

```
3. 「削除する」クリック → `DELETE /api/admin/stt-vocabulary/{id}` を呼び出す
```

v3 の方針では `/api/admin/stt-vocabulary/{id}` は存在しない（Next.js API Route を作らない）。正しくは FastAPI 直接呼び出しになるはず：

```
3. 「削除する」クリック → `DELETE {NEXT_PUBLIC_BACKEND_API_URL}/stt/vocabulary/{id}` を呼び出す
```

このまま実装すると誤ったエンドポイントを呼び出すコードが生成される可能性がある。

**改善提案**: §2.4 の削除フロー手順 3 を FastAPI 直接エンドポイントに修正する。

---

### [Medium] 本番環境での `ALLOWED_ORIGINS` 設定が要件に言及されていない

**カテゴリ**: セキュリティ / 運用
**場所**: 要件 §4.2、`backend/main.py:36-46`

**確認結果**:
`backend/main.py` にて CORS は適切に設定されている：
```python
_default_origins = ["http://localhost:3000", "http://localhost:3001"]
_allowed_origins = [
    o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()
] or _default_origins
```

開発環境（`localhost:3000`）はデフォルトで許可されており、クライアントサイドから直接 FastAPI を呼び出すアーキテクチャは既存の CORS 設定と整合している。

**懸念点**:
本番環境では `ALLOWED_ORIGINS` に正しい本番ドメインを設定しないとブラウザから CORS エラーが発生する。要件 §4.2 に `NEXT_PUBLIC_BACKEND_API_URL` の記載はあるが、バックエンド側の `ALLOWED_ORIGINS` 設定への言及がない。

**改善提案**: §4.2 の注記として「本番環境ではバックエンドの `ALLOWED_ORIGINS` に本番フロントエンドのドメインを追加すること」を記載する。

---

### [Low] 既存プロジェクトで初めての「クライアント直接 FastAPI 呼び出し」パターン

**カテゴリ**: アーキテクチャ一貫性

**確認結果**:
既存コードを検索したところ、フロントエンドから FastAPI を直接呼び出している箇所（`NEXT_PUBLIC_BACKEND` prefix を使った fetch）は現時点で**存在しない**。すべてのバックエンドアクセスは Next.js API Route または Supabase クライアント経由で行われている。

v3 で採用する「クライアントから FastAPI 直接呼び出し」は、このプロジェクトで**初めて登場するパターン**となる。

**懸念点**:
- `NEXT_PUBLIC_BACKEND_API_URL` が未設定の場合、クライアントサイドで `undefined` + エンドポイントパスとなり、わかりにくいエラーになる
- 将来の実装者が「なぜこのページだけ直接呼び出しなのか」と混乱する可能性がある

**改善提案**: `src/lib/api/stt-vocabulary.ts` 内で `NEXT_PUBLIC_BACKEND_API_URL` 未定義時に明確なエラーを throw するガード処理を実装すること（実装ガイド or architecture-doc に明記）。

---

### v3 変更の総合評価

**ポジティブ**:
- CORS は既に開発環境で機能する設定になっており、追加バックエンド変更不要
- API Route 不使用によりファイル数が減り、構成がシンプルになる
- `src/lib/api/stt-vocabulary.ts` による API クライアント関数の集約は保守性が高い

**要修正**:
- §2.4 削除フローのエンドポイント表記（`/api/admin/stt-vocabulary/{id}` → FastAPI 直接）の修正が必要（High）

---

## v2 対応確認サマリー

requirement-doc v2 にてレビューで指摘したすべての問題が対応済みであることを確認した。

| # | 問題（v1 指摘） | v2 対応状況 |
|---|------|--------|
| 1 | バックエンドカテゴリ型拡張がブロッカーとして明記されていない | **解決** §1.3 で実装順序を明示、§7.1 で Day 1 対応として強調 |
| 2 | 検索方針が不明確 | **解決** §2.3 で「クライアントサイドフィルタリング」と明示 |
| 3 | バックエンドプロキシURL/環境変数が未記載 | **解決** §4.2 で `BACKEND_URL` 環境変数を明記 |
| 4 | 削除確認UIが既存と不一致（`confirm` vs モーダル） | **容認** §8.1 の比較表で `window.confirm()` vs 専用モーダルの差分を明記済み。UX 向上として合意 |
| 5 | フィルター適用時の統計情報が不正確 | **解決** §2.6 で `allVocabulary`（フィルターなし全件）から算出と明示 |
| 6 | 全件取得とページネーションの矛盾 | **解決** §2.3・§2.7・§3.2 でクライアントサイドページネーションと統一 |
| 7 | 空の一覧表示が未定義 | **解決** §2.4「空状態の表示」節を追加、受け入れ条件 #5 に追加 |
| 8 | 未実装リンクのUX（404回避）が未定義 | **解決** §1.2・§2.2・§5.2 で disabled スタイル + ツールチップに変更 |

---

## 総評

要件ドキュメントは全体的に明確で、スコープが適切に絞られている。既存の知識ベース管理画面パターンを踏襲する方針も妥当。ただし、いくつかの技術的な矛盾・不明点・改善余地がある。

---

## 1. 発見された問題と懸念事項

### [High] バックエンド API のカテゴリ型が未拡張のまま実装すると型エラー

**カテゴリ**: 技術的整合性
**場所**: 要件 §4.2 / §7

**問題**:
要件ドキュメントの §7 で「バックエンド拡張が必要」と明記されているが、「フロントエンド実装と同時に対応が必要」という記述が曖昧。

`backend/api/stt_vocabulary.py` の現状:
```python
VocabularyCategory = Literal["facility", "location", "service", "event"]
```

フロントエンドの TypeScript 型定義（要件 §4.2）では 7 カテゴリを定義しているが、バックエンドが 4 カテゴリのままでは `person` / `tech` / `organization` の語彙をAPI経由で作成できず、既存データに混入した場合も `VocabularyItem(**v)` が Pydantic バリデーションエラーを起こす可能性がある。

**改善提案**:
バックエンド拡張をフロントエンド実装の **前提条件**（ブロッカー）として明記し、実装タスクの順序を明確にする。

---

### [High] フロントエンド検索がクライアントサイドかサーバーサイドか不明確

**カテゴリ**: アーキテクチャ不明点
**場所**: 要件 §2.3 / §4.1

**問題**:
バックエンドの `GET /stt/vocabulary` は `category` クエリパラメータのみサポートしており、**`search`（単語・読み仮名の部分一致）クエリパラメータは存在しない**。

```python
# backend/api/stt_vocabulary.py:159-166
@router.get("/stt/vocabulary", response_model=VocabularyListResponse)
async def list_vocabulary(category: Optional[VocabularyCategory] = None):
    vocabulary = await _load_vocabulary()
    if category:
        vocabulary = [v for v in vocabulary if v["category"] == category]
```

要件 §2.3 の「検索（単語または読み仮名）」機能を実現するには、以下のいずれかが必要:
- A) フロントエンドで全件取得してクライアントサイドでフィルタリング
- B) バックエンドに `search` クエリパラメータを追加

要件 §4.1 では `GET /stt/vocabulary` を利用するとしか書かれておらず、どちらの方針か不明。

さらに、データが JSON ファイル管理（最大でも数百〜数千件程度と想定）であればクライアントサイドフィルタリングでも実用的だが、要件 §3.2 には「初回ロードで統計情報を含む全件取得」と記述されており、クライアントサイドで処理する意図とも読める。一方でページネーションは「20件表示」となっており、全件取得とページネーションの組み合わせが整合しているか確認が必要。

**改善提案**:
- 全件取得してクライアントサイドでフィルタ・ページネーション処理する場合: 明示的にそう記述する
- バックエンド拡張する場合: `search` パラメータの追加をバックエンド拡張必要事項 §7 に含める

---

### [Medium] フロントエンドAPI Route のプロキシ先パスが既存と相違

**カテゴリ**: 実装上の注意事項
**場所**: 要件 §4.3

**問題**:
要件 §4.3 では:
```
フロントエンド API Route: /api/admin/stt-vocabulary/ → バックエンド /stt/vocabulary/ へプロキシ
```

知識ベース管理の既存パターンでは `knowledgeBaseUtils`（Supabase クライアント）を直接呼び出す方式で、バックエンドへのHTTPプロキシではない。Vosk 語彙はバックエンドの JSON ファイルに保存されるため、バックエンドへのHTTPプロキシが必要になる。

バックエンドへのプロキシに使う `BACKEND_URL` 環境変数等の設定が要件に記載されていない。

**改善提案**:
- バックエンドへのプロキシURLの環境変数名と設定方法を明記する
- 既存の API Route がバックエンドをプロキシしている例があれば参照する

---

### [Medium] 削除フローで knowledge管理との不一致（`confirm` vs モーダル）

**カテゴリ**: 既存パターンとの一貫性
**場所**: 要件 §2.4 / 既存 `knowledge/page.tsx:35`

**問題**:
既存の知識ベース管理画面では削除確認に `window.confirm()` を使用している:
```typescript
// frontend/src/app/(admin)/admin/knowledge/page.tsx:35
if (!confirm('削除してもよろしいですか？')) return;
```

要件では専用の確認モーダル（`DeleteConfirmModal.tsx`）を実装することになっている。これ自体は UX 向上として歓迎されるが、既存画面と UX が不一致になる点は認識しておく必要がある。

**改善提案**（任意）:
将来的には knowledge 管理画面の削除確認もモーダルに統一することを検討する（今回スコープ外）。

---

### [Medium] 統計情報の計算ロジックが「全件取得」に依存しているが、ページング後データでは不正確

**カテゴリ**: パフォーマンス / 正確性
**場所**: 要件 §2.6 / §3.2

**問題**:
統計情報は「語彙リストの取得結果から算出する（専用 API は不要）」と記載されているが、フィルター（カテゴリ・検索）適用後の結果から統計を算出すると、表示されている件数と実際の全体統計が乖離する。

例: `category=facility` でフィルタしたとき、統計情報には「施設: N件」のみが表示される。これは「全体の統計情報」として不適切。

**改善提案**:
- 統計情報は常に「フィルターなし全件」から算出する
- フィルター適用とは独立して統計用データを保持する（初回ロード時のみ全件取得して統計を計算、以後はキャッシュ）

---

### [Medium] ページネーション件数と全件取得の矛盾

**カテゴリ**: アーキテクチャ整合性
**場所**: 要件 §2.7 / §3.2

**問題**:
§3.2「初回ロードで統計情報を含む全件取得（最大20件表示）」という記述が矛盾している。
- 「全件取得」なら何百件もあるデータを全件フェッチする
- 「最大20件表示」はページネーションのページサイズ

「全件取得してクライアントサイドでページネーション」なのか、「20件のみ取得してサーバーサイドページネーション」なのかが不明。

バックエンド API には `page` / `limit` パラメータが存在しないため、現状では全件取得+クライアントページネーションしか実現できない。

**改善提案**:
全件取得 + クライアントサイドページネーション方式であることを明確化する（あるいはバックエンド拡張必要事項に `page`/`limit` を追加する）。

---

### [Low] カテゴリドロップダウンのオプションが固定値（要件 §2.5）

**カテゴリ**: YAGNI / 拡張性
**場所**: 要件 §2.5

**問題**:
カテゴリは 7 種類固定とされており、カテゴリ一覧をAPIから取得する仕組みは不要。これは適切なスコープ判断。ただし要件 §2.5 の「今後拡張が必要」という記述と「固定」という仕様が矛盾していない点を確認するだけでよい。問題なし。

---

### [Low] 空の一覧表示のエッジケースが未定義

**カテゴリ**: エッジケース
**場所**: 要件 §2.4

**問題**:
語彙が 0 件のとき（初期状態 or フィルター結果 0 件）のテーブル表示が要件に定義されていない。

**改善提案**:
- 「データがありません」等の空状態メッセージを表示することを受け入れ条件に追加する（knowledge管理画面は現状この状態の定義なし）

---

### [Low] 「認識テスト」ボタンと「インポート」ボタンの遷移先が未実装

**カテゴリ**: 実装考慮
**場所**: 要件 §1.2 / §2.2

**問題**:
遷移先が未実装のリンクについて、リンク先の動作が不明。Next.js では未実装パスへのリンクは 404 になる。ユーザーが誤操作したとき UX が悪い。

**改善提案**:
未実装リンクは `href="#"` + `pointer-events-none` + `disabled` スタイル、またはツールチップで「準備中」と表示する方式を検討する。要件に明記することが望ましい。

---

## 2. ポジティブフィードバック

- **スコープの明確さ**: リストページ + 削除のみに絞り込み、未実装機能はリンクのみとするアプローチは YAGNI 原則に忠実で適切。
- **既存パターンの踏襲**: `knowledge` 管理画面との共通構造（useSWR + fetcher パターン、Tailwind スタイリング）を明示的に指示している点が良い。
- **カラーパレットの具体性**: Tailwind クラスまで具体的に定義されており、実装時の判断を減らせる。
- **受け入れ条件の明確さ**: 11項目の受け入れ条件が具体的で検証しやすい。
- **バックエンド拡張の明記**: 現状との差分が §7 で明示されている点が良い。
- **ファイル構成の具体性**: 実装対象ファイルが明示されており、コンポーネント分割も適切なサイズ感。
- **セキュリティ**: 管理者認証については既存の `(admin)` ルートグループの仕組みに乗るため、追加実装不要（適切な設計）。

---

## 3. 問題一覧まとめ（v1 指摘・v2 対応状況）

| # | 問題 | カテゴリ | 重要度 | v2 対応 |
|---|------|---------|--------|---------|
| 1 | バックエンドカテゴリ型拡張がブロッカーとして明記されていない | 技術的整合性 | High | 解決済み |
| 2 | 検索機能がクライアントサイドかサーバーサイドか不明確（バックエンドAPIに`search`パラメータなし） | アーキテクチャ不明点 | High | 解決済み |
| 3 | バックエンドプロキシのURL/環境変数設定が未記載 | 実装上の注意事項 | Medium | 解決済み |
| 4 | 削除確認UIが既存知識ベース管理と不一致（`confirm` vs モーダル） | 既存パターン一貫性 | Medium | 容認（差分として明記） |
| 5 | フィルター適用時の統計情報が全体統計として不正確 | パフォーマンス/正確性 | Medium | 解決済み |
| 6 | 全件取得とサーバーサイドページネーションの矛盾 | アーキテクチャ整合性 | Medium | 解決済み |
| 7 | 空の一覧表示のエッジケースが未定義 | エッジケース | Low | 解決済み |
| 8 | 未実装リンクの UX（404回避）が未定義 | UX | Low | 解決済み |

---

## 4. 改善提案サマリー

### 要件ドキュメントへの追記が必要な項目

1. **バックエンド拡張を実装前提条件として明記**:
   「バックエンドのカテゴリ型拡張はフロントエンド実装の前提条件（Day 1）」として明記する。

2. **検索方針を明確化**:
   「全件取得してクライアントサイドでフィルタ + ページネーション」と明示する（またはバックエンドに `search` / `page` / `limit` を追加する）。

3. **バックエンドプロキシURLの設定**:
   環境変数 `BACKEND_URL` または Next.js の rewrites設定について言及する。

4. **空状態の定義**:
   「0件の場合は「登録されている語彙がありません」を表示」など受け入れ条件に追加する。

5. **未実装リンクの挙動**:
   「遷移先未実装のボタン/リンクは disabled スタイルを適用し、404に遷移しないようにする」と定義する。

---

## 5. 後続レビュー対象

plan-doc.md と architecture-doc.md が作成された後、以下を追加レビューする:

- タスク分割の粒度（大きすぎ/小さすぎ）
- コンポーネント分割の妥当性（過度な抽象化がないか）
- API Route の実装方針（バックエンドプロキシの実装詳細）
- エラーハンドリングの網羅性
