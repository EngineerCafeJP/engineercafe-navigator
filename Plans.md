# Plans.md - Engineer Cafe Navigator

> 最終更新: 2025-01-12
> モード: 2-Agent (Cursor PM + Claude Code Worker)

---

## 現在のステータス

| 項目 | 状態 |
|------|------|
| **CI/CD** | ✅ グリーン (最終実行: 2025-01-12) |
| **オープン PR** | PR #24 (テスト基盤整備 - レビュー待ち) |
| **完了したフェーズ** | 0.5 (OpenRouter API), 0.6 (構造リファクタリング), 1.1-1.4 (Router/BusinessInfo/Event/SlideAgent), 2.1 (MemoryAgent骨組み), 6 (テスト基盤) |
| **次のフェーズ** | 1.5 (FacilityAgent), 2.2-2.3 (Clarification/LanguageClassifier) |
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

### 最優先: フェーズ1.5 FacilityAgent実装

**目的**: 設備情報クエリ処理を実装

**推定期間**: 3日

### 次優先: フェーズ2.2-2.3 会話機能完成

**目的**: ClarificationAgentとLanguageClassifierを実装

**推定期間**: 1週間

---

## フェーズ 1: LangGraph 移行 - コア機能 `cc:WIP`

> 担当: テリスケ, Natsumi, けいてぃー

### 1.5 FacilityAgent 移行 `cc:TODO`
- [ ] 地下施設キーワード検出 `cc:TODO`
- [ ] 設備情報クエリ処理 `cc:TODO`
- [ ] テストケース作成 `cc:TODO`

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
| 24 | テスト基盤整備 | feature/test-infrastructure | OPEN (レビュー待ち) |
| 20 | RouterAgent実装 | feature/router-agent-implementation | OPEN (レビュー待ち) |
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
- フェーズ 2.1: MemoryAgent 骨組み実装
- フェーズ 6: テスト基盤整備

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

### 7.2 フロントエンドAPI Routes プロキシ化 `cc:WIP`
- [x] `/api/qa/route.ts` をバックエンドプロキシに変更 `cc:DONE`
- [x] `/api/voice/route.ts` をバックエンドプロキシに変更 `cc:DONE`
- [ ] `/api/slides/route.ts` をバックエンドプロキシに変更 `cc:blocked`
- [ ] `/api/character/route.ts` をバックエンドプロキシに変更 `cc:blocked`
- [ ] `/api/marp/route.ts` をバックエンドプロキシに変更 `cc:blocked`
- [ ] `/api/external/route.ts` をバックエンドプロキシに変更 `cc:blocked`
- [ ] `/api/knowledge/search/route.ts` をバックエンドプロキシに変更 `cc:blocked`

### 7.3 Mastra参照の整理 `cc:WIP`
- [x] `frontend/src/mastra/` を `frontend/src/_reference/mastra/` に移動 `cc:DONE`
- [x] `frontend/src/slides/` を削除 `cc:DONE`
- [ ] 残存する @/mastra import の解決 `cc:blocked`
  - src/_reference/mastra/ 内のファイル (40+ TypeScriptエラー)
  - src/lib/ 内の複数ファイル
  - src/jobs/ 内のファイル

### 7.4 環境変数設定 `cc:DONE`
- [x] `BACKEND_API_URL` を `.env.example` に追加 `cc:DONE`

### 7.5 バックエンド実装 (完全実装) `cc:TODO`
- [ ] 音声処理ロジック実装 (STT/TTS) `cc:TODO`
- [ ] スライド制御ロジック実装 `cc:TODO`
- [ ] キャラクター制御ロジック実装 `cc:TODO`
- [ ] LangGraphワークフローとの統合 `cc:TODO`

### 7.6 CI/CD検証 `cc:blocked`
- [x] `ruff check .` (backend) - ✅ PASS `cc:DONE`
- [x] `black --check .` (backend) - ✅ PASS `cc:DONE`
- [x] `pytest` (backend) - ⚠️ 7件失敗 (SlideAgent narration関連 - 既存問題) `cc:DONE`
- [x] `pnpm lint` (frontend) - ⚠️ 警告のみ `cc:DONE`
- [ ] `pnpm typecheck` (frontend) - ❌ FAIL (40+ TypeScriptエラー) `cc:blocked`
- [ ] `pnpm build` (frontend) - 未実行 `cc:blocked`

### ブロッカー詳細

**TypeScriptコンパイルエラー (40+件)**:
- `src/_reference/mastra/` 内のファイルが `@/mastra/*` をimport
- 移動後のパスが解決されない
- 影響範囲: agents, tools, workflows, types

**未実装バックエンドロジック**:
- `/api/voice`, `/api/slides`, `/api/character` はプレースホルダーのみ
- 実際の処理ロジックが未実装
- LangGraphワークフローとの統合が必要

**フロントエンドAPI Routes**:
- character, marp, slides, external, knowledge/search がまだMastra直接依存
- プロキシ化にはバックエンド実装が先行して必要

### 次のアクション (PMレビュー必要)

#### オプション1: 段階的移行
1. TypeScriptエラーを一時的に抑制 (`// @ts-ignore` または tsconfig除外)
2. 既にプロキシ化したAPI (/qa, /voice) のみでPR作成
3. 残りのAPI Routesは別PRで対応

#### オプション2: 完全移行
1. バックエンドの音声/スライド/キャラクター処理を完全実装
2. 全APIエンドポイントをプロキシ化
3. TypeScriptエラーをすべて解決
4. CI/CDオールグリーンでPR作成

**推奨**: オプション1 (段階的移行)
- リスクが低い
- レビューしやすい
- 既存機能への影響が限定的

