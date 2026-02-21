# Plans.md - Engineer Cafe Navigator

> 最終更新: 2026-02-15
> モード: 2-Agent (Cursor PM + Claude Code Worker)

---

## 現在のステータス

| 項目 | 状態 |
|------|------|
| **フェーズ** | ✅ 全フェーズ完了 (A/B/C/D/E) |
| **CI/CD** | ✅ グリーン |
| **テスト** | ✅ 852 passed (25 skipped), E2E 10/10 PASS (KW率100%) |
| **オープン PR** | #78 (RouterAgent削除 + クリーンアップ) |
| **エージェント数** | 8種（RouterAgent削除済み、ClarificationAgent・MemoryAgent吸収済み） |

---

## アーキテクチャ決定事項（2026-02-15 PM承認済み）

| カテゴリ | 決定 | 要点 |
|----------|------|------|
| **メモリ** | 2層構成 (Session短期 + pgvector長期) | LangGraph Store不採用、knowledge_base拡張 |
| **RAG** | Hierarchical RAG (pgvector) | document→section→chunk 3層、Adaptive RAG |
| **インジェスション** | LLM自動分類 + 5000字制限撤廃 | 重複排除もLLM自動判定 |
| **検索優先度** | コンテキスト駆動 + RAGキャッシュ | memory_loader二重検索解消 |
| **評価** | RAGAS (メモリ再設計後) | Faithfulness, Context P/R, CI/CD統合 |
| **Web検索** | Tavily移行 | Gemini Direct API廃止、結果はRAG非保存 |
| **実装順序** | A+D並列 → B → C | エージェント統合はメモリ完了後 |

> 詳細: [docs/architecture/HIERARCHICAL-RAG-ARCHITECTURE.md](docs/architecture/HIERARCHICAL-RAG-ARCHITECTURE.md)

---

## 実装ロードマップ

### Phase A: メモリシステム再設計 ✅ COMPLETE

| タスク | 状態 | 依存 |
|--------|------|------|
| A-1: knowledge_base テーブル拡張 (parent_id, chunk_level等) | ✅ 完了（Supabase適用済み） | - |
| A-2: Hierarchical検索RPC関数作成 | ✅ 完了（A-1マイグレーション内に含む） | A-1 |
| A-3: session-based TTL に memory_helper 書き換え | ✅ 完了（セッション境界ベース） | - |
| A-4: memory_loader RAGキャッシュ（二重検索解消） | ✅ 完了（RAGキャッシュ実装済み） | A-3 |
| A-5: EnhancedRAGSearch Hierarchical対応 | ✅ 完了（Hierarchical RAG対応済み） | A-2 |
| A-6: Tavily Web Search 移行 | ✅ 完了（Tavily移行済み） | - |

### Phase D: RAGAS評価（Phase Aと並列） ✅ COMPLETE (D-1/D-2/D-3)

| タスク | 状態 | 依存 |
|--------|------|------|
| D-1: ground_truth データセット作成（60件+新規） | ✅ 完了 | - |
| D-2: RAGAS評価パイプライン構築 | ✅ 完了 | D-1 |
| D-3: CI/CD統合（GitHub Actions） | ✅ 完了（ragas-evaluation.yml + CI mode） | D-2 |

### Phase B: YAML分離 + Hierarchical Chunking ✅ COMPLETE

| タスク | 状態 | 依存 |
|--------|------|------|
| B-1: Hierarchical チャンキングエンジン (loader.py) | ✅ 完了（391行、24テスト、レビュー修正済み） | A-1 |
| B-2: LLM自動分類パイプライン | ✅ 完了（classifier.py + 18テスト、セキュリティ対策済み） | B-1 |
| B-3: seed_knowledge.py → カテゴリ別YAML分離 | ✅ 完了（7ファイル、60エントリ、110テスト） | B-1 |
| B-3p: YAML Schema設計 (schema.py) | ✅ 完了（18テスト） | - |

### Phase C: 動的検索優先度 ✅ COMPLETE (C-1/C-2)

| タスク | 状態 | 依存 |
|--------|------|------|
| C-1: コンテキスト駆動優先度エンジン | ✅ 完了 | A-5 |
| C-2: Adaptive RAG ルーティング | ✅ 完了（context_signals配線 + 適応的Web検索、8テスト） | C-1 |

### Phase E: エージェント統合（Phase A完了後）

| タスク | 状態 | 依存 |
|--------|------|------|
| E-1: ClarificationAgent → OrchestratorAgent 統合 | ✅ 前倒し完了（テンプレート化+インライン処理） | - |
| E-2: MemoryAgent → GeneralKnowledgeAgent 統合 | ✅ 完了（GKA統合済み） | A |
| E-3: エージェント構造最適化（Singleton化） | ✅ 前倒し完了 | - |

---

## エージェント実装状況（8種）

| エージェント | 系統 | 備考 |
|-------------|------|------|
| orchestrator-agent | 統括 | RouterAgent機能統合済み |
| business-info-agent | 実務系 | |
| event-agent | 実務系 | |
| facility-agent | 実務系 | |
| slide-agent | 実務系 | |
| general-knowledge-agent | 実務系 | Web検索Tavily移行済み、メモリクエリ処理統合済み |
| ~~clarification-agent~~ | 音声系 | ✅ ワークフロー吸収済み（voice_agentのみ参照） |
| voice-agent | 音声系 | |
| character-control-agent | UI系 | |

レビュー中: ocr-agent
統合済み: ~~memory-agent~~ → general-knowledge-agent (#55)
削除済み: ~~router-agent~~ (#78, -793行)

---

## チーム編成

| チーム | 担当者 | 主なタスク |
|--------|--------|-----------|
| 実務系統括記憶 | テリスケ | Supabase統合、Memory/RAG再設計 |
| 音声系 | Jun, Chie, たけがわ | STT/TTS連携、音声フロー |
| OCR系 | けいてぃー, たけがわ | 画像認識→ルーター連携 |
| フロント系 | takegg0311, 中村 | VRM制御、API移行 |

---

## CI/CD チェックリスト

- [ ] `ruff check .` / `black --check .` (backend)
- [ ] `pnpm lint` / `pnpm typecheck` / `pnpm build` (frontend)
- [ ] RAGAS評価スコア確認（Phase D完了後に追加）

---

## リファレンス

- [アーキテクチャ設計書](docs/architecture/HIERARCHICAL-RAG-ARCHITECTURE.md)
- [エンジニアカフェ公式情報](docs/reference/engineer-cafe-reference.md)
- [決定事項 SSOT](.claude/memory/decisions.md)
- [完了済みフェーズ](.claude/memory/archive/Plans-archive.md)
