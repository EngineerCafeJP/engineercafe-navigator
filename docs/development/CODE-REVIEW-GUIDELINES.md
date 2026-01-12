# エージェント実装コードレビューガイドライン

> Engineer Cafe Navigator プロジェクトのコードレビュー品質向上とプロセス標準化のためのガイドライン

## 目次

- [概要](#概要)
- [1. レビュープロセス](#1-レビュープロセス)
- [2. PR作成前のチェックリスト](#2-pr作成前のチェックリスト)
- [3. レビュー観点](#3-レビュー観点)
- [4. レビューコメントのベストプラクティス](#4-レビューコメントのベストプラクティス)
- [5. PRテンプレート](#5-prテンプレート)
- [6. レビュアー用チェックリスト](#6-レビュアー用チェックリスト)
- [7. マージ前の最終確認](#7-マージ前の最終確認)
- [クイックリファレンス](#クイックリファレンス)

---

## 概要

このガイドラインは、LangGraph/FastAPI ベースのエージェント実装のコードレビュー品質を向上させ、レビュープロセスを標準化することを目的としています。

### 対象

- **PR作成者（Claude Code）**: 実装とテストを担当
- **レビュアー（Cursor PM）**: コードレビューと承認を担当

### 前提知識

- [2-Agent ワークフロールール](../../.claude/rules/workflow.md)
- [エージェント実装チェックリスト](./AGENT-IMPLEMENTATION-CHECKLIST.md)
- [テスト作成ガイド](../testing/TESTING-GUIDE.md)

---

## 1. レビュープロセス

### 1.1 全体フロー

```
実装完了 → セルフチェック → CI/CDグリーン → PR作成 → レビュー依頼 → レビュー → 修正 → 承認 → マージ
```

### 1.2 役割分担

#### Claude Code（実装者）の責務

1. **実装**: Plans.md のタスクを実装
2. **セルフチェック**: PR作成前チェックリストの実行
3. **CI/CD確認**: すべてのチェックがグリーンであることを確認
4. **PR作成**: テンプレートに従った丁寧な説明
5. **修正対応**: レビュアーの指摘に対する迅速な修正

#### Cursor（PM/レビュアー）の責務

1. **優先度判断**: レビューの優先順位付け
2. **品質チェック**: レビュー観点に基づいた確認
3. **建設的フィードバック**: 具体的で実行可能な指摘
4. **承認判断**: マージの可否判断
5. **本番デプロイ承認**: main ブランチへのマージ承認

### 1.3 レビュー依頼の方法

#### PR作成時

1. **Plans.md のタスクを `cc:DONE` にマーク**
2. **GitHub で PR を作成**（PRテンプレート使用）
3. **`/handoff-to-cursor` でハンドオフ報告**

例:
```markdown
## ハンドオフ報告

### 完了タスク
- [x] BusinessInfoAgent の実装
- [x] テストカバレッジ 92% 達成
- [x] CI/CD グリーン確認

### PR URL
https://github.com/owner/repo/pull/123

### レビュー依頼内容
- RAG統合の実装確認
- エラーハンドリングの妥当性確認
- テストケースの網羅性確認
```

### 1.4 レビューの優先順位

| 優先度 | 条件 | 対応時間 |
|-------|------|---------|
| **緊急** | 本番障害修正、セキュリティFix | 即時 |
| **高** | 機能追加、API変更、重要なリファクタリング | 24時間以内 |
| **中** | バグ修正、ドキュメント更新 | 48時間以内 |
| **低** | コードクリーンアップ、typo修正 | 1週間以内 |

---

## 2. PR作成前のチェックリスト

### 2.1 コード品質チェック

```bash
# Backend（Python）
cd backend

# フォーマット適用
ruff format .

# リント自動修正
ruff check . --fix

# 手動確認が必要な警告をチェック
ruff check .
```

**チェックポイント:**
- [ ] Ruff の警告がゼロ
- [ ] Black フォーマットが適用済み
- [ ] 型ヒントがすべて付与されている
- [ ] docstring が完備されている

### 2.2 テスト実行

```bash
# 単体テスト
pytest tests/agents/test_{agent_name}.py -v

# カバレッジ確認
pytest tests/agents/test_{agent_name}.py --cov=agents/{agent_name} --cov-report=html

# 統合テスト
pytest tests/integration/ -v
```

**チェックポイント:**
- [ ] すべてのテストがパス
- [ ] カバレッジが 90% 以上
- [ ] エッジケースのテストが含まれている
- [ ] モックが適切に使用されている

### 2.3 CI/CD チェック

```bash
# Frontend（該当する場合）
cd frontend
pnpm lint
pnpm typecheck
pnpm build
```

**チェックポイント:**
- [ ] GitHub Actions の全チェックがグリーン
- [ ] ビルドエラーがない
- [ ] 型チェックエラーがない

### 2.4 ドキュメント確認

**チェックポイント:**
- [ ] `docs/migration/agents/{agent-name}/SPEC.md` が最新
- [ ] `docs/migration/agents/{agent-name}/TESTING.md` が最新
- [ ] README やその他のドキュメントが更新されている（該当する場合）
- [ ] コード内の docstring が充実している

---

## 3. レビュー観点

### 3.1 機能性

#### RAG検索の実装

**確認項目:**
- [ ] Enhanced RAG Search の使用が適切か
- [ ] カテゴリマッピングが正しいか（hours, pricing, facility-info など）
- [ ] クエリ拡張が適切に機能しているか
- [ ] 検索結果の取得数が適切か（max_results 設定）

**良い例:**
```python
# カテゴリマッピングが明確
category = self._map_request_type_to_category(request_type)

# Enhanced RAG呼び出しが適切
rag_result = await self.enhanced_rag.search(
    query=query,
    category=category,
    language=language,
    include_advice=True,
    max_results=10
)
```

**悪い例:**
```python
# カテゴリが常に "general"
rag_result = await self.enhanced_rag.search(query=query)

# エラーハンドリングがない
context = rag_result["data"]["context"]  # KeyError の可能性
```

#### LLM統合

**確認項目:**
- [ ] プロンプトが適切に構築されているか
- [ ] トークン使用量が考慮されているか
- [ ] レスポンスのパースが堅牢か
- [ ] 感情タグの決定ロジックが妥当か

**良い例:**
```python
# プロンプトが言語に応じて分岐
if language == "en":
    prompt = f"Answer: {query}\nContext: {context}"
else:
    prompt = f"質問: {query}\n情報: {context}"

# 適切なモデル設定
response = await self.llm_provider.generate(
    messages=[{"role": "user", "content": prompt}],
    config=get_model_config("facility_info"),
)
```

#### エラーハンドリング

**確認項目:**
- [ ] 適切な例外がキャッチされているか
- [ ] フォールバックメッセージが用意されているか
- [ ] エラーログが適切に出力されているか
- [ ] ユーザーフレンドリーなエラーメッセージか

**良い例:**
```python
try:
    response = await self.llm_provider.generate(...)
except ProviderTimeoutError:
    logger.warning(f"LLM timeout for query: {query[:50]}...")
    return self._fallback_response(language)
except ProviderError as e:
    logger.error(f"LLM error: {e}")
    return self._error_response(language, str(e))
```

**悪い例:**
```python
# bare except は避ける
try:
    response = await self.llm_provider.generate(...)
except:  # 何の例外か不明
    return {"answer": "エラーが発生しました"}
```

### 3.2 コード品質

#### コーディング規約

**確認項目:**
- [ ] PEP 8 に準拠しているか
- [ ] Ruff/Black フォーマットが適用されているか
- [ ] 型ヒントが完全か
- [ ] docstring が Google スタイルで記述されているか

**良い例:**
```python
async def answer_facility_query(
    self,
    query: str,
    request_type: str | None = None,
    language: str = "ja",
    session_id: str | None = None,
) -> dict[str, Any]:
    """
    施設情報クエリに回答する。

    Args:
        query: ユーザークエリ
        request_type: リクエストタイプ（wifi, facility など）
        language: 言語コード（ja または en）
        session_id: セッションID

    Returns:
        回答辞書 {answer, emotion, metadata}

    Raises:
        ValueError: 無効なパラメータが指定された場合
    """
    ...
```

#### 命名規則

**確認項目:**
- [ ] 変数名が意味のある名前か
- [ ] 関数名が動詞で始まっているか
- [ ] クラス名がPascalCaseか
- [ ] 定数が大文字で定義されているか

**良い例:**
```python
# 明確な変数名
category_mapping = {"hours": "hours", "price": "pricing"}
rag_result = await self.enhanced_rag.search(...)

# 動詞で始まる関数名
def _map_request_type_to_category(self, request_type: str) -> str:
    ...

def _determine_emotion(self, request_type: str, response_text: str) -> str:
    ...
```

**悪い例:**
```python
# 不明瞭な変数名
m = {"h": "hours", "p": "pricing"}
r = await self.rag.search(...)

# 名詞で始まる関数名
def request_type_category(self, request_type: str) -> str:
    ...
```

### 3.3 パフォーマンス

#### RAG検索の効率性

**確認項目:**
- [ ] 不要な検索が実行されていないか
- [ ] 検索結果の取得数が適切か
- [ ] キャッシュが有効活用されているか

**良い例:**
```python
# 必要な場合のみ検索
if not context:
    rag_result = await self.enhanced_rag.search(...)
```

#### LLM API呼び出しの最適化

**確認項目:**
- [ ] プロンプトが簡潔か（トークン使用量削減）
- [ ] 不要なAPI呼び出しがないか
- [ ] タイムアウト設定が適切か

#### メモリ使用量

**確認項目:**
- [ ] 大きなデータを不必要にメモリに保持していないか
- [ ] ジェネレータが適切に使用されているか

### 3.4 テスト

#### テストカバレッジ

**確認項目:**
- [ ] カバレッジが 90% 以上か
- [ ] 重要なパスがすべてテストされているか
- [ ] カバレッジレポートが添付されているか

#### ユニットテストの質

**確認項目:**
- [ ] テストが独立しているか（他のテストに依存していない）
- [ ] テストケース名が明確か
- [ ] Arrange-Act-Assert パターンに従っているか
- [ ] 境界値テストが含まれているか

**良い例:**
```python
@pytest.mark.asyncio
async def test_wifi_query_japanese(self):
    """Wi-Fi関連のクエリテスト（日本語）"""
    # Arrange
    agent = FacilityAgent()
    with patch.object(agent.enhanced_rag, "search", new_callable=AsyncMock) as mock_rag:
        mock_rag.return_value = {
            "success": True,
            "data": {"context": "Wi-Fiは無料で利用できます。"}
        }

        # Act
        result = await agent.answer_facility_query(
            query="Wi-Fiはありますか？",
            request_type="wifi",
            language="ja"
        )

        # Assert
        assert result["answer"] is not None
        assert "wifi" in result["answer"].lower()
        assert result["metadata"]["request_type"] == "wifi"
```

#### モックの適切な使用

**確認項目:**
- [ ] 外部依存がモック化されているか
- [ ] モックの返り値が現実的か
- [ ] モックが過度に使用されていないか（実装の詳細に依存していない）

**良い例:**
```python
# 外部API呼び出しをモック
with patch.object(agent.llm_provider, "generate", new_callable=AsyncMock) as mock_llm:
    mock_llm.return_value = "[relaxed]Wi-Fiは無料です。"
    result = await agent.answer_facility_query(...)
```

**悪い例:**
```python
# 内部メソッドまでモック化（過度なモック）
with patch.object(agent, "_map_request_type_to_category") as mock_map:
    mock_map.return_value = "facility-info"
    # 実装の詳細に依存しすぎている
```

#### エッジケースのテスト

**確認項目:**
- [ ] 空文字列、None の処理がテストされているか
- [ ] エラーケースがテストされているか
- [ ] 境界値がテストされているか

**テストすべきエッジケース:**
```python
# 空クエリ
await agent.answer_facility_query(query="", ...)

# RAG検索失敗
mock_rag.return_value = {"success": False}

# LLMタイムアウト
mock_llm.side_effect = ProviderTimeoutError()

# 不正な言語コード
await agent.answer_facility_query(query="test", language="xx")
```

### 3.5 セキュリティ

#### APIキーの取り扱い

**確認項目:**
- [ ] APIキーがハードコードされていないか
- [ ] 環境変数から適切に取得しているか
- [ ] ログにAPIキーが出力されていないか

**良い例:**
```python
# 環境変数から取得
api_key = os.getenv("OPENROUTER_API_KEY")
if not api_key:
    raise ValueError("OPENROUTER_API_KEY is not set")
```

#### 入力バリデーション

**確認項目:**
- [ ] ユーザー入力が適切にバリデーションされているか
- [ ] SQLインジェクション対策がされているか
- [ ] コマンドインジェクション対策がされているか

#### エラーメッセージの情報漏洩

**確認項目:**
- [ ] エラーメッセージに機密情報が含まれていないか
- [ ] スタックトレースが本番環境で公開されていないか

**良い例:**
```python
# ユーザー向けメッセージは一般的に
return {
    "answer": "申し訳ございません。処理中にエラーが発生しました。",
    "emotion": "apologetic"
}

# 詳細はログに
logger.error(f"Database error: {e}", exc_info=True)
```

### 3.6 保守性

#### コードの可読性

**確認項目:**
- [ ] 関数が適切なサイズか（50行以内目安）
- [ ] ネストが深すぎないか（3レベル以内）
- [ ] 複雑なロジックが分割されているか

**良い例:**
```python
# 複雑なロジックを小さな関数に分割
async def answer_facility_query(self, query: str, ...) -> dict:
    category = self._map_request_type_to_category(request_type)
    rag_result = await self._search_rag(query, category, language)

    if not self._is_valid_result(rag_result):
        return self._get_default_response(language)

    return await self._generate_response(query, rag_result, language)
```

#### 適切なコメント

**確認項目:**
- [ ] 複雑なロジックにコメントがあるか
- [ ] コメントが「なぜ」を説明しているか（「何を」ではなく）
- [ ] TODOコメントに担当者と期限が記載されているか

**良い例:**
```python
# Enhanced RAGの検索結果を最大10件取得
# 地下施設のバリエーションを網羅するため、多めに取得
rag_result = await self.enhanced_rag.search(
    query=expanded_query,
    category=category,
    max_results=10
)
```

#### ドキュメント更新

**確認項目:**
- [ ] 仕様ドキュメントが更新されているか
- [ ] API変更がドキュメントに反映されているか
- [ ] 使用例が最新か

---

## 4. レビューコメントのベストプラクティス

### 4.1 建設的なフィードバックの書き方

#### 基本原則

1. **具体的に**: 何が問題で、どう改善すべきか明確に
2. **前向きに**: 否定ではなく、改善提案として
3. **説明的に**: なぜそれが重要かを説明
4. **サンプル付き**: 可能な限りコード例を提示

#### 良いコメント例

```markdown
**MUST: エラーハンドリングの改善**

現在の実装では、RAG検索が失敗した場合にKeyErrorが発生する可能性があります。

\`\`\`python
# 現在の実装
context = rag_result["data"]["context"]  # KeyErrorの可能性
\`\`\`

以下のように安全にアクセスすることをお勧めします:

\`\`\`python
if not rag_result.get("success"):
    return self._get_default_response(language)

context = rag_result.get("data", {}).get("context", "")
\`\`\`

**理由**: 外部APIの応答形式が変わった場合でも、エラーで停止せずフォールバック応答を返すことができます。

**参考**: [エラーハンドリングのベストプラクティス](./docs/development/BEST-PRACTICES.md#error-handling)
```

#### 悪いコメント例

```markdown
# ❌ 具体性がない
これは良くないです。修正してください。

# ❌ 否定的すぎる
このコードはひどい。何も考えていない。

# ❌ 理由がない
ここは直してください。
```

### 4.2 コメントの優先度付け

#### MUST（必須修正）

- セキュリティ上の問題
- 機能が動作しない致命的なバグ
- パフォーマンス上の重大な問題
- テストが不足している箇所

**例:**
```markdown
**MUST: SQLインジェクション対策**

現在の実装ではユーザー入力をそのままクエリに埋め込んでおり、SQLインジェクションのリスクがあります。

\`\`\`python
# 危険
query = f"SELECT * FROM users WHERE name = '{user_input}'"

# 安全
query = "SELECT * FROM users WHERE name = %s"
cursor.execute(query, (user_input,))
\`\`\`
```

#### SHOULD（推奨修正）

- コード品質の向上
- 保守性の改善
- ベストプラクティスへの準拠
- ドキュメントの充実

**例:**
```markdown
**SHOULD: docstringの追加**

この関数は複雑なロジックを含んでいるため、docstringを追加することをお勧めします。

\`\`\`python
def _filter_context_by_request_type(self, context: str, request_type: str) -> str:
    """
    コンテキストをリクエストタイプに応じてフィルタリングする。

    Args:
        context: RAG検索結果のコンテキスト
        request_type: リクエストタイプ（hours, price など）

    Returns:
        フィルタリングされたコンテキスト
    """
    ...
\`\`\`
```

#### NICE_TO_HAVE（あると良い）

- さらなる最適化
- コメントの追加
- 変数名の改善
- コードスタイルの統一

**例:**
```markdown
**NICE_TO_HAVE: 変数名の明確化**

`r` という変数名は短すぎて意味が不明瞭です。`rag_result` のように明確な名前にすると可読性が向上します。

\`\`\`python
# Before
r = await self.rag.search(query)

# After
rag_result = await self.enhanced_rag.search(query)
\`\`\`
```

### 4.3 参考資料へのリンク

レビューコメントには、関連する参考資料へのリンクを含めると効果的です。

**例:**
```markdown
**参考資料:**
- [Pythonエラーハンドリングのベストプラクティス](https://docs.python.org/3/tutorial/errors.html)
- [プロジェクトのコーディング規約](./docs/development/CODING-STANDARDS.md)
- [類似の実装例](./backend/agents/business_info_agent.py#L45-L60)
```

---

## 5. PRテンプレート

### 5.1 基本テンプレート

```markdown
## 変更内容

<!-- このPRで何を実装/修正したかを簡潔に説明 -->

### 実装内容

- [ ] BusinessInfoAgent の RAG統合
- [ ] エラーハンドリングの追加
- [ ] ユニットテストの作成

### 変更ファイル

- `backend/agents/business_info_agent.py`: エージェント実装
- `backend/tests/agents/test_business_info_agent.py`: テスト実装
- `docs/migration/agents/business-info-agent/SPEC.md`: 仕様更新

## テスト結果

### ユニットテスト

\`\`\`bash
pytest tests/agents/test_business_info_agent.py -v
\`\`\`

**結果:**
- テスト数: 15
- 成功: 15
- 失敗: 0
- カバレッジ: 92%

### カバレッジレポート

\`\`\`
Name                                  Stmts   Miss  Cover
---------------------------------------------------------
backend/agents/business_info_agent.py    120      9    92%
\`\`\`

### CI/CD 確認

- [x] GitHub Actions: すべてグリーン
- [x] Backend Lint: PASS
- [x] Frontend Build: PASS（該当なし）

## スクリーンショット/ログ

<!-- 該当する場合は追加 -->

### 実行ログ例

\`\`\`
[BusinessInfoAgent] Processing query: 営業時間は？
[BusinessInfoAgent] RAG search: category=hours, results=3
[BusinessInfoAgent] LLM response generated successfully
Response: エンジニアカフェの営業時間は9:00〜22:00です。
\`\`\`

## レビュー依頼事項

<!-- レビュアーに特に確認してほしい点を記載 -->

1. RAG検索のカテゴリマッピングが適切か
2. エラーハンドリングのフォールバック戦略が妥当か
3. テストケースの網羅性が十分か

## 関連Issue/PR

- Closes #123
- Related to #456

## チェックリスト

### コード品質

- [x] Ruff/Black フォーマット適用済み
- [x] 型ヒント完備
- [x] docstring 完備
- [x] コードレビュー観点を自己確認

### テスト

- [x] ユニットテスト作成
- [x] カバレッジ 90% 以上
- [x] エッジケーステスト含む
- [x] モック適切に使用

### ドキュメント

- [x] SPEC.md 更新
- [x] TESTING.md 更新
- [x] README 更新（該当する場合）

### CI/CD

- [x] GitHub Actions グリーン
- [x] ローカルで全テストパス
- [x] ビルドエラーなし
```

### 5.2 バグ修正用テンプレート

```markdown
## バグ修正内容

### 問題の説明

<!-- どんなバグがあったか -->

**症状:**
- RAG検索が失敗した場合にKeyErrorが発生していた

**再現手順:**
1. 営業時間を質問
2. RAG検索が失敗するケース
3. KeyError が発生

**影響範囲:**
- BusinessInfoAgent のすべてのクエリ

### 修正内容

<!-- どのように修正したか -->

\`\`\`python
# Before
context = rag_result["data"]["context"]

# After
if not rag_result.get("success"):
    return self._get_default_response(language)

context = rag_result.get("data", {}).get("context", "")
\`\`\`

**修正ポイント:**
- RAG検索の成功/失敗を明示的にチェック
- 安全なdict アクセスに変更
- フォールバック応答を返すように修正

### テスト結果

\`\`\`bash
# 修正前（失敗）
pytest tests/agents/test_business_info_agent.py::test_rag_failure -v
# FAILED: KeyError

# 修正後（成功）
pytest tests/agents/test_business_info_agent.py::test_rag_failure -v
# PASSED
\`\`\`

## チェックリスト

- [x] バグの原因を特定
- [x] 修正を実装
- [x] 再現テストを追加
- [x] 回帰テストがすべてパス
- [x] CI/CD グリーン
```

### 5.3 リファクタリング用テンプレート

```markdown
## リファクタリング内容

### 目的

<!-- なぜリファクタリングが必要だったか -->

関数が長すぎて（150行）可読性が低下していたため、小さな関数に分割しました。

### 変更内容

**Before:**
- `answer_facility_query()`: 150行の単一関数

**After:**
- `answer_facility_query()`: 30行（メイン処理）
- `_search_rag()`: RAG検索ロジック
- `_generate_response()`: LLM応答生成ロジック
- `_is_valid_result()`: 結果検証ロジック

### 動作保証

**テストカバレッジ:**
- リファクタリング前: 92%
- リファクタリング後: 93%

**すべてのテストがパス:**
\`\`\`bash
pytest tests/agents/test_facility_agent.py -v
# 25 passed
\`\`\`

## チェックリスト

- [x] 動作が変わっていないことを確認
- [x] すべてのテストがパス
- [x] カバレッジが低下していない
- [x] docstring を更新
- [x] CI/CD グリーン
```

---

## 6. レビュアー用チェックリスト

### 6.1 設計・アーキテクチャ

```markdown
### 設計・アーキテクチャ

- [ ] 単一責務原則に従っているか
  - エージェントが1つの明確な責務を持っているか
  - 他エージェントの責務を侵していないか

- [ ] 他エージェントとの境界が明確か
  - RouterAgentとの連携が適切か
  - MemoryAgentの使用が適切か

- [ ] 依存関係が適切か
  - 循環依存がないか
  - 必要最小限の依存に絞られているか

- [ ] 拡張性を考慮した設計か
  - 新しい機能追加が容易か
  - ハードコードされた値がないか
```

### 6.2 コード品質

```markdown
### コード品質

- [ ] 型ヒントが完全か
  - すべての関数シグネチャに型ヒントがあるか
  - カスタム型が適切に定義されているか
  - Optional, Union, Literal が適切に使用されているか

- [ ] docstring が適切か
  - Google スタイルで記述されているか
  - Args, Returns, Raises が明記されているか
  - 複雑なロジックに説明があるか

- [ ] 関数サイズが適切か
  - 1関数が50行以内目安か
  - 複雑な処理が分割されているか

- [ ] ネストが深すぎないか
  - 3レベル以内に収まっているか
  - early return が活用されているか

- [ ] マジックナンバーがないか
  - 数値が定数として定義されているか
  - 定数名が意味のある名前か
```

### 6.3 エラーハンドリング

```markdown
### エラーハンドリング

- [ ] 例外処理が適切か
  - 具体的な例外をキャッチしているか（bare except を避ける）
  - 例外メッセージが適切か

- [ ] フォールバックが実装されているか
  - API失敗時の処理があるか
  - タイムアウト時の処理があるか
  - 無効な入力への対処があるか

- [ ] エラーメッセージが適切か
  - ユーザーフレンドリーか
  - 機密情報が含まれていないか

- [ ] ログ出力が適切か
  - エラー時にログが出力されるか
  - ログレベルが適切か（ERROR, WARNING, INFO）
```

### 6.4 セキュリティ

```markdown
### セキュリティ

- [ ] 機密情報がハードコードされていないか
  - APIキーが環境変数から取得されているか
  - パスワードやトークンがコードに含まれていないか

- [ ] 入力値のバリデーションがあるか
  - ユーザー入力が適切にチェックされているか
  - 型チェックがあるか

- [ ] SQLインジェクション対策がされているか
  - プレースホルダーが使用されているか
  - ORM が適切に使用されているか

- [ ] XSS対策がされているか（該当する場合）
  - ユーザー入力がエスケープされているか
```

### 6.5 テスト

```markdown
### テスト

- [ ] テストカバレッジが 90% 以上か
  - カバレッジレポートが添付されているか
  - 重要なパスがカバーされているか

- [ ] 正常系テストがあるか
  - 基本的な機能が動作することを確認しているか

- [ ] 異常系テストがあるか
  - エラーハンドリングがテストされているか
  - フォールバックがテストされているか

- [ ] エッジケーステストがあるか
  - 空文字列、None の処理がテストされているか
  - 境界値がテストされているか

- [ ] モックが適切に使用されているか
  - 外部依存がモック化されているか
  - モックが過度に使用されていないか
```

### 6.6 ドキュメント

```markdown
### ドキュメント

- [ ] SPEC.md が最新か
  - 実装との差分がないか
  - 入出力インターフェースが正確か

- [ ] TESTING.md が最新か
  - テスト結果が記録されているか
  - テストケースが明記されているか

- [ ] README 更新が必要か（該当する場合）
  - 新機能の説明があるか
  - 使用方法が更新されているか
```

### 6.7 パフォーマンス

```markdown
### パフォーマンス

- [ ] 非同期処理が適切か
  - I/Oバウンド処理に async/await が使用されているか
  - 並列実行可能な処理が asyncio.gather() で実行されているか

- [ ] 不要なAPI呼び出しがないか
  - キャッシュが活用されているか
  - 重複した検索がないか

- [ ] キャッシュが適切に使用されているか
  - TTL（有効期限）が適切か
  - キャッシュキーが適切か

- [ ] メモリリークの可能性がないか
  - 不要なオブジェクトの参照が解放されているか
  - ジェネレータが活用されているか
```

---

## 7. マージ前の最終確認

### 7.1 マージ条件

以下のすべてを満たしていることを確認してからマージしてください。

```markdown
### 必須条件（1つでも満たさない場合はマージ不可）

- [ ] すべてのレビューコメントが解決済み
- [ ] MUST（必須修正）の指摘がすべて修正済み
- [ ] GitHub Actions のすべてのチェックがグリーン
- [ ] テストカバレッジが 90% 以上
- [ ] コンフリクトが解消されている
- [ ] 最新のベースブランチが取り込まれている（develop または main）
- [ ] 少なくとも1人のレビュアーの承認がある

### 推奨条件（可能な限り満たす）

- [ ] SHOULD（推奨修正）の指摘が修正済み
- [ ] ドキュメントが最新化されている
- [ ] 変更内容がCHANGELOGに記載されている（該当する場合）
```

### 7.2 ブランチ別マージルール

#### develop ブランチへのマージ

```markdown
- [ ] feature/* ブランチからのPR
- [ ] CI/CD グリーン
- [ ] レビュアー承認 1名以上
- [ ] テストカバレッジ 90% 以上
- [ ] コンフリクト解消済み
```

**マージコマンド:**
```bash
# Squash merge を推奨（コミット履歴を整理）
git checkout develop
git merge --squash feature/agent/business-info
git commit -m "feat(agent): Add BusinessInfoAgent with RAG integration"
git push origin develop
```

#### main ブランチへのマージ

```markdown
- [ ] develop ブランチからのPR
- [ ] 本番環境への影響確認済み
- [ ] PM（Cursor）の承認が必須
- [ ] すべてのテストがパス
- [ ] ドキュメント最新化
- [ ] リリースノート作成済み（該当する場合）
```

**マージコマンド:**
```bash
# Merge commit を推奨（履歴を保持）
git checkout main
git merge --no-ff develop
git tag -a v1.2.0 -m "Release v1.2.0: Add BusinessInfoAgent"
git push origin main --tags
```

### 7.3 マージ後のタスク

```markdown
### Claude Code（実装者）

- [ ] マージ通知を確認
- [ ] feature ブランチを削除
- [ ] Plans.md のタスクを「完了」にマーク
- [ ] 次のタスクに着手

### Cursor（PM）

- [ ] マージ完了を確認
- [ ] 本番デプロイの準備（main へのマージの場合）
- [ ] ステークホルダーへの報告（該当する場合）
```

---

## クイックリファレンス

### よく使うコマンド

```bash
# ========================================
# コード品質チェック
# ========================================

# Backend
cd backend

# フォーマット適用
ruff format .

# リント実行
ruff check .

# リント自動修正
ruff check . --fix

# ========================================
# テスト実行
# ========================================

# 単体テスト（詳細出力）
pytest tests/agents/test_{agent_name}.py -v

# カバレッジ付きテスト
pytest tests/agents/test_{agent_name}.py \
  --cov=agents/{agent_name} \
  --cov-report=html

# 全テスト実行
pytest tests/ -v

# 統合テスト
pytest tests/integration/ -v

# ========================================
# Frontend チェック
# ========================================

cd frontend

# リント
pnpm lint

# 型チェック
pnpm typecheck

# ビルド
pnpm build

# ========================================
# Git 操作
# ========================================

# 最新の develop を取り込む
git checkout develop
git pull origin develop
git checkout feature/your-branch
git merge develop

# コンフリクト解消後
git add .
git commit -m "Merge develop into feature/your-branch"
git push origin feature/your-branch
```

### レビュー優先度の早見表

| 優先度 | キーワード | 対応 |
|-------|----------|------|
| **MUST** | セキュリティ、致命的バグ、動作不良 | 必ず修正（マージ条件） |
| **SHOULD** | ベストプラクティス、保守性、品質向上 | 推奨修正（可能な限り） |
| **NICE_TO_HAVE** | 最適化、コメント、変数名 | 任意修正（時間があれば） |

### テストカバレッジ目標

| 対象 | 目標カバレッジ |
|------|--------------|
| **新規エージェント** | 90% 以上 |
| **既存エージェント修正** | 既存以上（最低 85%） |
| **ユーティリティ関数** | 95% 以上 |
| **統合テスト** | 主要フロー 100% |

### 関連ドキュメント

- [2-Agent ワークフロールール](../../.claude/rules/workflow.md)
- [エージェント実装チェックリスト](./AGENT-IMPLEMENTATION-CHECKLIST.md)
- [テスト作成ガイド](../testing/TESTING-GUIDE.md)
- [コントリビューティングガイド](./CONTRIBUTING.md)
- エージェント仕様: `docs/migration/agents/{agent-name}/SPEC.md`
- エージェントテスト: `docs/migration/agents/{agent-name}/TESTING.md`

---

## 変更履歴

| 日付 | バージョン | 変更内容 |
|------|----------|---------|
| 2026-01-13 | 1.0.0 | 初版作成 |
