# エージェント実装チェックリスト

> Engineer Cafe Navigator プロジェクトにおけるエージェント実装時の品質保証チェックリスト

## 目次

- [概要](#概要)
- [1. 実装前チェックリスト](#1-実装前チェックリスト)
- [2. 実装中チェックリスト](#2-実装中チェックリスト)
- [3. 実装後チェックリスト](#3-実装後チェックリスト)
- [4. CI/CD チェック項目](#4-cicd-チェック項目)
- [5. コードレビュー時の確認項目](#5-コードレビュー時の確認項目)
- [クイックリファレンス](#クイックリファレンス)

---

## 概要

このチェックリストは、LangGraph ベースのエージェント実装において、品質を確保し実装漏れを防ぐためのガイドです。

### 対象エージェント

| エージェント | 責務 |
|------------|------|
| RouterAgent | クエリのルーティング、言語検出、リクエストタイプ抽出 |
| BusinessInfoAgent | 営業時間、料金、場所などのビジネス情報 |
| FacilityAgent | 設備、Wi-Fi、地下施設などの施設情報 |
| EventAgent | イベント、カレンダー情報 |
| MemoryAgent | 会話履歴、コンテキスト管理 |
| ClarificationAgent | 曖昧なクエリの明確化 |
| GeneralKnowledgeAgent | スコープ外クエリの処理 |
| SlideAgent | スライド表示制御 |
| VoiceAgent | 音声処理 |
| CharacterControlAgent | キャラクター制御 |

---

## 1. 実装前チェックリスト

### 1.1 要件確認

- [ ] **仕様ドキュメントの確認**
  - `docs/migration/agents/{agent-name}/SPEC.md` を確認
  - 入出力インターフェースを理解
  - 依存関係を把握

- [ ] **既存実装の確認**
  - Mastra 版の既存実装がある場合、ロジックを理解
  - `src/mastra/agents/` 配下の対応エージェントを確認
  - 移行時の差分を明確化

- [ ] **テスト要件の確認**
  - `docs/migration/agents/{agent-name}/TESTING.md` を確認
  - 目標テストカバレッジを把握（通常 90% 以上）
  - パフォーマンス基準を確認

### 1.2 設計確認

- [ ] **エージェント設計**
  - 単一責務原則に従っているか
  - 他エージェントとの境界が明確か
  - ステート管理方針が適切か

- [ ] **依存関係の設計**
  - LLM プロバイダー（OpenRouter）との連携方法
  - RAG システムとの連携方法
  - メモリシステムとの連携方法

- [ ] **エラーハンドリング設計**
  - フォールバック戦略が定義されているか
  - エラー時のユーザーメッセージが適切か
  - リトライ戦略が必要か

### 1.3 開発環境準備

- [ ] **ブランチ作成**
  ```bash
  git checkout develop
  git pull origin develop
  git checkout -b feature/agent/{agent-name}
  ```

- [ ] **依存関係インストール**
  ```bash
  cd backend
  pip install -r requirements.txt
  ```

- [ ] **環境変数設定**
  - `.env` ファイルが最新か確認
  - テスト用環境変数が設定されているか

---

## 2. 実装中チェックリスト

### 2.1 コード品質

- [ ] **型ヒント**
  - すべての関数シグネチャに型ヒントを付与
  - カスタム型は `TypedDict` または `dataclass` で定義
  - `Optional`, `Union`, `Literal` を適切に使用

- [ ] **ドキュメント**
  - クラスに Google スタイルの docstring を記述
  - すべての public メソッドに docstring を記述
  - 複雑なロジックにはインラインコメントを追加

- [ ] **コーディング規約**
  - PEP 8 準拠（Ruff でフォーマット）
  - 関数は 50 行以内を目安
  - ネストは 3 レベル以内を目安

### 2.2 エージェント実装パターン

- [ ] **基本構造**
  ```python
  class YourAgent:
      """エージェントの説明（Google スタイル docstring）"""

      def __init__(self, provider: OpenRouterProvider | None = None) -> None:
          """初期化"""
          self.provider = provider or OpenRouterProvider()

      async def process(
          self,
          query: str,
          session_id: str,
          language: str = "ja",
          context: dict[str, Any] | None = None,
      ) -> AgentResponse:
          """メイン処理メソッド"""
          pass
  ```

- [ ] **レスポンス構造**
  ```python
  @dataclass
  class AgentResponse:
      answer: str
      emotion: str
      metadata: dict[str, Any]
  ```

- [ ] **LLM 呼び出しパターン**
  - プロンプトは定数として定義
  - トークン使用量を追跡
  - タイムアウト設定を実装

### 2.3 エラーハンドリング

- [ ] **例外処理**
  - カスタム例外クラスを定義（必要に応じて）
  - 具体的な例外をキャッチ（bare `except` を避ける）
  - エラーログを適切に出力

- [ ] **フォールバック**
  - API 失敗時のフォールバックメッセージ
  - タイムアウト時の処理
  - 無効な入力に対する処理

```python
try:
    result = await self.provider.generate(prompt)
except ProviderTimeoutError:
    logger.warning(f"LLM timeout for query: {query[:50]}...")
    return self._fallback_response(query, language)
except ProviderError as e:
    logger.error(f"LLM error: {e}")
    return self._error_response(query, language, str(e))
```

### 2.4 パフォーマンス考慮

- [ ] **非同期処理**
  - I/O バウンド処理には `async/await` を使用
  - 並列実行可能な処理は `asyncio.gather()` を使用

- [ ] **キャッシュ**
  - 頻繁に使用するデータはキャッシュを検討
  - TTL（有効期限）を適切に設定

- [ ] **メモリ効率**
  - 大きなデータには generator を使用
  - 不要なオブジェクトの参照を解放

---

## 3. 実装後チェックリスト

### 3.1 テスト作成

- [ ] **テストファイル作成**
  - `backend/tests/agents/test_{agent_name}.py` を作成
  - テンプレート（`backend/tests/templates/test_agent_template.py`）を参考に

- [ ] **テストカテゴリ**
  - [ ] 初期化テスト (`test_initialization_*`)
  - [ ] 基本機能テスト (`test_basic_*`)
  - [ ] エラーハンドリングテスト (`test_error_*`)
  - [ ] エッジケーステスト (`test_edge_case_*`)
  - [ ] 統合テスト (`test_integration_*`)

- [ ] **モック使用**
  - 外部 API 呼び出しはモック化
  - `backend/tests/utils/mock_helpers.py` のヘルパーを使用

```python
from tests.utils.mock_helpers import create_mock_openrouter_provider

def test_basic_query(mock_openrouter_provider):
    agent = YourAgent(provider=mock_openrouter_provider)
    result = await agent.process("テストクエリ", "test-session")
    assert result.answer
```

### 3.2 テスト実行

- [ ] **ローカルテスト実行**
  ```bash
  cd backend
  pytest tests/agents/test_{agent_name}.py -v
  ```

- [ ] **カバレッジ確認**
  ```bash
  pytest tests/agents/test_{agent_name}.py --cov=agents/{agent_name} --cov-report=html
  ```
  - 目標: 90% 以上のカバレッジ

- [ ] **パフォーマンステスト**
  - 平均レスポンス時間: 100ms 以下（ルーティング）
  - 最大レスポンス時間: 200ms 以下（ルーティング）
  - 同時リクエスト処理: 10 件/500ms 以内

### 3.3 ワークフロー統合

- [ ] **ワークフロー定義の更新**
  - `backend/workflows/main_workflow.py` にノードを追加
  - エッジ（遷移条件）を定義
  - 状態スキーマを更新

- [ ] **統合テスト**
  ```bash
  pytest tests/integration/test_workflow.py -v
  ```

### 3.4 ドキュメント更新

- [ ] **仕様ドキュメント**
  - `docs/migration/agents/{agent-name}/SPEC.md` を最新化
  - 実装との差分がないか確認

- [ ] **テストドキュメント**
  - `docs/migration/agents/{agent-name}/TESTING.md` を最新化
  - テスト結果を記録

- [ ] **API ドキュメント**
  - 入出力インターフェースを記載
  - 使用例を追加

---

## 4. CI/CD チェック項目

### 4.1 コード品質チェック

実装完了後、以下のコマンドをすべて実行し、エラーがないことを確認します。

```bash
# Backend（Python）
cd backend

# フォーマットチェック
ruff format --check .

# リントチェック
ruff check .

# 型チェック（該当モジュールのみ）
mypy agents/{agent_name}.py --ignore-missing-imports
```

### 4.2 テスト実行

```bash
# 単体テスト
pytest tests/agents/test_{agent_name}.py -v

# 統合テスト
pytest tests/integration/ -v

# 全テスト（CI と同等）
pytest tests/ -v --tb=short
```

### 4.3 Frontend 影響確認（該当する場合）

```bash
# Frontend
cd frontend

# リントチェック
pnpm lint

# 型チェック
pnpm typecheck

# ビルドチェック
pnpm build
```

### 4.4 プルリクエスト前チェック

- [ ] すべてのテストがパス
- [ ] リントエラーがゼロ
- [ ] 型チェックエラーがゼロ
- [ ] ビルドが成功
- [ ] カバレッジが目標値以上

---

## 5. コードレビュー時の確認項目

### 5.1 設計・アーキテクチャ

| 確認項目 | OK |
|---------|-----|
| 単一責務原則に従っているか | [ ] |
| 他エージェントとの境界が明確か | [ ] |
| 依存関係が適切か（循環依存がないか） | [ ] |
| 拡張性を考慮した設計か | [ ] |

### 5.2 コード品質

| 確認項目 | OK |
|---------|-----|
| 型ヒントが完全か | [ ] |
| docstring が適切か | [ ] |
| 関数サイズが適切か（50 行以内目安） | [ ] |
| ネストが深すぎないか（3 レベル以内） | [ ] |
| マジックナンバーがないか | [ ] |

### 5.3 エラーハンドリング

| 確認項目 | OK |
|---------|-----|
| 例外処理が適切か | [ ] |
| フォールバックが実装されているか | [ ] |
| エラーメッセージが適切か | [ ] |
| ログ出力が適切か | [ ] |

### 5.4 セキュリティ

| 確認項目 | OK |
|---------|-----|
| 機密情報がハードコードされていないか | [ ] |
| 入力値のバリデーションがあるか | [ ] |
| SQL インジェクション対策がされているか | [ ] |
| XSS 対策がされているか（該当する場合） | [ ] |

### 5.5 テスト

| 確認項目 | OK |
|---------|-----|
| テストカバレッジが 90% 以上か | [ ] |
| 正常系テストがあるか | [ ] |
| 異常系テストがあるか | [ ] |
| エッジケーステストがあるか | [ ] |
| モックが適切に使用されているか | [ ] |

### 5.6 ドキュメント

| 確認項目 | OK |
|---------|-----|
| SPEC.md が最新か | [ ] |
| TESTING.md が最新か | [ ] |
| README 更新が必要か（該当する場合） | [ ] |

### 5.7 パフォーマンス

| 確認項目 | OK |
|---------|-----|
| 非同期処理が適切か | [ ] |
| 不要な API 呼び出しがないか | [ ] |
| キャッシュが適切に使用されているか | [ ] |
| メモリリークの可能性がないか | [ ] |

---

## クイックリファレンス

### よく使うコマンド

```bash
# テスト実行（詳細出力）
pytest tests/agents/test_{agent_name}.py -v

# カバレッジ付きテスト
pytest tests/agents/test_{agent_name}.py --cov=agents/{agent_name} --cov-report=html

# フォーマット適用
ruff format .

# リント自動修正
ruff check . --fix

# 型チェック
mypy agents/{agent_name}.py --ignore-missing-imports
```

### ディレクトリ構造

```
backend/
├── agents/
│   └── {agent_name}.py       # エージェント実装
├── tests/
│   ├── agents/
│   │   └── test_{agent_name}.py  # 単体テスト
│   ├── integration/
│   │   └── test_workflow.py      # 統合テスト
│   ├── templates/
│   │   └── test_agent_template.py  # テストテンプレート
│   └── utils/
│       ├── mock_helpers.py       # モックヘルパー
│       └── test_helpers.py       # テストヘルパー
└── workflows/
    └── main_workflow.py          # ワークフロー定義
```

### 参考ドキュメント

- [テスト作成ガイド](../testing/TESTING-GUIDE.md)
- [コントリビューティングガイド](./CONTRIBUTING.md)
- [2-Agent ワークフロールール](../../.claude/rules/workflow.md)
- エージェント仕様: `docs/migration/agents/{agent-name}/SPEC.md`
- エージェントテスト: `docs/migration/agents/{agent-name}/TESTING.md`

---

## 変更履歴

| 日付 | バージョン | 変更内容 |
|------|----------|---------|
| 2026-01-13 | 1.0.0 | 初版作成 |
