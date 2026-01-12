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

**完了**: AGENTS.md, Plans.md作成
**残タスク**: .cursor/commands/, .claude/rules整備, .gitignore整理, OpenRouterモデル更新

---

## 📋 次の実装計画（優先順位順）

1. **フェーズ7.5**: バックエンド完全実装 (STT/TTS, スライド/キャラクター制御) - 2-3週間
2. **フェーズ8**: 開発環境整備 (Docker, mise/make) - 1-2週間
3. **フェーズ9**: ドキュメント更新 (README, API, アーキテクチャ) - 1週間
4. **フェーズ2.2-2.3**: 会話機能完成 (ClarificationAgent, LanguageClassifier) - 1週間

---

## フェーズ 1: LangGraph 移行 - コア機能 `cc:DONE`

> 担当: テリスケ, Natsumi, けいてぃー
> 完了: 2025-01-13

**完了したサブフェーズ**:
- ✅ 1.1 RouterAgent 移行
- ✅ 1.2 BusinessInfoAgent 移行
- ✅ 1.3 EventAgent 移行
- ✅ 1.4 SlideAgent 移行
- ✅ 1.5 FacilityAgent 移行
- ✅ 1.6 RouterAgent統合とエージェント連携検証

→ 詳細は [`.claude/memory/archive/Plans-archive.md`](.claude/memory/archive/Plans-archive.md) を参照

---

## フェーズ 8: 開発環境整備 `cc:TODO`

> 担当: Claude Code

**タスク**:
- Docker環境整備 (Dockerfile, docker-compose.yml)
- mise/make統合 (.mise.toml, Makefile)
- E2Eテスト環境構築

---

## フェーズ 9: ドキュメント更新 `cc:TODO`

> 担当: Claude Code

**タスク**:
- README更新 (root, backend, frontend)
- 開発ガイド更新 (パス修正含む)
- APIドキュメント更新
- アーキテクチャ図更新

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

- VoiceAgent移行 (STT/TTS, 感情タグ)
- CharacterControlAgent移行 (表情マッピング, VRM制御)

---

## フェーズ 4: 新機能 `cc:TODO`

> 担当: けいてぃー, たけがわ

- OCRAgent新規実装 (YOLO/Google Vision, QR/表情認識)
- EventAgent拡張 (Connpass/Calendar API完全実装)
- GeneralKnowledgeAgent移行 (Web検索)

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
> ブランチ: refactor/backend-api-integration

**完了済み**:
- ✅ 7.1-7.4: バックエンドAPI拡張、フロントエンドプロキシ化、Mastra参照整理
- ✅ 7.6: CI/CD検証 (TypeScript 0エラー達成)

**進行中**:
- 🔄 7.5: バックエンド完全実装 (音声/スライド/キャラクター処理)

**PR #25**: Draft (PMレビュー待ち)
→ 詳細は [PR #25](https://github.com/EngineerCafeJP/engineercafe-navigator/pull/25) 参照
