# Plans.md - Engineer Cafe Navigator

> 最終更新: 2026-01-13
> モード: 2-Agent (Cursor PM + Claude Code Worker)

---

## 現在のステータス

| 項目 | 状態 |
|------|------|
| **CI/CD** | ✅ グリーン (最終実行: 2026-01-13) |
| **オープン PR** | PR #20 (RouterAgent), PR #30 (フェーズ8+9完了 - レビュー待ち), PR #31 (GeneralKnowledgeAgent完全実装 - グリーン) |
| **完了したフェーズ** | 0.5 (OpenRouter), 0.6 (構造整理), 1.1-1.5 (Agent移行), 2.1-2.3 (会話機能骨組み), 4.3 (GeneralKnowledgeAgent), 6 (テスト), 7.1-7.6 (バックエンド統合) |
| **次のフェーズ** | 7.5 (バックエンド完全実装), 3.1-3.2 (出力機能), 4.1-4.2 (新機能) |
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

## フェーズ 1: LangGraph 移行 - コア機能 `cc:DONE`
> 完了: RouterAgent, BusinessInfoAgent, EventAgent, SlideAgent 骨組み実装 | 詳細: [アーカイブ](.claude/memory/archive/Plans-archive.md)

---

## フェーズ 2: LangGraph 移行 - 会話機能 `cc:DONE`
> 完了: MemoryAgent, ClarificationAgent, LanguageClassifier 骨組み実装 | 詳細: [アーカイブ](.claude/memory/archive/Plans-archive.md)

---

## フェーズ 3: LangGraph 移行 - 出力機能 `cc:TODO`

> 担当: Chie, takegg0311, テリスケ

- VoiceAgent移行 (STT/TTS, 感情タグ)
- CharacterControlAgent移行 (表情マッピング, VRM制御)

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

### 4.3 GeneralKnowledgeAgent 移行 `cc:DONE`
> 完了: 骨組み実装 | 詳細: [アーカイブ](.claude/memory/archive/Plans-archive.md)

#### 4.3.1 GeneralKnowledgeAgent完全実装 `cc:DONE` `pm:確認済`
> 依頼日: 2026-01-13
> 担当: Claude Code
> 完了日: 2026-01-13
> プラン: [generalknowledgeagent完全実装とrouteragent統合](.cursor/plans/generalknowledgeagent完全実装とrouteragent統合_01c9d7a6.plan.md)

**タスク**:
- [x] Web検索ツールの実装（backend/tools/web_search.py） `cc:DONE` (2026-01-13)
- [x] GeneralKnowledgeAgentの完全実装（backend/agents/general_knowledge_agent.py） `cc:DONE` (2026-01-13)
- [ ] テスト実装（backend/tests/agents/test_general_knowledge_agent.py） `cc:TODO`
- [x] RouterAgentのGeneralKnowledgeAgentルーティング確認・修正（PR#20） `cc:DONE` (2026-01-13)
- [x] PR#31作成（GeneralKnowledgeAgent完全実装、CI/CDグリーン） `cc:DONE` (2026-01-13)
- [x] PR#20のコンフリクト解消と最終確認 `cc:DONE` (2026-01-13)

**完了条件**:
- [x] GeneralKnowledgeAgent完全実装完了 ✅
- [x] Web検索ツール実装完了 ✅
- [ ] テスト実装完了
- [x] PR#31作成完了（CI/CDグリーン） ✅
- [x] PR#20のコンフリクト解消完了 ✅
- [x] 統合テスト成功 ✅

---

## オープン PR 一覧

| # | タイトル | ブランチ | ステータス |
|---|----------|----------|-----------|
| 20 | RouterAgent実装 | feature/router-agent-implementation | OPEN (コンフリクト解決中) |
| 30 | フェーズ8+9完了 - 開発環境整備とエージェント実装支援資料 | feature/phase-8-9-completion | OPEN (レビュー待ち) |
| 31 | GeneralKnowledgeAgent完全実装 | feature/general-knowledge-agent-implementation | OPEN (CI/CD グリーン) |

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
- フェーズ 1.1-1.5: Agent移行（Router, BusinessInfo, Event, Slide, Facility）
- フェーズ 2.1-2.3: 会話機能骨組み（Memory, Clarification, LanguageClassifier）
- フェーズ 4.3: GeneralKnowledgeAgent 完全実装 (Web検索ツール含む) | PR: #31
- フェーズ 6: テスト基盤整備
- フェーズ 7.5.1-7.5.4: エージェント骨組み実装とワークフロー統合
- フェーズ 8: 開発環境整備（Docker + mise + Makefile） | PR: #29
- フェーズ 9: エージェント実装支援資料の整備（7ドキュメント作成）

---

## フェーズ 7: AIロジックのバックエンド統合とフロントエンド整理 `cc:WIP`

> 担当: Claude Code
> ブランチ: refactor/backend-api-integration

**完了済み**:
- ✅ 7.1-7.4: バックエンドAPI拡張、フロントエンドプロキシ化、Mastra参照整理
- ✅ 7.6: CI/CD検証 (TypeScript 0エラー達成)

**完了済み**:
- ✅ 7.1-7.4: バックエンドAPI拡張、フロントエンドプロキシ化、Mastra参照整理
- ✅ 7.6: CI/CD検証 (TypeScript 0エラー達成)

**7.5 バックエンド完全実装** `cc:TODO`

- ✅ 7.5.1-7.5.4: エージェント骨組み実装完了 (2026-01-13 | PR: #27, #28) - [アーカイブ参照](.claude/memory/archive/Plans-archive.md)
- [ ] LanguageClassifier のワークフロー統合 `cc:TODO`
- [ ] VoiceAgent のワークフロー統合（音声処理エンドポイント `/api/voice`） `cc:TODO`
- [ ] CharacterControlAgent のワークフロー統合（キャラクター制御エンドポイント `/api/character`） `cc:TODO`
- [ ] RouterAgent関連のファイル変更はPR#20にpush `cc:TODO` `pm:依頼中`

---

## フェーズ 8: 開発環境整備 `cc:DONE`
> 完了: Docker + mise + Makefile 統一開発環境 | PR: #29 | 詳細: [アーカイブ](.claude/memory/archive/Plans-archive.md)

---

## フェーズ 9: エージェント実装支援資料の整備 `cc:DONE`
> 完了: 7種ドキュメント作成、docs/ 構造整理 | PR: #30 | 詳細: [アーカイブ](.claude/memory/archive/Plans-archive.md)
