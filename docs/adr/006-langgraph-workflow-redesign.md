# ADR-006: LangGraph ワークフロー再設計 — 多言語対応・受付統一・ルーティング最適化

## Status

Accepted (2026-03-29)

## Context

Engineer Cafe Navigator のバックエンドは LangGraph Supervisor Pattern を採用している。kiosk デプロイ（2026-04-11目標）に向けて、3つのソース（Codex CLI アーキテクチャレビュー、内部ワークフロー分析、Web技術調査）から以下の構造的問題が特定された：

### 特定された問題

1. **ルーティング効率**: memory_loader が全クエリに対して実行され、キーワード fast-path の効果を相殺（Codex HIGH）
2. **多言語RAG不整合**: 英語クエリ翻訳後も `language` パラメータが元のまま → テキストフォールバックが空振り（Codex HIGH）
3. **Reception二重実装**: reception_workflow.py と main_workflow.py 内 inline が並立し、ルーティングマッピングが不一致（Codex MEDIUM-HIGH）
4. **日本語ナレッジのみ**: 英語ユーザーの検索精度が構造的に劣化

## Decision

LangGraph ワークフローを再設計し、キーワード fast-path 導入・Reception 統一・多言語 RAG 修正により、kiosk デプロイ（2026-04-11）に必要な応答速度と多言語品質を確保する。

以下の変更を Phase 1（4/11前）で実施する。D-RAG は Phase 2 に移行。

### D1: キーワード Fast-Path のグラフ分岐（Reception gate 付き）

- グラフ構造を以下に変更:
  ```
  START → reception_check → {
    active_reception: memory_loader → orchestrator,
    no_reception: keyword_router → {
      fast: agent直行,
      normal: memory_loader → orchestrator
    }
  }
  ```
- **Reception gate**: キーワードルーティングの前に reception 状態を必ず確認する
  - アクティブな reception セッション中 → 常に memory_loader → orchestrator 経由（fast-path スキップ）
  - Mixed-intent greeting（例: "hello, wifi password?"） → normal path
  - 代名詞・照応クエリ（例: "それについて教えて"） → normal path（コンテキスト必要）
  - メモリ関連クエリ → normal path
  - Topic guard 必要なクエリ → normal path
- キーワードマッチで確定できるクエリ（WiFi、営業時間、料金等）は memory_loader/RAG をスキップ
- 根拠: LangGraph の conditional_edges パターン

### D2: Reception ワークフロー一本化

現在 Reception は以下の3箇所に分散実装されている:

1. **main_workflow.py inline**: `_handle_reception_gate`, `_handle_reception_inline` による inline 処理
2. **reception_workflow.py**: 独立した StateGraph による standalone 実装
3. **backend/api/reception.py**: API フロー（PurposeFlowService, ReceptionHandoffService を使用）

統一方針:
- LangGraph subgraphs を使用し、Reception を first-class graph component として統合
- main_workflow.py 内の inline reception handler を削除
- reception_workflow.py を subgraph として MainWorkflow に組み込み
- `consultation` のルーティング先を `general_knowledge` に統一（reception_workflow.py 側を正とする）
- PurposeFlowService と ReceptionHandoffService は統一アーキテクチャ内で保持
- 状態遷移を明確にドキュメント化: `initiated → greeting → purpose_hearing → routing → completed`（ambiguous-purpose ループを含む）
- 根拠: DDD Bounded Context原則 — Reception は独立したドメイン、LangGraph Subgraphs パターン

### D3: 多言語RAG修正（tRAG パターン — ja/en/zh/ko）

システムは既に ja/en/zh/ko サポートを宣言している（reception.py L256, purpose_flow_service.py L21）。D3 はこの4言語すべてに対応する。

#### D3a: 即時バグ修正（Phase 1）

- 翻訳済みクエリの RAG 呼び出し時に `language="ja"` を明示的に設定（全非日本語言語共通）
- テキストフォールバック検索の言語フィルタを修正
- 根拠: tRAG (Translation RAG) パターン

#### D3b: 多言語戦略拡充（Phase 1）

- Top-20 FAQ を en/zh/ko でナレッジベースに追加（既存マークダウンから抽出）
- en/zh/ko クエリハンドリングの統一（翻訳 → ja RAG → 元言語で回答）
- 多言語 RAGAS 評価を実施（en/zh/ko 各言語での answer_correctness 計測）

### D4: CRAG retrieval grading 強化 + bilingual FAQ 拡張（Phase 1）

- 既存の CRAG スタイル grading（enhanced_rag.py L250）を活用し、retrieval quality の判定を強化
- bilingual FAQ エントリを knowledge_base に追加
- 多言語 RAGAS 評価を実施（D3b と連携）
- 根拠: 既存 CRAG パターンの段階的強化

### D5: D-RAG（弁証法RAG）導入 — Phase 2（post 4/11）

- 日本語RAG結果と英語クエリの整合性をクロスバリデーション
- LangGraph ノードとして実装: `rag_validator` ノードが日英の検索結果を比較・統合
- Self-RAG の自己反省メカニズムとの組み合わせを検討
- 根拠: Dialectic RAG（+12.9% accuracy improvement — 仮説、本プロジェクトでの検証未実施）

## Consequences

### Positive

- kiosk レスポンス速度向上（FAQ 50-70% が fast-path 対象 — 仮説、計測で検証予定）
- 多言語ユーザー（en/zh/ko）の回答品質改善
- Reception フローの一貫性確保（3実装 → subgraph 1本化）
- テスト可能性の向上（Reception が独立ドメインとして分離）

### Negative

- グラフ構造変更に伴うリグレッションリスク
- 既存テストの修正が必要
- D-RAG は Phase 2 に延期 → 多言語クロスバリデーションの恩恵は 4/11 には間に合わない

### Risks

- memory_loader スキップ時に会話コンテキストが欠落するケースの考慮が必要
- Reception gate 判定の精度（mixed-intent の分類ミス）
- 多言語 FAQ の品質（翻訳精度の担保）

### Acceptance Criteria (Phase 1 — 2026-04-11)

- Fast-path リグレッションテストが全パス
- Reception 状態遷移テストが全パス（initiated → greeting → purpose_hearing → routing → completed）
- 多言語 retrieval テストが全パス（en/zh/ko クエリで正しい結果を返す）
- レイテンシ: FAQ クエリ < 500ms、通常クエリ < 3s
- RAGAS answer_correctness >= 0.85（日本語）、>= 0.75（英語）

## Implementation Notes

What was actually implemented versus the original plan, as of 2026-04-13:

### D1: キーワード Fast-Path — DONE (#377)

- `main_workflow.py` に `reception_check` と `keyword_router` を追加
- グラフ構造を `START → reception_check → { active_reception: memory_loader, no_reception: keyword_router }` に変更
- FAQ 系クエリは `keyword_router` から agent に直行し、mixed-intent / anaphora / memory 依存クエリは `memory_loader` にフォールバック
- fast-path でも最低限の会話履歴は保存するようにした

### D2: Reception ワークフロー一本化 — DONE (PR #390)

- `main_workflow.py` 内の `_handle_reception_gate()` と `_handle_reception_inline()` を削除（約200行削減）
- `reception_workflow.py` を callable subgraph として昇格
- 新関数 `workflow_state_to_reception_state()`、`reception_state_to_workflow_result()`、`invoke_reception_subgraph()` を追加
- `api/reception.py` はシングルトンワークフローを使用（`asyncio.Lock` で保護）
- `consultation` のルーティング先を `general_knowledge` に統一（plan 通り）

### D3: 多言語RAG修正（tRAG） — DONE (PR #389) + 暫定拡張 (PR #424)

- 翻訳ガード変更: 英語クエリのみ日本語に翻訳してRAGを呼び出す（zh/ko はクロスリンガル埋め込みを直接使用し翻訳をスキップ）
- `text_fallback_search` は常に `"ja"` でフィルタ（KB は日本語のみのため）
- エンティティラベルとアドバイステンプレートを en/zh/ko に対応
- 中国語・韓国語のグリーティングキーワードを追加
- 新規テスト30件追加

**暫定拡張 (PR #424, 2026-04-11)**: 韓国語RAGのほぼ全滅（38/38失敗）を受け、ko/zh クエリにもLLM翻訳（OpenRouter Gemini Flash）を暫定追加。クロスリンガル埋め込みのみでは精度不足と判明。正式方針はSTT provider比較（Issue #425）と合わせて再検討。

### D4: CRAG 強化 + bilingual FAQ — Partial (PR #391)

- 多言語 RAGAS ベンチマークを追加: `ground_truth.json` に30件（en×10、zh×10、ko×10）
- 新評価ランナー `run_multilingual_eval.py`（言語別スコア分解）
- bilingual FAQ エントリの knowledge_base への追加は未実施

### Browser / Live E2E Verification — DONE (#139, PR #455 / #456)

- Playwright merge gate が `smoke.spec.ts`、`reception-flow.spec.ts`、`webgl-fallback.spec.ts` を実行
- `voice-live.spec.ts` がブラウザから live backend に対して `STT -> /api/qa -> /api/chat -> TTS` の round-trip を検証
- backend 側にも live LangGraph scenario / voice round-trip テストを追加し、UI 経由と API 経由の両方でワークフロー確認を行う体制にした

### D5: D-RAG — Deferred (Phase 2, post 4/11)

計画通り延期。日英クロスバリデーションは Phase 2 で対応。

## References

- LangGraph 1.0 GA: https://changelog.langchain.com/announcements/langgraph-1-0-is-now-generally-available
- LangGraph Conditional Edges: https://langchain-ai.github.io/langgraph/concepts/low_level/#conditional-edges
- LangGraph Subgraphs: https://docs.langchain.com/oss/python/langgraph/use-subgraphs
- tRAG Pattern: https://arxiv.org/html/2407.01463v1
- D-RAG (Dialectic RAG): https://arxiv.org/html/2504.04771v1
- Self-RAG: https://arxiv.org/html/2310.11511v1
- Language Drift in Multilingual LLMs: https://arxiv.org/html/2511.09984v1
- RAGAS Evaluation: https://docs.ragas.io/
- DDD for Multi-Agent AI: https://www.jamescroft.co.uk/applying-domain-driven-design-principles-to-multi-agent-ai-systems/

## Related Issues

- Epic: #376
- Sub Issues: #377, #378, #379, #380, #381, #382
- #117 (受付フロー統合)
- #138 (多言語品質改善)
- #139 (E2Eテスト, closed 2026-04-13)
- #367 (Wave 6計画)
