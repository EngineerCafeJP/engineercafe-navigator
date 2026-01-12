# Plans.md - Engineer Cafe Navigator

> 最終更新: 2025-01-12
> モード: 2-Agent (Cursor PM + Claude Code Worker)

---

## 現在のステータス

| 項目 | 状態 |
|------|------|
| **CI/CD** | ✅ グリーン (最終実行: 2025-01-12) |
| **オープン PR** | PR #24 (テスト基盤), PR #25 (バックエンド統合 - Draft) |
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
- フェーズ 2.2: ClarificationAgent 骨組み実装 (2025-01-13)
- フェーズ 2.3: LanguageClassifier 骨組み実装 (2025-01-13)
- フェーズ 4.3: GeneralKnowledgeAgent 骨組み実装 (2025-01-13)
- フェーズ 6: テスト基盤整備
- フェーズ 7.5.1-7.5.4: エージェント骨組み実装とワークフロー統合 (2025-01-13)

---

## フェーズ 7: AIロジックのバックエンド統合とフロントエンド整理 `cc:WIP`

> 担当: Claude Code
> 開始日: 2025-01-12
> ブランチ: refactor/backend-api-integration

**目的**: フロントエンド(Mastra)からバックエンド(FastAPI + LangGraph)へのAIロジック移行

**完了済み**:
- ✅ 7.1-7.4: バックエンドAPI拡張、フロントエンドプロキシ化、Mastra参照整理
- ✅ 7.6: CI/CD検証 (TypeScript 0エラー達成)

**進行中**:
- 🔄 7.5: バックエンド実装 (音声/スライド/キャラクター処理)

**7.5 バックエンド実装**

### 7.5.1-7.5.4 エージェント骨組み実装とワークフロー統合 `cc:DONE` `pm:確認済`
> 完了: 2025-01-13 | PR: #27, #28
> VoiceAgent, CharacterControlAgent, ClarificationAgent, GeneralKnowledgeAgentの骨組み実装とワークフロー統合が完了。詳細はアーカイブ参照。

**残タスク**:
- [ ] LanguageClassifier のワークフロー統合（RouterAgentから呼び出される形で既に統合済みの可能性あり、要確認）
- [ ] VoiceAgent のワークフロー統合（音声処理エンドポイント `/api/voice`）
- [ ] CharacterControlAgent のワークフロー統合（キャラクター制御エンドポイント `/api/character`）
- [ ] RouterAgent関連のファイル変更はPR#20にpush（要確認）
