# Plans.md - Engineer Cafe Navigator

> 最終更新: 2025-12-27
> モード: 2-Agent (Cursor PM + Claude Code Worker)

---

## 現在のステータス

| 項目 | 状態 |
|------|------|
| **CI/CD** | ✅ グリーン (最終実行: 2025-12-27) |
| **オープン PR** | 5件 |
| **現在のブランチ** | revert/pr-15-wrong-base |
| **ベースブランチ** | main |

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

## フェーズ 1: LangGraph 移行 - コア機能 `cc:TODO`

> 担当: テリスケ, Natsumi, けいてぃー

### 1.1 RouterAgent 移行 `pm:依頼中`

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

### 1.2 BusinessInfoAgent 移行 `pm:確認済`
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

### 1.3 EventAgent 移行 `pm:確認済`
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

### 1.4 SlideAgent 移行 `pm:確認済`
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
- [ ] **スライドファイルの配置（backend/slides/）** `cc:TODO` `pm:依頼中`

**ブランチ**: `feature/business-info-event-slide-agents`（BusinessInfoAgentと同一ブランチ）

### 1.5 FacilityAgent 移行
- [ ] 地下施設キーワード検出 `cc:TODO`
- [ ] 設備情報クエリ処理 `cc:TODO`
- [ ] テストケース作成 `cc:TODO`

---

## フェーズ 2: LangGraph 移行 - 会話機能 `cc:TODO`

> 担当: takegg0311, Chie, Jun

### 2.1 MemoryAgent 移行
- [ ] Supabase 連携実装 `cc:TODO`
- [ ] 3分 TTL 処理 `cc:TODO`
- [ ] コンテキスト継承 `cc:TODO`

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

### 3.3 SlideAgent 移行
- [ ] ナレーションデータ読み込み `cc:TODO`
- [ ] スライドナビゲーション `cc:TODO`

---

## フェーズ 4: 新機能 `cc:TODO`

> 担当: けいてぃー, たけがわ

### 4.1 OCRAgent 新規実装 (LangGraph のみ)
- [ ] 技術選定完了 (YOLO/Google Vision) `cc:TODO`
- [ ] 番号認識実装 `cc:TODO`
- [ ] QR コード認識 `cc:TODO`
- [ ] 表情認識実装 `cc:TODO`
- [ ] プライバシーポリシー確認 `cc:TODO`

### 4.2 EventAgent 移行
- [ ] Connpass API 連携 `cc:TODO`
- [ ] Google Calendar API 連携 `cc:TODO`

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
