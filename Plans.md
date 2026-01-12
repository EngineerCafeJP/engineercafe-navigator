# Plans.md - Engineer Cafe Navigator

> 最終更新: 2025-01-12
> モード: 2-Agent (Cursor PM + Claude Code Worker)

---

## 現在のステータス

| 項目 | 状態 |
|------|------|
| **CI/CD** | ✅ グリーン (最終実行: 2025-01-12) |
| **オープン PR** | PR #20 (RouterAgent - レビュー待ち) |
| **完了したフェーズ** | フェーズ0.5 (OpenRouter API徹底整備), フェーズ0.6 (プロジェクト構造リファクタリング), フェーズ1.1-1.4 (RouterAgent, BusinessInfoAgent, EventAgent, SlideAgent), フェーズ2.1 (MemoryAgent骨組み実装) |
| **次のフェーズ** | フェーズ6 (pytestとLangGraphEvaluate基本実装) |
| **ベースブランチ** | develop |

---

## CI/CD チェックリスト

Claude Code は PR 作成・更新時に以下を確認:

- [ ] `pnpm lint` (frontend) - ESLint
- [ ] `pnpm typecheck` (frontend) - TypeScript
- [ ] `pnpm build` (frontend) - Next.js ビルド
- [ ] `ruff check .` (backend) - Python リンター
- [ ] `black --check .` (backend) - Python フォーマット

**失敗時のアクション:**
1. エラーログを確認
2. 自動修正を試行
3. 修正不可の場合は PM に報告

---

## フェーズ 0: ハーネスセットアップ `cc:WIP`

- [x] AGENTS.md 作成 `cc:DONE`
- [x] Plans.md 作成 `cc:DONE`
- [ ] .cursor/commands/ 作成 `cc:TODO`
- [ ] .claude/rules/ 作成 `cc:TODO`
- [ ] .claude/memory/ 初期化 `cc:TODO`
- [ ] .claude/settings.json 更新 `cc:TODO`
- [ ] 環境診断実行 `cc:TODO`
- [ ] CI/CD グリーン確認 `cc:TODO`

### PM → Claude Code 依頼 (2025-12-27) `pm:依頼中`

- [ ] `.gitignore` を allowlist 方式に整理（`.cursor/commands/` と `.claude/{rules,settings.json,memory/{decisions,patterns}.md}` は追跡、それ以外のローカル状態/ログ/ハーネスは ignore）
- [ ] 共有ファイルを追跡対象として `git add`（`AGENTS.md`, `Plans.md`, `.cursor/commands/*`, `.claude/rules/*`, `.claude/memory/{decisions,patterns}.md`, `.claude/settings.json`）
- [ ] `feature/openrouter-infrastructure` ブランチへ取り込み（merge/cherry-pick）→ 既存 PR を更新
- [ ] OpenRouter のモデル定義を **2025/12 最新**へ更新（`backend/llm/models.py` など、古いモデルIDの整理・置換）

---

## フェーズ 0.5: OpenRouter API徹底整備 `cc:DONE`

> 担当: テリスケ（統括）
> 完了日: 2025-01-12

### 0.5.1 OpenRouter API基盤整備
- [x] `langchain-google-genai`パッケージ削除（requirements.txt, pyproject.toml） `cc:DONE`
- [x] `backend/README.md`のGemini API直接使用記述削除 `cc:DONE`
- [x] OpenRouter API使用チェックリスト作成 `cc:DONE`
- [x] OpenRouter API使用ベストプラクティスドキュメント作成 `cc:DONE`

**完了条件**:
- [x] `langchain-google-genai`が依存関係から削除されている
- [x] ドキュメントからGemini直接APIの記述が削除されている
- [x] OpenRouter API使用のチェックリストが作成されている
- [x] CI/CDがグリーン

**成果物**:
- `docs/migration/agents/openrouter-checklist.md` - OpenRouter API使用チェックリスト
- `docs/migration/agents/openrouter-best-practices.md` - OpenRouter APIベストプラクティス
- `backend/requirements.txt` - langchain-google-genai削除済み
- `backend/pyproject.toml` - langchain-google-genai削除済み
- `backend/README.md` - OpenRouter API使用方法更新済み

## フェーズ 0.6: プロジェクト構造リファクタリング `cc:DONE` `pm:確認済`

> 依頼日時: 2025-01-12  
> 完了日時: 2025-01-12  
> 目的: プロジェクト構造を整理し、入れ子構造やルート直下の散在を解消

### 0.6.1 不要なディレクトリの削除
- [x] `agents/` ディレクトリ削除（ルートレベル、空の__init__.pyのみ） `cc:DONE`
- [x] `backend/backend/` ディレクトリ削除（空の__init__.pyのみ） `cc:DONE`
- [x] `backend/docs/` の重複確認と整理 `cc:DONE`

### 0.6.2 ルートディレクトリのドキュメント整理
- [x] `CHANGELOG.md` → `docs/CHANGELOG.md` に移動 `cc:DONE`
- [x] `CLAUDE.md` → `docs/development/CLAUDE.md` に移動 `cc:DONE`
- [x] `CONTRIBUTING.md` → `docs/development/CONTRIBUTING.md` に移動 `cc:DONE`
- [x] `DEVELOPER-GUIDE.md` → `docs/development/DEVELOPER-GUIDE.md` に移動 `cc:DONE`
- [x] `unified-response-demo.md` → `docs/archive/` に移動 `cc:DONE`
- [x] `AGENTS.md` → `docs/development/AGENTS.md` に移動 `cc:DONE`
- [x] `Plans.md` → **ルートに保持**（移動しない） `cc:DONE`

### 0.6.3 docs/ディレクトリの整理
- [x] `docs/archive/` に古いドキュメントを移動 `cc:DONE`
- [x] `docs/api/` ディレクトリを作成し、API関連ドキュメントを移動 `cc:DONE`
- [x] `docs/architecture/` にアーキテクチャ関連ドキュメントを移動 `cc:DONE`
- [x] `docs/development/` に開発ガイドを移動 `cc:DONE`
- [x] `docs/blog/` にブログ記事を移動 `cc:DONE`

### 0.6.4 プロジェクト構造の見直しとパス修正
- [x] `docs/development/repo-structure.md` を更新（新しい構造を反映） `cc:DONE`
- [x] すべてのドキュメント内のパス参照を修正 `cc:DONE`
- [x] README.mdのパス参照を更新 `cc:DONE`
- [x] CI/CD設定ファイルのパス参照を確認・修正 `cc:DONE`

### 0.6.5 インポートパスと参照の確認
- [x] コード内のドキュメント参照パスを確認 `cc:DONE`
- [x] テストファイルのパス参照を確認 `cc:DONE`
- [x] 設定ファイルのパス参照を確認 `cc:DONE`

**完了条件**:
- [x] 不要なディレクトリが削除されている `cc:DONE`
- [x] ルートディレクトリが整理されている（README.md, Plans.md以外はdocs/に移動） `cc:DONE`
- [x] docs/ディレクトリがカテゴリ別に整理されている `cc:DONE`
- [x] すべてのパス参照が更新されている `cc:DONE`
- [x] CI/CDがグリーン `cc:DONE`

**ブランチ**: `refactor/project-structure-cleanup`  
**PR**: #22  
**マージ方法**: **PR作成 → CI/CDグリーン確認 → developに直接マージ**

### 0.6.6 追加リファクタリング（追加タスク） `cc:DONE` `pm:確認済`
> 依頼日時: 2025-01-12  
> 完了日時: 2025-01-12  
> 目的: モノレポ構造の徹底的な整理

- [x] ルートの`supabase/`ディレクトリ削除（空で、実際の設定は`frontend/supabase/`にある） `cc:DONE`
- [x] ルートの`package-lock.json`の削除（pnpm使用のため不要） `cc:DONE`
- [x] `firebase-debug.log`の削除 `cc:DONE`
- [x] ルートの`package.json`の確認（workspace設定として適切） `cc:DONE`
- [x] **`frontend/supabase/`を`backend/supabase/`に移動**（最重要） `cc:DONE`
  - 理由: バックエンド（LangGraph）でRAG、メモリエージェントがSupabaseを使用
  - マイグレーションは共有リソースなので、バックエンドに配置すべき
  - フロントエンドは環境変数のみでSupabaseクライアントに接続（設定ファイル不要）
- [x] `.gitignore`の更新（`frontend/supabase/`参照を削除、`backend/supabase/`追加） `cc:DONE`
- [x] `docs/development/repo-structure.md`を更新（最終構造を反映） `cc:DONE`

**完了条件**:
- [x] 不要なディレクトリ・ファイルが削除されている `cc:DONE`
- [x] モノレポ構造が適切に整理されている `cc:DONE`
- [x] すべてのパス参照が更新されている `cc:DONE`
- [x] CI/CDがグリーン `cc:DONE`

**ブランチ**: `refactor/project-structure-cleanup`  
**PR**: #22  
**マージ方法**: **PR作成 → CI/CDグリーン確認 → developに直接マージ**

---

## 📋 次の実装計画（優先順位順）

### 最優先: フェーズ6 pytestとLangGraphEvaluate基本実装

**目的**: テスト基盤を構築し、他のエンジニアがテストを書きやすくする

**理由**:
- 他のエンジニアが担当するエージェントのテストを書きやすくするため
- CI/CDでのテスト実行を確実にするため

**推定期間**: 1週間

---

## フェーズ 1: LangGraph 移行 - コア機能 `cc:WIP`

> 担当: テリスケ, Natsumi, けいてぃー

### 1.1 RouterAgent 移行 `cc:DONE` `pm:確認済`

> 依頼日時: 2025-01-12  
> レビュー日時: 2025-01-12

- [x] LanguageProcessor実装 `cc:DONE`
- [x] QueryClassifier実装 `cc:DONE`
- [x] RouterAgent本体実装（OpenRouter API使用） `cc:DONE`
- [x] OCR結果処理ロジック実装 `cc:DONE`
- [x] ClarificationAgent連携ロジック実装 `cc:DONE`
- [x] メモリシステム未実装時でも動作する実装 `cc:DONE`
- [x] 単体テスト実装 `cc:DONE`
- [x] **PR作成してYukitoLynにレビュー依頼** `cc:DONE` (PR #20)
- [x] **フォールバック戦略強化（ネットワークエラー時対応）** `cc:DONE` `pm:確認済`
- [x] **環境変数テンプレート更新（.env.example）** `cc:DONE` `pm:確認済`
- [x] **ドキュメント更新（フォールバック戦略説明）** `cc:DONE` `pm:確認済`

**ブランチ**: `feature/router-agent-implementation`  
**マージ方法**: **必ずPRを作成してレビュー（YukitoLynにレビュー依頼）**  
**PR**: #20 (レビュー待ち)

### 1.2 BusinessInfoAgent 移行 `cc:DONE` `pm:確認済`
> 依頼日時: 2025-01-12  
> 完了日時: 2025-01-12

- [x] Enhanced RAG 移植 `cc:DONE`
- [x] 営業時間/料金/場所クエリ処理 `cc:DONE`
- [x] main_workflow.pyの_business_info_node()を実装 `cc:DONE`
- [x] OpenRouter API使用を確認（OpenRouterProviderとget_model_config("facility_info")を使用） `cc:DONE`
- [x] テストケース作成 `cc:DONE`
- [x] CI/CDがグリーン `cc:DONE`
- [x] PRを作成してCI/CD確認後、developにマージ `cc:DONE`
- [x] PR #20との整合性確保（ディレクトリ構造・インポートパス統一） `cc:DONE` `pm:確認済`

**ブランチ**: `feature/business-info-event-slide-agents`  
**PR**: #21  
**マージ方法**: **PR作成 → CI/CDグリーン確認 → developに直接マージ**

### 1.3 EventAgent 移行 `cc:DONE` `pm:確認済`
> 依頼日時: 2025-01-12  
> 完了日時: 2025-01-12

- [x] Google Calendar API連携（期間抽出ロジック含む） `cc:DONE`
- [x] イベント情報取得・整形処理 `cc:DONE`
- [x] main_workflow.pyの_event_node()を実装 `cc:DONE`
- [x] OpenRouter API使用を確認（OpenRouterProviderとget_model_config("event_info")を使用） `cc:DONE`
- [x] テストケース作成 `cc:DONE`
- [x] CI/CDがグリーン `cc:DONE`
- [x] PRを作成してCI/CD確認後、developにマージ `cc:DONE`

**ブランチ**: `feature/business-info-event-slide-agents`（BusinessInfoAgentと同一ブランチ）

### 1.4 SlideAgent 移行 `cc:DONE` `pm:確認済`
> 依頼日時: 2025-01-12  
> 完了日時: 2025-01-12

- [x] ナレーションJSON読み込み機能 `cc:DONE`
- [x] スライドナレーション生成 `cc:DONE`
- [x] スライドナビゲーション（次へ/前へ/特定スライド） `cc:DONE`
- [x] スライド質問応答 `cc:DONE`
- [x] main_workflow.pyの_slide_node()を実装（必要に応じて） `cc:DONE`
- [x] OpenRouter API使用を確認（OpenRouterProviderとget_model_config("qa_response")を使用） `cc:DONE`
- [x] テストケース作成 `cc:DONE`
- [x] CI/CDがグリーン `cc:DONE`
- [x] PRを作成してCI/CD確認後、developにマージ `cc:DONE`
- [x] **スライドファイルの配置（backend/slides/）** `cc:DONE`

**ブランチ**: `feature/business-info-event-slide-agents`（BusinessInfoAgentと同一ブランチ）

### 1.5 FacilityAgent 移行 `cc:TODO`
- [ ] 地下施設キーワード検出 `cc:TODO`
- [ ] 設備情報クエリ処理 `cc:TODO`
- [ ] テストケース作成 `cc:TODO`

---

## フェーズ 2: LangGraph 移行 - 会話機能 `cc:WIP`

> 担当: テリスケ（骨組み）, takegg0311・YukitoLyn（完全実装）, Chie, Jun

### 2.1 MemoryAgent 骨組み実装 `cc:DONE` `pm:確認済`

> 依頼日時: 2025-01-12
> 完了日時: 2025-01-12
> 目的: 専門エンジニア（takegg0311・YukitoLyn）がMemoryAgentを実装するための骨組みとドキュメント

**タスク**:
- [x] `backend/utils/memory_interface.py`を作成 - Protocolインターフェース定義 `cc:DONE`
- [x] `backend/utils/memory_helper.py`を作成 - 暫定実装（Supabase + Supabase Storage） `cc:DONE`
- [x] `backend/agents/memory_agent.py`を作成 - 骨組みのみ（TODOコメント付き） `cc:DONE`
- [x] `backend/workflows/main_workflow.py`の`_memory_node()`を骨組みに置き換え `cc:DONE`
- [x] Checkpointer基盤実装（`langgraph-checkpoint-postgres`統合） `cc:DONE`
- [x] 専門エンジニア向けの実装ガイドを作成 `cc:DONE`
- [x] 単体テスト作成（骨組み動作確認） `cc:DONE`

**完了条件**:
- [x] `MemorySystemInterface` Protocolが定義されている
- [x] 暫定実装（`SimplifiedMemoryHelper`）が動作する
- [x] MemoryAgentの骨組みが作成されている
- [x] Checkpointer基盤が実装されている
- [x] 専門エンジニア向けの実装ガイドが作成されている
- [x] RouterAgentがメモリシステムとオプショナルに連携できる
- [x] CI/CDがグリーン（Ruff, Black, Pytest 全てパス）

**成果物**:
- `backend/utils/memory_interface.py` - MemorySystemInterface Protocol
- `backend/utils/memory_helper.py` - SimplifiedMemoryHelper暫定実装
- `backend/utils/checkpointer.py` - Checkpointer基盤
- `backend/agents/memory_agent.py` - MemoryAgent骨組み
- `backend/workflows/main_workflow.py` - _memory_node()更新
- `docs/migration/agents/memory-agent/IMPLEMENTATION-GUIDE.md` - 完全実装ガイド
- `backend/tests/test_memory_skeleton.py` - 骨組みテスト（17テスト全てパス）

**ブランチ**: `feature/memory-agent-skeleton`  
**PR**: #23  
**マージ方法**: **直接developブランチにマージ（PR不要）**

**注意**: 完全実装は専門エンジニア（takegg0311・YukitoLyn）が担当。骨組み実装のみ完了。

### 2.2 ClarificationAgent 移行
- [ ] 曖昧さ検出ロジック `cc:TODO`
- [ ] 選択肢生成 `cc:TODO`
- [ ] テストケース作成 `cc:TODO`

### 2.3 LanguageClassifier 移行
- [ ] 言語検出ロジック `cc:TODO`
- [ ] テストケース作成 `cc:TODO`

---

## フェーズ 3: LangGraph 移行 - 出力機能 `cc:TODO`

> 担当: Chie, takegg0311, テリスケ

### 3.1 VoiceAgent 移行
- [ ] Google Cloud STT 連携 `cc:TODO`
- [ ] Google Cloud TTS 連携 `cc:TODO`
- [ ] STT 補正システム移植 `cc:TODO`
- [ ] 感情タグ処理 `cc:TODO`

### 3.2 CharacterControlAgent 移行
- [ ] 感情→表情マッピング `cc:TODO`
- [ ] VRM 制御コマンド生成 `cc:TODO`

### 3.3 SlideAgent 移行 `cc:DONE` `pm:確認済`

> 完了日時: 2025-01-12

- [x] ナレーションデータ読み込み `cc:DONE`
- [x] スライドナビゲーション `cc:DONE`

**ステータス**: フェーズ1.4で完了

---

## フェーズ 6: テスト基盤整備 `cc:TODO` `pm:次フェーズ`

> 担当: テリスケ
> 目的: テスト基盤を構築し、他のエンジニアがテストを書きやすくする

### 6.1 pytest基本設定とフィクスチャ `cc:TODO`
- [ ] `backend/tests/conftest.py`を作成 - pytest設定とフィクスチャ `cc:TODO`
- [ ] テストフィクスチャ（OpenRouterProvider, モデル設定等） `cc:TODO`
- [ ] 非同期テスト設定（pytest-asyncio） `cc:TODO`

### 6.2 テストユーティリティ作成 `cc:TODO`
- [ ] `backend/tests/utils/test_helpers.py`作成 - テストヘルパー関数 `cc:TODO`
- [ ] `backend/tests/utils/mock_helpers.py`作成 - モック作成ユーティリティ `cc:TODO`
- [ ] `backend/tests/utils/assertion_helpers.py`作成 - カスタムアサート関数 `cc:TODO`

### 6.3 LangGraphEvaluate基本セットアップ `cc:TODO`
- [ ] `backend/tests/utils/langgraph_evaluate_setup.py`作成 `cc:TODO`
- [ ] LangGraphEvaluator基本設定 `cc:TODO`
- [ ] 評価メトリクス定義 `cc:TODO`

### 6.4 エージェントテストテンプレート `cc:TODO`
- [ ] `backend/tests/templates/test_agent_template.py`作成 `cc:TODO`
- [ ] 基本的な機能テストのテンプレート `cc:TODO`
- [ ] エラーハンドリングテストのテンプレート `cc:TODO`
- [ ] 非同期処理テストのテンプレート `cc:TODO`

### 6.5 テスト作成ガイド `cc:TODO`
- [ ] `docs/testing/TESTING-GUIDE.md`作成 - テスト作成ガイド `cc:TODO`
- [ ] pytestの基本的な使い方 `cc:TODO`
- [ ] フィクスチャとモックの使い方 `cc:TODO`
- [ ] LangGraphEvaluateの使い方 `cc:TODO`
- [ ] テストテンプレートの使い方 `cc:TODO`

**完了条件**:
- [ ] `backend/tests/conftest.py`が作成されている
- [ ] テストユーティリティが作成されている
- [ ] LangGraphEvaluateが基本セットアップされている
- [ ] エージェントテストテンプレートが作成されている
- [ ] テスト作成ガイドが作成されている
- [ ] 既存テストが全て動作する
- [ ] CI/CDがグリーン

**ブランチ**: `feature/test-infrastructure`
**マージ方法**: **PRを作成してCI/CDグリーン確認 → developに直接マージ**

---

## フェーズ 4: 新機能 `cc:TODO`

> 担当: けいてぃー, たけがわ

### 4.1 OCRAgent 新規実装 (LangGraph のみ)
- [ ] 技術選定完了 (YOLO/Google Vision) `cc:TODO`
- [ ] 番号認識実装 `cc:TODO`
- [ ] QR コード認識 `cc:TODO`
- [ ] 表情認識実装 `cc:TODO`
- [ ] プライバシーポリシー確認 `cc:TODO`

### 4.2 EventAgent 拡張 `cc:TODO`

> フェーズ1.3で骨組み実装済み。以下は拡張機能。

- [ ] Connpass API 連携（完全実装） `cc:TODO`
- [ ] Google Calendar API 連携（完全実装） `cc:TODO`

### 4.3 GeneralKnowledgeAgent 移行
- [ ] Web 検索機能 `cc:TODO`

---

## オープン PR 一覧

| # | タイトル | ブランチ | ステータス |
|---|----------|----------|-----------|
| 13 | OCRAgent YOLO/ML アプローチ | docs/ocr-agent-yolo-update | OPEN |
| 12 | OpenRouter LLM インフラ | feature/openrouter-infrastructure | OPEN |
| 11 | VoiceAgent MIGRATION-GUIDE | docs/voice-agent | OPEN |
| 9 | ClarificationAgent ドキュメント | docs/clarification-agent | OPEN |
| 7 | テリスケ担当エージェントドキュメント | docs/agent-documentation-enhancement | OPEN |

---

## 決定事項 (SSOT)

→ `.claude/memory/decisions.md` 参照

---

## メモ

- **Tailwind CSS v3.4.17 必須** - v4 は使用禁止
- **OpenAI Embeddings 1536 次元** - 768 次元は非推奨
- **モバイル AudioContext** - ユーザー操作が必要
