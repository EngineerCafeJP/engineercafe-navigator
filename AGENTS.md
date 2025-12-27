# AGENTS.md - Engineer Cafe Navigator

## 開発モード: 2-Agent (Cursor PM + Claude Code Worker)

---

## 役割分担

| 役割 | 担当 | 責任範囲 |
|------|------|---------|
| **PM (計画・レビュー)** | Cursor | 要件定義、プラン作成、コードレビュー、本番デプロイ |
| **Worker (実装)** | Claude Code | 実装、テスト、staging デプロイ、CI/CD 修正 |

---

## ワークフロー

```
[ユーザー] 「〇〇を作りたい」
    ↓
[Cursor PM] 要件ヒアリング → Plans.md 作成
    ↓
[Cursor PM] /handoff-to-claude → タスク依頼
    ↓
[Claude Code] 実装 + テスト + CI/CD グリーン確認
    ↓
[Claude Code] /handoff-to-cursor → 完了報告
    ↓
[Cursor PM] レビュー → 本番デプロイ or 修正依頼
```

---

## マーカー凡例

| マーカー | 状態 | 説明 |
|---------|------|------|
| `cc:TODO` | 未着手 | Claude Code が実行予定 |
| `cc:WIP` | 作業中 | Claude Code が実装中 |
| `cc:DONE` | 完了 | Claude Code が完了 |
| `cc:BLOCKED` | ブロック中 | 依存タスク待ち |
| `pm:依頼中` | PM から依頼 | Cursor からの依頼 |
| `pm:確認済` | PM 確認済み | Cursor がレビュー完了 |

---

## プロジェクト構成

```
engineer-cafe-navigator2025/
├── frontend/                 # Next.js 15 + Mastra (TypeScript)
│   ├── src/
│   │   ├── app/             # App Router
│   │   ├── mastra/          # AI Agents (12エージェント)
│   │   ├── lib/             # ユーティリティ
│   │   └── slides/          # Marp スライド
│   └── supabase/            # マイグレーション
├── backend/                  # Python + LangGraph (移行中)
│   ├── agents/
│   ├── workflows/
│   └── tests/
├── docs/                     # ドキュメント
│   └── migration/agents/    # エージェント移行仕様
├── Plans.md                  # タスク管理
├── CLAUDE.md                # Claude Code 設定
└── AGENTS.md                # このファイル
```

---

## エージェント一覧 (LangGraph 移行)

| エージェント | 担当者 | 役割 | ステータス |
|-------------|--------|------|-----------|
| RouterAgent | テリスケ | クエリルーティング | Mastra 実装済 |
| BusinessInfoAgent | テリスケ | 営業時間・料金 | Mastra 実装済 |
| FacilityAgent | Natsumi | 設備・地下施設 | Mastra 実装済 |
| EventAgent | テリスケ | イベント・カレンダー | Mastra 実装済 |
| MemoryAgent | takegg0311 | 会話履歴管理 | Mastra 実装済 |
| ClarificationAgent | Chie | 曖昧さ解消 | Mastra 実装済 |
| LanguageClassifier | Chie | 言語検出 | Mastra 実装済 |
| GeneralKnowledgeAgent | テリスケ | Web 検索 | Mastra 実装済 |
| CharacterControlAgent | takegg0311 | VRM キャラクター | Mastra 実装済 |
| VoiceAgent | Chie | STT/TTS | Mastra 実装済 |
| SlideAgent | テリスケ | スライドナレーション | Mastra 実装済 |
| OCRAgent | けいてぃー | 画像認識 | **新規** (LangGraph のみ) |

---

## CI/CD 要件

- **すべての PR で CI がグリーンであること**
- Claude Code は CI 失敗時に自動修正を試みる
- 修正不可の場合は PM に報告

---

## 関連ファイル

- `Plans.md` - タスク管理
- `CLAUDE.md` - Claude Code 詳細設定
- `.cursor/commands/` - Cursor コマンド
- `.claude/memory/` - 意思決定記録
