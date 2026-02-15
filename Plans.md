# Plans.md - Engineer Cafe Navigator

> 最終更新: 2026-02-15
> モード: 2-Agent (Cursor PM + Claude Code Worker)

---

## 現在のステータス

| 項目 | 状態 |
|------|------|
| **フェーズ** | 2月: 結合テスト + RAGナレッジベース強化 |
| **CI/CD** | ✅ グリーン |
| **単体テスト** | ✅ 481 passed / 0 failed |
| **E2E回答品質** | ✅ 5/6 PASS, 平均KW率 83% |
| **オープン PR** | PR #76 (backend-internal-improvements) |
| **ベースブランチ** | develop |

---

## 2月マイルストーン: 結合テスト

### チーム編成と担当範囲

| チーム | 担当者 | 対象エージェント | 主なタスク |
|--------|--------|-----------------|-----------|
| **実務系統括記憶** | テリスケ | Router, Memory, BusinessInfo, Event, Facility, Slide, GeneralKnowledge | Supabase統合、DB結合テスト |
| **音声系** | Jun, Chie, たけがわ | LanguageClassifier, ClarificationAgent, VoiceAgent | STT/TTS連携、音声フロー統合 |
| **OCR系** | けいてぃー, たけがわ | OCRAgent + 関連エージェント | 画像認識→ルーター連携 |
| **フロント系** | takegg0311, 中村 | CharacterControlAgent, フロントエンド | VRM制御、API移行 |

### 重要タスク

1. **環境変数の統一** - 各エージェントで異なる変数名を統一
2. **用語の標準化** - 感情(emotion) vs 表情(expression) など
3. **API移行** - フロントエンド(Next.js)からバックエンド(FastAPI)へ

---

## エージェント実装状況

### 単体テスト完了（マージ済み）

| エージェント | 系統 | メイン実装 | PR |
|-------------|------|-----------|-----|
| router-agent | 統括 | テリスケ | - |
| business-info-agent | 実務系 | テリスケ | - |
| event-agent | 実務系 | テリスケ | #48 |
| facility-agent | 実務系 | テリスケ | - |
| slide-agent | 実務系 | テリスケ | - |
| general-knowledge-agent | 実務系 | テリスケ | #31 |
| clarification-agent | 音声系 | Chie | #34 |
| language-classifier | 音声系 | たけがわ | #44 |
| voice-agent | 音声系 | たけがわ | #45 |
| character-control-agent | UI/フロント系 | takegg0311 | #47 |

### レビュー中

| エージェント | 系統 | メイン実装 | レビュアー | PR |
|-------------|------|-----------|-----------|-----|
| memory-agent | 記憶系 | YukitoLyn | takegg0311 | #55 |
| ocr-agent | 画像系 | けいてぃー | たけがわ | - |

### 実装中

| 項目 | 担当 | 備考 |
|------|------|------|
| フロントエンド整備・更新 | 中村 | API移行調査中 |

---

## 今週完了したタスク（2026-02-15）

| タスク | PR | 担当 |
|--------|-----|------|
| X投稿分析に基づくルーティングキーワード拡張（貸切/建物/イベント/設備等） | #76 | テリスケ |
| ClarificationAgent実践メッセージ化（saino営業時間/会議室タイプ） | #76 | テリスケ |
| ゴールデンデータセット拡張（38→48ケース、100%正解維持） | #76 | テリスケ |
| RAGカテゴリボーナスバグ修正 + 類似度閾値チューニング(0.5→0.35) | #76 | テリスケ |
| ナレッジベース拡充 20→25エントリ（saino メニュー3件 + EIC 2026 3件） | #76 | テリスケ |
| 施設プロンプト改善（メニュー対応 + 具体的情報指示） | #76 | テリスケ |
| E2E回答品質評価ツール作成（run_answer_quality_evaluation.py） | #76 | テリスケ |
| E2E回答品質: 1/6 PASS → 5/6 PASS 改善 | #76 | テリスケ |

---

## 次フェーズ: プロダクションRAGシステム構築

### スコープ

1. **Hierarchical RAG採用**: 親ドキュメント→子チャンク→リランカー構成
2. **PDF/MDアップロード抽出・補完**: 自動分析・分類・ナレッジ追加
3. **RAGAS評価フレームワーク導入**: RAG品質の定量的評価
4. **動的ナレッジ優先度管理**: プロダクションレベルのRAGシステム

### ナレッジベース構造化（次フェーズで実施）

現在: `scripts/seed_knowledge.py` に全25エントリを単一ファイル管理
提案: カテゴリ別YAML/JSONファイルに分離

```
backend/knowledge/
├── data/
│   ├── general.yaml          # 基本概要、連絡先
│   ├── facilities.yaml       # メインホール、MAKER's、集中スペース、会議室
│   ├── saino_cafe.yaml       # 営業情報、フード、ドリンク、バー
│   ├── community.yaml        # CM相談、Lab、EIC
│   ├── building_history.yaml # 赤煉瓦文化館
│   └── policies.yaml         # 飲食、喫煙、駐車場、駐輪場
├── loader.py                 # YAML読み込み→Supabase seed
└── schema.py                 # エントリのバリデーションスキーマ
```

メリット:
- カテゴリ別管理で編集・レビューが容易
- PDF/MD自動処理パイプラインとの統合が自然
- マージコンフリクトの最小化

### 未収集ナレッジ（要ヒアリング）

| 項目 | 優先度 | 状態 |
|------|--------|------|
| MAKER's素材・材料費の具体価格 | 高 | 未収集 |
| バリアフリー情報（車椅子・エレベーター） | 中 | 未収集 |
| 子連れ利用・騒音ポリシー | 中 | 未収集 |
| 撮影ポリシー（一般利用時） | 低 | 未収集 |
| 初回利用登録の詳細フロー | 中 | 部分的 |

---

## CI/CD チェックリスト

PR 作成・更新時に以下を確認:

- [ ] `pnpm lint` (frontend) - ESLint
- [ ] `pnpm typecheck` (frontend) - TypeScript
- [ ] `pnpm build` (frontend) - Next.js ビルド
- [ ] `ruff check .` (backend) - Python リンター
- [ ] `black --check .` (backend) - Python フォーマット

---

## 結合テスト: 環境変数統一タスク

> バックログで管理: 各チームで以下を確認・統一

### 統一すべき項目

| 項目 | 現状 | 統一後 |
|------|------|--------|
| OpenRouter APIキー | `OPENROUTER_API_KEY` | 統一済み |
| Supabase URL | `SUPABASE_URL` | 統一済み |
| 感情タグ | `emotion` / `feeling` など | `emotion` に統一 |
| 表情 | `expression` / `face` など | `expression` に統一 |
| 言語コード | `lang` / `language` など | `language` に統一 |

### 各チームのアクション

1. **developをpull**して最新状態を確認
2. **自チームのエージェント**の環境変数・用語を確認
3. **不整合を発見**したらDiscordで報告
4. **修正PR**を作成してマージ

---

## リファレンス資料

- `docs/reference/engineer-cafe-reference.md` - エンジニアカフェ公式情報
- `docs/development/AGENT-QUICKSTART.md` - エージェント開発クイックスタート
- `docs/development/ENVIRONMENT-VARIABLES.md` - 環境変数ガイド

---

## 決定事項 (SSOT)

→ `.claude/memory/decisions.md` 参照

---

## 📦 完了済みフェーズのアーカイブ

→ [`.claude/memory/archive/Plans-archive.md`](.claude/memory/archive/Plans-archive.md)

**アーカイブ内容**:
- フェーズ 0.5-0.6: OpenRouter API整備、構造リファクタリング
- フェーズ 1.1-1.5: Agent移行（Router, BusinessInfo, Event, Slide, Facility）
- フェーズ 2.1-2.3: 会話機能骨組み（Memory, Clarification, LanguageClassifier）
- フェーズ 4.3: GeneralKnowledgeAgent 完全実装
- フェーズ 6: テスト基盤整備
- フェーズ 7.5.1-7.5.4: エージェント骨組み実装とワークフロー統合
- フェーズ 8: 開発環境整備（Docker + mise + Makefile）
- フェーズ 9: エージェント実装支援資料
- **新規** LangChain Evaluations拡張（PR #53, #54）
- **新規** バックエンド実践データ強化 + RAG改善（PR #76, 2026-02-07~15）
