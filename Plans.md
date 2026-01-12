# Plans.md - Engineer Cafe Navigator

> 最終更新: 2026-01-13
> モード: 2-Agent (Cursor PM + Claude Code Worker)

---

## 現在のステータス

| 項目 | 状態 |
|------|------|
| **CI/CD** | ✅ グリーン (最終実行: 2026-01-13) |
| **オープン PR** | PR #20 (RouterAgent), PR #30 (フェーズ8+9完了 - レビュー待ち) |
| **完了したフェーズ** | 0.5 (OpenRouter), 0.6 (構造整理), 1.1-1.5 (Agent移行), 2.1-2.3 (会話機能骨組み), 6 (テスト), 7.1-7.6 (バックエンド統合) |
| **次のフェーズ** | 7.5 (バックエンド完全実装), 3.1-3.2 (出力機能), 4.1-4.3 (新機能) |
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

---

## フェーズ 1: LangGraph 移行 - コア機能 `cc:DONE`

> 担当: テリスケ, Natsumi, けいてぃー
> **完了**: フェーズ1のコア機能実装は全て完了。詳細はアーカイブ参照。

---

## フェーズ 2: LangGraph 移行 - 会話機能 `cc:DONE`

> 担当: テリスケ（骨組み）, takegg0311・YukitoLyn（完全実装）, Chie, Jun
> **完了**: フェーズ2の会話機能骨組みは全て完了。詳細はアーカイブ参照。

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

### 4.3 GeneralKnowledgeAgent 移行 `cc:DONE` `pm:確認済`
> 完了: 2025-01-13 | 骨組み実装完了。詳細はアーカイブ参照。
- [ ] Web 検索機能 `cc:TODO` (完全実装時に実装)

---

## オープン PR 一覧

| # | タイトル | ブランチ | ステータス |
|---|----------|----------|-----------|
| 20 | RouterAgent実装 | feature/router-agent-implementation | OPEN (レビュー待ち) |
| 30 | フェーズ8+9完了 - 開発環境整備とエージェント実装支援資料 | feature/phase-8-9-completion | OPEN (レビュー待ち) |

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
- フェーズ 1.1-1.4: Agent移行（Router, BusinessInfo, Event, Slide）
- フェーズ 2.1-2.3: 会話機能骨組み（Memory, Clarification, LanguageClassifier）
- フェーズ 4.3: GeneralKnowledgeAgent 骨組み実装
- フェーズ 6: テスト基盤整備
- フェーズ 7.5.1-7.5.4: エージェント骨組み実装とワークフロー統合
- フェーズ 8: 開発環境整備（Docker + mise + Makefile） | PR: #29
- フェーズ 9: エージェント実装支援資料の整備（7ドキュメント作成）

---

## フェーズ 7: AIロジックのバックエンド統合とフロントエンド整理 `cc:WIP`

> 担当: Claude Code
> 開始日: 2025-01-12
> ブランチ: refactor/backend-api-integration

**目的**: フロントエンド(Mastra)からバックエンド(FastAPI + LangGraph)へのAIロジック移行

**完了済み**:
- ✅ 7.1-7.4: バックエンドAPI拡張、フロントエンドプロキシ化、Mastra参照整理
- ✅ 7.6: CI/CD検証 (TypeScript 0エラー達成)

**7.5 バックエンド完全実装** `cc:TODO`

- ✅ 7.5.1-7.5.4: エージェント骨組み実装完了 (2025-01-13 | PR: #27, #28) - [アーカイブ参照](.claude/memory/archive/Plans-archive.md)
- [ ] LanguageClassifier のワークフロー統合 `cc:TODO`
- [ ] VoiceAgent のワークフロー統合（音声処理エンドポイント `/api/voice`） `cc:TODO`
- [ ] CharacterControlAgent のワークフロー統合（キャラクター制御エンドポイント `/api/character`） `cc:TODO`
- [ ] RouterAgent関連のファイル変更はPR#20にpush `cc:TODO`

---

## フェーズ 8: 開発環境整備（Docker + mise + Makefile） `cc:DONE` `pm:確認済`

> 担当: Claude Code
> 完了日: 2025-01-13 | PR: #29

**目的**: Docker環境とmise/Makefileによる統一された開発コマンドの整備

**実装完了内容**:
- ✅ mise設定（.mise.toml） - Node.js 18.20.0, Python 3.11.10, pnpm 10.12.1
- ✅ Docker環境（Dockerfile, docker-compose.yml, .dockerignore）
- ✅ Makefile - 統一開発コマンド（setup, dev, lint, clean等）
- ✅ ドキュメント更新（README.md, LOCAL-DEVELOPMENT-SETUP.md）
- ✅ CI/CDチェック合格

**詳細はアーカイブ参照**: [Plans-archive.md](.claude/memory/archive/Plans-archive.md#phase-8)

---

## フェーズ 9: エージェント実装支援資料の整備 `cc:DONE` `pm:確認済`

> 担当: Claude Code
> 優先度: 高
> 完了日: 2026-01-13 | PR: #30

**目的**: 新規エンジニアが効率的にエージェント実装できるよう、ドキュメント・ツール・ガイドラインを整備

**タスク**:
- [x] 9.1 クイックスタートガイド（AGENT-QUICKSTART.md） `cc:DONE`
- [x] 9.2 実装チェックリスト（AGENT-IMPLEMENTATION-CHECKLIST.md） `cc:DONE`
- [x] 9.3 環境変数設定ガイド（ENVIRONMENT-VARIABLES.md） `cc:DONE`
- [x] 9.4 デバッグツール整備（debug_agent.py, Makefileコマンド追加） `cc:DONE`
- [x] 9.5 トラブルシューティングガイド（TROUBLESHOOTING.md） `cc:DONE`
- [x] 9.6 コードレビューガイドライン（CODE-REVIEW-GUIDELINES.md） `cc:DONE`
- [x] 9.7 実装例の充実（AGENT-EXAMPLES.md, docstring追加） `cc:DONE`
- [x] 9.8 専門エンジニアへの実装依頼ドキュメント（AGENT-IMPLEMENTATION-REQUEST.md） `cc:DONE`
- [x] 9.9 プロジェクト全体のドキュメントリファクタリング・パス修正 `cc:DONE`

**実装完了内容**:
- ✅ ドキュメント構造整理（frontend/docs/ 削除、docs/ に統一）
- ✅ パス参照修正（README.md, frontend/README.md, backend/README.md）
- ✅ docs/README.md 包括的更新（50+ドキュメント、推奨読書順序追加）
- ✅ アーカイブディレクトリ作成（docs/archive/frontend-docs-old/）

**詳細はアーカイブ参照**: [Plans-archive.md](.claude/memory/archive/Plans-archive.md#phase-9)
