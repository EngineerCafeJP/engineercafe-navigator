# Plans.md - Engineer Cafe Navigator

> 最終更新: 2025-01-13
> モード: 2-Agent (Cursor PM + Claude Code Worker)

---

## 現在のステータス

| 項目 | 状態 |
|------|------|
| **CI/CD** | ✅ グリーン (最終実行: 2025-01-13) |
| **オープン PR** | PR #25 (バックエンド統合 - Draft), PR #20 (RouterAgent実装 - コンフリクト解決完了、push待ち) |
| **完了したフェーズ** | 0.5 (OpenRouter), 0.6 (構造整理), 1.1-1.5 (Agent移行), 2.1 (Memory骨組み), 6 (テスト基盤) |
| **次のフェーズ** | 1.6 (RouterAgent統合完了確認), 7.5 (バックエンド完全実装), 8 (開発環境整備), 9 (ドキュメント更新) |
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

## 📋 次の実装計画（優先順位順）

### 最優先: フェーズ7.5 バックエンド完全実装（フロントエンド統合）

**目的**: フロントエンドのAIロジックを完全にバックエンド（LangGraph）に移行し、UIを最適化

**推定期間**: 2-3週間

**タスク**:
1. バックエンドAPIの完全実装
   - 音声処理ロジック実装 (STT/TTS)
   - スライド制御ロジック実装
   - キャラクター制御ロジック実装
2. フロントエンドの最適化
   - 残存するMastraエージェントのクライアントサイド実行を完全に削除
   - すべてのAPI Routesをバックエンドプロキシに変更
   - UI/UXの最適化

### 次優先: フェーズ8 開発環境整備

**目的**: Docker整備とmise/makeを使ったモノレポベストプラクティスの実装

**推定期間**: 1-2週間

**タスク**:
1. Docker環境の整備
   - Dockerfile作成（backend, frontend）
   - docker-compose.yml作成
   - ローカル開発環境の構築
2. mise/makeの統合
   - `.mise.toml`作成
   - `Makefile`作成
   - モノレポ操作コマンドの統合
3. ローカル動作確認環境
   - エンドツーエンドテスト環境
   - 開発ワークフローの最適化

### その後: フェーズ9 ドキュメント更新

**目的**: 大幅に変わったプロジェクト構造に沿ってドキュメント更新・パス修正

**推定期間**: 1週間

**タスク**:
1. README.mdの更新
2. 開発ガイドの更新
3. APIドキュメントの更新
4. ドキュメント内のパス修正
5. アーキテクチャドキュメントの更新

### その他: フェーズ2.2-2.3 会話機能完成

**目的**: ClarificationAgentとLanguageClassifierを実装

**推定期間**: 1週間

---

## フェーズ 1: LangGraph 移行 - コア機能 `cc:WIP`

> 担当: テリスケ, Natsumi, けいてぃー

### 1.5 FacilityAgent 移行 `cc:DONE` `pm:確認済`
- [x] FacilityAgentクラス実装 (wifi/facility/basement requestType対応) `cc:DONE`
- [x] 地下施設キーワード検出ロジック実装 `cc:DONE`
- [x] クエリ拡張ロジック実装 (requestType別) `cc:DONE`
- [x] Enhanced RAG統合 `cc:DONE`
- [x] ワークフロー統合 (main_workflow.py) `cc:DONE`
- [x] テストケース作成 (16テスト全PASS) `cc:DONE`
- [x] CI/CD検証 (Ruff/Black/Pytest) `cc:DONE`

**完了日**: 2025-01-12  
**ブランチ**: `feature/facility-agent`  
**PR**: #26 (✅ マージ済み)

---

### 1.6 RouterAgent統合とエージェント連携検証 `cc:DONE` `pm:確認済`

**目的**: RouterAgent実装（PR #20）のコンフリクト解決とワークフロー統合

**完了日**: 2025-01-13

#### 1.6.1 PR #24（テスト基盤整備）レビュー・マージ `cc:DONE` `pm:確認済`
- [x] PR #24をレビュー `cc:DONE`
- [x] テスト基盤の内容を確認 `cc:DONE`
- [x] CI/CD確認（すべてグリーン） `cc:DONE`
- [x] developブランチにマージ `cc:DONE`

#### 1.6.2 SlideAgentバグ修正 `cc:DONE` `pm:確認済`
- [x] ナレーションファイルパス解決バグを修正 `cc:DONE`
- [x] `__file__`ベースの絶対パスで堅牢なパス解決実装 `cc:DONE`
- [x] SlideAgentテスト 15/15 全通過を達成 `cc:DONE`

#### 1.6.3 RouterAgent統合テスト実装 `cc:DONE` `pm:確認済`
- [x] MainWorkflowとRouterAgentの統合テスト11ケースを実装 `cc:DONE`
- [x] feature/router-agent-implementationブランチで11/11全通過を確認 `cc:DONE`

#### 1.6.4 PR #20（RouterAgent実装）コンフリクト解決 `cc:DONE` `pm:確認済`
- [x] developブランチをマージ `cc:DONE`
- [x] 5つのファイルのコンフリクト解決 `cc:DONE`
  - [x] `backend/utils/__init__.py` - RouterAgent utilities追加 `cc:DONE`
  - [x] `backend/tests/utils/__init__.py` - docstring統一 `cc:DONE`
  - [x] `backend/agents/__init__.py` - 全エージェントのexport統合 `cc:DONE`
  - [x] `backend/README.md` - OpenRouter API説明を統一 `cc:DONE`
  - [x] `Plans.md` - 完了済みフェーズをアーカイブ参照に整理 `cc:DONE`
- [x] `main_workflow.py`の`_router_node()`をRouterAgent実装で置き換え `cc:DONE`
- [x] テンプレートファイルのリネームとテスト修正 `cc:DONE`
- [x] Black自動フォーマット適用 `cc:DONE`
- [x] 142/142テスト PASS `cc:DONE`
- [x] CI/CD確認（Ruff/Black/Pytest すべてグリーン） `cc:DONE`

**コミット**:
- `f6031d4c` - Merge branch 'develop' into feature/router-agent-implementation
- `d4eb8e55` - fix: developマージ後のテスト修正

**次のステップ**: PR #20ブランチをpushしてPRを更新、またはレビュー依頼

---

## フェーズ 8: 開発環境整備 `cc:TODO`

> 担当: Claude Code
> 目的: Docker整備とmise/makeを使ったモノレポベストプラクティスの実装

### 8.1 Docker環境の整備 `cc:TODO`
- [ ] `backend/Dockerfile`作成 `cc:TODO`
- [ ] `frontend/Dockerfile`作成 `cc:TODO`
- [ ] `docker-compose.yml`作成（ルートディレクトリ） `cc:TODO`
- [ ] `.dockerignore`作成 `cc:TODO`
- [ ] ローカル開発環境の構築 `cc:TODO`
- [ ] 環境変数の管理（docker-compose.yml） `cc:TODO`

### 8.2 mise/makeの統合 `cc:TODO`
- [ ] `.mise.toml`作成（プロジェクトルート） `cc:TODO`
  - [ ] Python 3.11/3.12の設定 `cc:TODO`
  - [ ] Node.js 20.xの設定 `cc:TODO`
  - [ ] 必要なツールの設定 `cc:TODO`
- [ ] `Makefile`作成（プロジェクトルート） `cc:TODO`
  - [ ] `make setup` - 初期セットアップ `cc:TODO`
  - [ ] `make install` - 依存関係インストール `cc:TODO`
  - [ ] `make test` - テスト実行（backend + frontend） `cc:TODO`
  - [ ] `make lint` - リンター実行 `cc:TODO`
  - [ ] `make dev` - 開発サーバー起動 `cc:TODO`
  - [ ] `make build` - ビルド実行 `cc:TODO`
  - [ ] `make clean` - クリーンアップ `cc:TODO`

### 8.3 ローカル動作確認環境 `cc:TODO`
- [ ] エンドツーエンドテスト環境構築 `cc:TODO`
- [ ] 開発ワークフローの最適化 `cc:TODO`
- [ ] ドキュメント作成（ローカル開発ガイド） `cc:TODO`

**参照ファイル**:
- `langgraph-reference/coworking-space-system/docker-compose.yml` - 参考実装

---

## フェーズ 9: ドキュメント更新 `cc:TODO`

> 担当: Claude Code
> 目的: 大幅に変わったプロジェクト構造に沿ってドキュメント更新・パス修正

### 9.1 README.mdの更新 `cc:TODO`
- [ ] プロジェクトルートの`README.md`更新 `cc:TODO`
- [ ] `backend/README.md`更新 `cc:TODO`
- [ ] `frontend/README.md`更新 `cc:TODO`
- [ ] セットアップ手順の更新 `cc:TODO`
- [ ] アーキテクチャ図の更新 `cc:TODO`

### 9.2 開発ガイドの更新 `cc:TODO`
- [ ] `docs/development/DEVELOPER-GUIDE.md`更新 `cc:TODO`
- [ ] `docs/development/LOCAL-DEVELOPMENT-SETUP.md`更新 `cc:TODO`
- [ ] `docs/development/LANGGRAPH-DEVELOPMENT-GUIDE.md`更新 `cc:TODO`
- [ ] パス修正（旧パス → 新パス） `cc:TODO`

### 9.3 APIドキュメントの更新 `cc:TODO`
- [ ] `docs/api/API.md`更新 `cc:TODO`
- [ ] `docs/api/API-ja.md`更新 `cc:TODO`
- [ ] エンドポイント一覧の更新 `cc:TODO`
- [ ] リクエスト/レスポンス形式の更新 `cc:TODO`

### 9.4 アーキテクチャドキュメントの更新 `cc:TODO`
- [ ] `docs/architecture/SYSTEM-ARCHITECTURE.md`更新 `cc:TODO`
- [ ] `docs/architecture/UNIFIED-ARCHITECTURE.md`更新 `cc:TODO`
- [ ] エージェント構成図の更新 `cc:TODO`
- [ ] ワークフロー図の更新 `cc:TODO`

### 9.5 その他のドキュメント修正 `cc:TODO`
- [ ] ドキュメント内のパス修正（一括検索・置換） `cc:TODO`
- [ ] 古い参照の削除 `cc:TODO`
- [ ] リンク切れの修正 `cc:TODO`

**完了条件**:
- [ ] すべてのドキュメントが最新のプロジェクト構造を反映している
- [ ] パス参照が正しい
- [ ] セットアップ手順が動作することを確認

---

## フェーズ 2: LangGraph 移行 - 会話機能 `cc:WIP`

> 担当: テリスケ（骨組み）, takegg0311・YukitoLyn（完全実装）, Chie, Jun

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
| 24 | テスト基盤整備 | feature/test-infrastructure | ✅ マージ済み |
| 20 | RouterAgent実装 | feature/router-agent-implementation | ✅ コンフリクト解決完了 (push待ち) |
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

---

## 📦 完了済みフェーズのアーカイブ

完了済みのフェーズ詳細は以下を参照:

→ [`.claude/memory/archive/Plans-archive.md`](.claude/memory/archive/Plans-archive.md)

**アーカイブ内容**:
- フェーズ 0.5: OpenRouter API徹底整備
- フェーズ 0.6: プロジェクト構造リファクタリング
- フェーズ 1.1: RouterAgent 移行
- フェーズ 1.2: BusinessInfoAgent 移行
- フェーズ 1.3: EventAgent 移行
- フェーズ 1.4: SlideAgent 移行
- フェーズ 1.5: FacilityAgent 移行
- フェーズ 1.6: RouterAgent統合とエージェント連携検証
- フェーズ 2.1: MemoryAgent 骨組み実装
- フェーズ 6: テスト基盤整備
- フェーズ 7: AIロジックのバックエンド統合とフロントエンド整理

---

## フェーズ 7: AIロジックのバックエンド統合とフロントエンド整理 `cc:WIP`

> 担当: Claude Code
> 開始日: 2025-01-12
> ブランチ: refactor/backend-api-integration

**目的**: フロントエンド(Mastra)からバックエンド(FastAPI + LangGraph)へのAIロジック移行

### 7.1 バックエンドAPI拡張 `cc:DONE`
- [x] `/api/voice` エンドポイント追加 (プレースホルダー) `cc:DONE`
- [x] `/api/slides` エンドポイント追加 (プレースホルダー) `cc:DONE`
- [x] `/api/character` エンドポイント追加 (プレースホルダー) `cc:DONE`
- [x] backend/main.py にリクエスト/レスポンスモデル定義 `cc:DONE`

### 7.2 フロントエンドAPI Routes プロキシ化 `cc:DONE`
- [x] `/api/qa/route.ts` をバックエンドプロキシに変更 `cc:DONE`
- [x] `/api/voice/route.ts` をバックエンドプロキシに変更 `cc:DONE`
- [x] `/api/slides/route.ts` をバックエンドプロキシに変更 `cc:DONE`
- [x] `/api/character/route.ts` をバックエンドプロキシに変更 `cc:DONE`
- [x] `/api/marp/route.ts` を一時無効化(503) `cc:DONE`
- [x] `/api/external/route.ts` を一時無効化(503) `cc:DONE`
- [x] `/api/knowledge/search/route.ts` を一時無効化(503) `cc:DONE`

### 7.3 Mastra参照の整理 `cc:DONE`
- [x] `frontend/src/mastra/` を `frontend/src/_reference/mastra/` に移動 `cc:DONE`
- [x] `frontend/src/slides/` を削除 `cc:DONE`
- [x] 残存する @/mastra import の解決 `cc:DONE`
  - [x] tsconfig.json で src/_reference/** を除外 `cc:DONE`
  - [x] src/lib/types.ts を作成し一時的な型定義を追加 `cc:DONE`
  - [x] src/lib/ 内の全 @/mastra/types/config 参照を @/lib/types に変更 `cc:DONE`
  - [x] src/jobs/ 内の @/mastra 参照を修正 `cc:DONE`

### 7.4 環境変数設定 `cc:DONE`
- [x] `BACKEND_API_URL` を `.env.example` に追加 `cc:DONE`

### 7.5 バックエンド実装 (完全実装) `cc:TODO`
- [ ] 音声処理ロジック実装 (STT/TTS) `cc:TODO`
- [ ] スライド制御ロジック実装 `cc:TODO`
- [ ] キャラクター制御ロジック実装 `cc:TODO`
- [ ] LangGraphワークフローとの統合 `cc:TODO`

### 7.6 CI/CD検証 `cc:DONE`
- [x] `ruff check .` (backend) - ✅ PASS `cc:DONE`
- [x] `black --check .` (backend) - ✅ PASS `cc:DONE`
- [x] `pytest` (backend) - ⚠️ 7件失敗 (SlideAgent narration関連 - 既存問題) `cc:DONE`
- [x] `pnpm lint` (frontend) - ✅ PASS (警告のみ、既存) `cc:DONE`
- [x] `pnpm typecheck` (frontend) - ✅ PASS (0 TypeScriptエラー) `cc:DONE`
- [x] `pnpm build` (frontend) - ⚠️ Supabase設定エラー(既存問題) `cc:DONE`

### 完了したタスク

**PMレビュー後の対応完了**:
- ✅ TypeScriptエラー解決 (40+ → 0件)
- ✅ 全API Routesのプロキシ化/一時無効化
- ✅ src/lib/ および src/jobs/ 内の @/mastra 参照修正
- ✅ CI/CD検証完了 (typecheck PASS)

### 残タスク (別PR予定)

**バックエンド完全実装 (フェーズ7.5)**:
- バックエンドの音声/スライド/キャラクター処理の完全実装 (80%)
- LangGraphワークフローとの統合
- Supabaseビルドエラー修正 (既存問題)

### PR #25 状態

- ブランチ: `refactor/backend-api-integration`
- ステータス: Draft PR (PMレビュー待ち)
- URL: https://github.com/EngineerCafeJP/engineercafe-navigator/pull/25
- 次のアクション: PMレビュー後にReady for Reviewまたはマージ判断
