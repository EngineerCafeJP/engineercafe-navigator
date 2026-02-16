# Hierarchical RAG アーキテクチャ設計書

> 承認日: 2026-02-15 (PM承認済み)
> ステータス: 設計確定、実装未着手

## 技術選定: pgvector（Supabase PostgreSQL拡張）

LangGraph Store 不採用理由:
- `InMemoryStore` はプロセス再起動でデータ消失（揮発性）
- Python SDK に永続Store未実装（LangGraph Platformのみ）
- RAGAS の `contexts: List[str]` との互換性が低い
- knowledge_base（pgvector）との二重管理が発生

## DBスキーマ拡張（knowledge_base テーブル）

```sql
-- 新規カラム（既存テーブルに追加）
ALTER TABLE knowledge_base ADD COLUMN parent_id UUID REFERENCES knowledge_base(id);
ALTER TABLE knowledge_base ADD COLUMN chunk_level VARCHAR(20) DEFAULT 'document';
  -- 'document' | 'section' | 'chunk'
ALTER TABLE knowledge_base ADD COLUMN chunk_index INT DEFAULT 0;
ALTER TABLE knowledge_base ADD COLUMN token_count INT;
```

## 階層構造イメージ

```
document (営業時間)                    ← chunk_level='document'
  ├── section (エンジニアカフェ営業時間)  ← chunk_level='section', parent_id=↑
  │     ├── chunk (平日スケジュール)     ← chunk_level='chunk', parent_id=↑
  │     └── chunk (休日スケジュール)     ← chunk_level='chunk', parent_id=↑
  └── section (サイノカフェ営業時間)     ← chunk_level='section', parent_id=↑
        ├── chunk (ランチタイム)         ← chunk_level='chunk', parent_id=↑
        └── chunk (バータイム)           ← chunk_level='chunk', parent_id=↑
```

## 2層メモリアーキテクチャ

```
┌──────────────────────────────────────────────────┐
│              Short-term Memory                    │
│  LangGraph AsyncPostgresSaver (Checkpointer)     │
│  - セッション単位の会話状態                       │
│  - セッション境界で自動リセット                   │
│  - 既存 conversation_sessions テーブル活用        │
└──────────────────┬───────────────────────────────┘
                   │ セッション終了時に重要情報を昇格
                   ▼
┌──────────────────────────────────────────────────┐
│              Long-term Memory                     │
│  Supabase pgvector (knowledge_base 拡張)          │
│  - Hierarchical RAG (parent/child chunks)         │
│  - ユーザー学習データも同テーブルに統合            │
│  - RAGAS で品質評価可能                           │
└──────────────────────────────────────────────────┘
```

## Adaptive RAG パイプライン

```
Query → Embedding生成
  │
  ├─[1] Chunk-level 検索 (similarity_threshold=0.35)
  │     top-K chunks を取得
  │
  ├─[2] Parent展開 (Hierarchical Retrieval)
  │     chunk.parent_id → section の content も取得
  │     → より広いコンテキストを確保
  │
  ├─[3] CRAG グレーディング（既存ロジック拡張）
  │     HIGH/MEDIUM/LOW 判定
  │     LOW → Tavily Web Search にフォールバック
  │
  └─[4] コンテキスト構築
        Section + Chunk を統合して LLM に渡す
```

## ナレッジベース構造化（Phase B で実施）

現在: `scripts/seed_knowledge.py` に全60エントリを単一ファイル管理
計画: カテゴリ別YAML/JSONファイルに分離 + Hierarchical チャンキング

```
backend/knowledge/
├── data/
│   ├── general.yaml          # 基本概要、連絡先
│   ├── facilities.yaml       # メインホール、MAKER's、集中スペース、会議室
│   ├── saino_cafe.yaml       # 営業情報、フード、ドリンク、バー
│   ├── community.yaml        # CM相談、Lab、EIC
│   ├── building_history.yaml # 赤煉瓦文化館
│   └── policies.yaml         # 飲食、喫煙、駐車場、駐輪場
├── loader.py                 # YAML読み込み→Hierarchicalチャンキング→Supabase seed
└── schema.py                 # エントリのバリデーションスキーマ
```

## 技術スタック（現在 → 計画）

| レイヤー | 現在 | 計画 |
|----------|------|------|
| **LLM** | OpenRouter (Gemini 3 Flash) | 変更なし |
| **Embedding** | OpenRouter (text-embedding-3-small, 1536d) | 変更なし |
| **Vector DB** | Supabase pgvector (IVFFlat) | Hierarchical RAG拡張 |
| **Short-term Memory** | agent_memory (3min TTL) | LangGraph Checkpointer (session-based) |
| **Long-term Memory** | なし | knowledge_base (pgvector) 統合 |
| **Web Search** | Gemini Direct API (google.generativeai) | **Tavily** |
| **RAG評価** | E2Eキーワードマッチのみ | **RAGAS** (Faithfulness, Context P/R) |
| **ワークフロー** | LangGraph StateGraph + Command | 変更なし |
