# Mastra → LangGraph 移行概要

## 目的

既存のMastraで構成されているAIエージェントフレームワークをLangGraphに書き換えることにより、以下の目標を達成します：

1. **Pythonエコシステムの活用**: OCR、より正確かつ細かい短期・長期記憶を動的に管理できるRAG
2. **拡張性の向上**: Gemini以外のAI API（ローカルLLMも含む）やSupabase以外のDB（MySQLなど）にも対応
3. **汎用性の高いOSS**: 様々な環境で利用可能な汎用的なシステムとして完成

## 移行の背景

### 現状（Mastra版）

- **フロントエンド**: Next.js + TypeScript + Mastra 0.10.5
- **エージェント**: RouterAgent, BusinessInfoAgent, FacilityAgent, MemoryAgent, EventAgent, GeneralKnowledgeAgent, ClarificationAgent, RealtimeAgent等
- **データベース**: Supabase (PostgreSQL + pgvector)
- **AI API**: Google Gemini 2.5 Flash Preview
- **埋め込みモデル**: OpenAI text-embedding-3-small

### 目標（LangGraph版）

- **バックエンド**: Python + FastAPI + LangGraph
- **エージェント**: 既存のMastraエージェントをPython版LangGraphで再実装
- **データベース**: Supabase（既存） + MySQL等への拡張対応
- **AI API**: Gemini + OpenAI + ローカルLLM対応
- **新機能**: OCRエージェント（新規実装）

## 移行のメリット

### 1. Pythonエコシステムの活用

- **OCR**: Tesseract, EasyOCR, Google Vision API等の豊富なライブラリ
- **RAG**: LangChain/LangGraphの高度なメモリ管理機能
- **データ処理**: pandas, numpy等の強力なデータ処理ライブラリ

### 2. 拡張性

- **AI API**: 複数のLLMプロバイダーに対応（Gemini, OpenAI, ローカルLLM等）
- **データベース**: Supabase以外のDB（MySQL, PostgreSQL等）にも対応
- **アーキテクチャ**: モジュラー設計により、新しいエージェントやツールを容易に追加可能

### 3. 開発効率

- **グラフベースのワークフロー**: LangGraphの視覚的なワークフロー設計
- **状態管理**: 永続的な実行状態とヒューマンインザループ対応
- **デバッグ**: LangSmithによる詳細なデバッグとモニタリング

## 移行対象エージェント

### 既存エージェント（Mastra版から移行）

1. **RouterAgent** (統合エージェント)
2. **BusinessInfoAgent** (エンジニアカフェ情報)
3. **FacilityAgent** (施設機能説明)
4. **MemoryAgent** (記憶機能)
5. **EventAgent** (イベント)
6. **GeneralKnowledgeAgent** (一般知識)
7. **ClarificationAgent** (明確化)
8. **RealtimeAgent** (リアルタイム音声)
9. **WelcomeAgent** (ウェルカム)
10. **SlideNarrator** (スライドナレーション)
11. **VoiceOutputAgent** (音声出力)
12. **CharacterControlAgent** (キャラクター制御)

### 新規エージェント

1. **OCRAgent** (OCR処理) - **新規実装・Mastra版未実装**

## 移行アプローチ

### Phase 1: 基盤整備（1-2週間）

- ドキュメント整備
- LangGraphワークフローの骨組み実装
- 開発環境のセットアップ
- テストフレームワークの構築

### Phase 2: エージェント移行（3-4週間）

- 各エージェントを順次移行
- featureブランチで個別開発
- developブランチで統合テスト

### Phase 3: 統合と最適化（1-2週間）

- 全体統合
- パフォーマンス最適化
- エラーハンドリングの強化

### Phase 4: 本番運用（継続）

- mainブランチへのマージ
- 本番環境へのデプロイ
- モニタリングと改善

## 参考リポジトリ

- **LangGraph参考実装**: `langgraph-reference/` (https://github.com/terisuke/langgraph)
  - coworking-space-systemの実装例を参考にします
  - git submoduleとして管理されています

### 参考リポジトリの取得

```bash
# 初回クローン時
git clone --recurse-submodules <repository-url>

# 既存リポジトリの場合
git submodule update --init --recursive
```

## 準備状況

開発に必要な準備は完了しています：

- ✅ バックエンドのディレクトリ構造
- ✅ 共通ユーティリティと型定義
- ✅ テストフレームワーク設定
- ✅ CI/CDパイプライン
- ✅ 環境変数テンプレート
- ✅ エラーハンドリングとロギング標準
- ✅ OCR関連の依存関係
- ✅ 実装例とサンプルコード
- ✅ コードレビュープロセス

詳細: [準備チェックリスト](PREPARATION-CHECKLIST.md)

## ドキュメント構造

詳細なドキュメントは以下の構造で整備されています：

```
docs/migration/
├── OVERVIEW.md                    # 本ドキュメント
├── ROADMAP.md                     # 移行ロードマップ
├── BRANCH-STRATEGY.md             # ブランチ戦略
├── TEAM-ASSIGNMENTS.md            # チーム担当者一覧
├── INTEGRATION-GUIDE.md           # 統合ガイド
├── COWORKING-SYSTEM-ANALYSIS.md   # coworking-space-system分析
├── MASTRA-AGENT-ANALYSIS.md       # Mastra版エージェント分析
└── agents/                        # エージェント別ドキュメント
    ├── router-agent/
    ├── business-info-agent/
    ├── facility-agent/
    ├── memory-agent/
    ├── event-agent/
    ├── general-knowledge-agent/
    ├── clarification-agent/
    ├── character-control-agent/
    ├── language-classifier/
    ├── voice-agent/
    ├── slide-agent/
    └── ocr-agent/
```

## 次のステップ

1. [BRANCH-STRATEGY.md](./BRANCH-STRATEGY.md) を読んでブランチ戦略を理解する
2. [TEAM-ASSIGNMENTS.md](./TEAM-ASSIGNMENTS.md) で自分の担当エージェントを確認する
3. 担当エージェントのドキュメント（`agents/{agent-name}/README.md`）を読む
4. featureブランチを作成して開発を開始する

