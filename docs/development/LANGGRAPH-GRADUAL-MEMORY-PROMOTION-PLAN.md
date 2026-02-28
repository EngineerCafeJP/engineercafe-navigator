# LangGraph 段階昇格メモリ実装計画（知識ラグ・口調適応）

更新日: 2026-02-26
対象: Engineer Cafe Navigator 2025（LangGraphベース AI受付）

## 1. 目的

本計画は、現在のAI受付に対して以下を追加するための実装計画です。

- 3分単位の会話履歴を起点にした段階的メモリ昇格（短期→候補→長期）
- 新規情報を即時に最優先化しない「知識ラグ」設計
- ユーザーごとの口調/関係性の漸進的適応
- 既存のLangGraphワークフローを壊さない段階導入

## 2. 結論（先に要点）

ユーザー提案の方向性は妥当であり、現行実装とも整合します。ただし、実運用では次を分離して設計する必要があります。

- `事実系（営業時間・イベント・設備・料金）`: ラグを最小化し、RAG/外部データを優先
- `関係性系（呼称・好み・会話スタイル）`: 段階昇格と時間減衰を適用

この分離を守れば、親しみやすさを上げつつ、受付としての正確性を維持できます。

## 3. 外部根拠（一次情報・最新知見）

### 3.1 RAGの前提（パラメトリック知識 + 外部メモリ）

RAG論文は、パラメトリック記憶（モデル内部）と非パラメトリック記憶（外部知識）を組み合わせる構成を明示しています。今回の「会話から徐々に外部メモリへ昇格」は、この前提と整合します。

- Lewis et al., 2020 (RAG): https://arxiv.org/abs/2005.11401

### 3.2 「知識ラグ」を作る技術要素

- LangChainのTime-Weighted Retrieverは、`semantic relevance + recency + other scores` の合成で検索順位を調整でき、最新情報が常に最上位になる挙動を緩和できます。
  - https://python.langchain.com/docs/how_to/time_weighted_vectorstore/
- Pineconeのfreshness文書は、分散構成・非同期反映により最終的整合性を前提にした挙動が起こりうることを示しており、設計上「即時反映前提にしない」思想と相性が良いです。
  - https://docs.pinecone.io/guides/index-data/check-data-freshness

### 3.3 LangGraphの実装ベストプラクティス（最新）

- `Thinking in LangGraph`:
  - 状態は生データ中心に保つ（prompt向け整形を状態に固定しない）
  - ノードは明確な責務を持たせる
  - エラーと失敗モードを前提に設計する
  - https://docs.langchain.com/oss/python/langgraph/thinking-in-langgraph
- `Persistence / Memory`:
  - スレッド単位の短期状態（checkpointer）と、スレッド横断の長期記憶（Store）を分離して扱える
  - `runtime.store` 経由でノード内からStoreを利用できる
  - https://docs.langchain.com/oss/python/langgraph/persistence
  - https://docs.langchain.com/oss/python/langgraph/memory
- `LangSmith Test`:
  - 本番前に失敗モードや回帰を評価するテスト戦略が必要
  - https://docs.langchain.com/langsmith/test

### 3.4 参考（旧LangGraphドキュメントURL / リポジトリ内で利用中）

現在のコードコメント・ドキュメントには旧URL（`langchain-ai.github.io`）が残っています。移行時の歴史的参照として保持しつつ、新規設計は現行 `docs.langchain.com` を正として扱います。

- `backend/workflows/main_workflow.py`
- `backend/utils/checkpointer.py`
- `backend/utils/store.py`

## 4. 現状実装の把握（このリポジトリの事実）

### 4.1 すでにあるもの（強い土台）

1. LangGraphワークフローに `memory_loader` と `format_response` があり、前後処理の差し込み点が明確
- `backend/workflows/main_workflow.py:127`
- `backend/workflows/main_workflow.py:128`
- `backend/workflows/main_workflow.py:130`
- `backend/workflows/main_workflow.py:151`
- `backend/workflows/main_workflow.py:159`

2. `memory_loader` で短期会話コンテキスト取得 + RAGプリフェッチ + 長期記憶ロードが既に実装済み
- `backend/workflows/main_workflow.py:235`
- `backend/workflows/main_workflow.py:248`
- `backend/workflows/main_workflow.py:267`
- `backend/workflows/main_workflow.py:308`
- `backend/workflows/main_workflow.py:321`

3. `format_response` で会話保存 + 長期記憶抽出/保存の後段処理が既に実装済み
- `backend/workflows/main_workflow.py:593`
- `backend/workflows/main_workflow.py:606`
- `backend/workflows/main_workflow.py:612`

4. LangGraph `checkpointer` / `store` を compile 引数で受けられる構造になっている（拡張しやすい）
- `backend/workflows/main_workflow.py:161`
- `backend/workflows/main_workflow.py:163`
- `backend/workflows/main_workflow.py:165`
- `backend/workflows/main_workflow.py:169`

5. Store/Checkpointer の基盤ユーティリティが既にある（Supabase PostgreSQL）
- `backend/utils/store.py:15`
- `backend/utils/store.py:29`
- `backend/utils/store.py:57`
- `backend/utils/checkpointer.py:17`
- `backend/utils/checkpointer.py:40`
- `backend/utils/checkpointer.py:78`

### 4.2 既にあるが未活用/不足している点（今回の主対象）

1. 長期記憶抽出はあるが、現在は単発抽出→即保存寄り
- `backend/utils/memory_extractor.py:20`
- `backend/utils/memory_extractor.py:39`
- `backend/utils/memory_extractor.py:61`

2. `long_term_memory` はワークフローからGKAへ受け渡しているが、GKA本体で活用されていない
- 受け渡し側: `backend/workflows/main_workflow.py:547`, `backend/workflows/main_workflow.py:549`
- GKAシグネチャ: `backend/agents/general_knowledge_agent.py:79`
- 実利用なし（`answer_general_query`に渡されていない）: `backend/agents/general_knowledge_agent.py:84`

3. バックエンド短期メモリは「3分窓」ではなく、`conversation_sessions` の active 判定 + セッション全体取得
- `backend/utils/memory_helper.py:54`
- `backend/utils/memory_helper.py:132`
- `backend/utils/memory_helper.py:215`

4. フロント側には「3分短期メモリ」の設計思想が残っているが、バックエンド主導運用と完全一致していない
- `frontend/src/lib/simplified-memory.ts:7`
- `frontend/src/lib/simplified-memory.ts:23`
- `frontend/src/lib/simplified-memory.ts:172`

## 5. 非破壊導入できる理由（論拠）

### 5.1 差し込み位置が既存ノードに存在し、責務も一致している

- `memory_loader` は「読む/前処理」
- `format_response` は「保存/後処理」

よって、段階昇格の追加は新ノードを増やさずに「内部処理の拡張（additive change）」として導入できます。

### 5.2 既存ワークフローは失敗を許容する設計・実装になっている

`store_message` 失敗時もワークフロー継続するコードパスが明示されています。

- `backend/workflows/main_workflow.py:253`
- `backend/workflows/main_workflow.py:599`
- `backend/workflows/main_workflow.py:627`

### 5.3 既存テストが主要な回帰ポイントを既にカバーしている

- メモリロード結果が `state.context.memory` に入る
  - `backend/tests/workflows/test_main_workflow.py:27`
  - `backend/tests/workflows/test_streaming_memory.py:326`
- ユーザー/アシスタントメッセージ保存
  - `backend/tests/workflows/test_main_workflow.py:303`
  - `backend/tests/workflows/test_main_workflow.py:342`
  - `backend/tests/workflows/test_streaming_memory.py:267`
  - `backend/tests/workflows/test_streaming_memory.py:296`
- 保存失敗でもワークフロー継続
  - `backend/tests/workflows/test_main_workflow.py:374`
  - `backend/tests/workflows/test_streaming_memory.py:372`
- ワークフロー初期化・checkpointer利用
  - `backend/tests/workflows/test_main_workflow.py:170`

上記に加え、今回の変更では新規テストを追加して回帰面を強化します（後述）。

## 6. 設計方針（本計画の中核）

### 6.1 メモリを4層に分離する

1. `短期（Immediate / Session Window）`
- 直近会話を即時参照
- 回答品質に直結
- ここはラグを入れない

2. `候補（Candidate / Staging）`
- 3分窓ごとの要約・抽出結果を一旦保管
- まだ人格/長期知識には反映しない

3. `長期（Promoted / Durable）`
- 繰り返し出現・明示要求・高信頼で昇格
- スレッド横断で利用

4. `スタイルプロファイル（Relational / Tone Profile）`
- 呼称、丁寧さ、説明長、雑談許容度など
- 変化速度に上限をつける

### 6.2 「事実」と「関係性」を分離する

`事実系` と `関係性系` を同じ昇格ルールにしないことが重要です。

- `事実系（店舗情報・イベント・設備）`
  - ソース優先順位: 外部データ / RAG > 会話メモリ
  - 更新ラグは極小
  - 会話メモリは補助的文脈に限定
- `関係性系（好み・呼び方・口調）`
  - 候補化→昇格→減衰の対象
  - 誤学習防止のため段階昇格

### 6.3 ラグの対象を明示する

今回の「知識ラグ」は、原則として以下に限定します。

- ユーザー属性・嗜好・会話スタイル
- 非クリティカルな会話的記憶

以下には適用しません（または別ルール）。

- 営業時間、イベント日程、料金、設備可用性などの運用事実

## 7. 目標アーキテクチャ（LangGraph適用形）

### 7.1 変更の基本戦略

既存グラフのトポロジーは維持し、まずは `memory_loader` / `format_response` 内部を拡張します。

- Phase 1-2: グラフ構造は変更しない（非破壊優先）
- Phase 3以降: 必要があれば独立ノード化（観測性・再実行性改善）

### 7.2 データの流れ（提案）

1. `memory_loader`
- 短期メモリ取得（現行）
- 長期メモリ取得（現行）
- 今後追加: `candidate_summary` / `style_profile` の読み込み（feature flagでON）

2. 各ドメインエージェント
- 事実系回答では長期メモリの利用を限定（優先度低）
- 一般知識/雑談系でのみ関係性メモリの反映を強める

3. `format_response`
- 会話保存（現行）
- 長期記憶抽出（現行）
- 今後追加: 候補メモリ生成イベントをenqueue（同期処理は最小化）

4. バックグラウンドPromoter（新規）
- 3分窓の要約
- 候補抽出
- 重複統合/矛盾判定
- 昇格判定
- スタイルプロファイル更新

### 7.3 LangGraph Storeのnamespace分離（提案）

既存 `("visitor_memories", user_id)` を維持しつつ、用途ごとにnamespaceを分けます。

- `("visitor_memories", user_id)` : 昇格済み長期メモリ（現行互換）
- `("visitor_memory_candidates", user_id)` : 候補メモリ（新規）
- `("visitor_style_profile", user_id)` : 口調/関係性プロファイル（新規）
- `("visitor_memory_events", user_id)` : 抽出イベントログ（監査用、任意）

## 8. 段階昇格アルゴリズム（実装仕様）

### 8.1 3分窓バッチ（候補化）

トリガー（優先順）

1. セッション継続中に3分経過
2. セッション終了/離脱
3. 発話数閾値（例: 8往復）到達

処理

1. セッション窓の会話を要約（raw transcriptは保持）
2. 候補メモリを抽出
3. 各候補にメタデータ付与

候補メモリ例

- `type`: `visitor_preference`, `visitor_name`, `explicit_remember`, `style_signal`
- `content`
- `confidence`
- `evidence_turn_ids`
- `window_start`, `window_end`
- `recency_score`
- `sensitivity`（PII/非PII）
- `volatility`（high/medium/low）

### 8.2 昇格判定（候補→長期）

昇格条件（例）

- 明示的記憶要求 (`explicit_remember`) かつ安全性OK
- 同種候補が複数窓で再出現
- 信頼度 >= 閾値（型別閾値）
- 矛盾検出に未抵触

昇格抑制条件

- 単発・曖昧・感情的発言
- 高いPII感度で同意が未確認
- 運用事実と競合（営業時間など）

### 8.3 時間減衰と検索順位制御（知識ラグ）

長期メモリ検索後に、以下の合成スコアで再順位付けします（実装はStore検索後のアプリ層rerankで開始）。

- `semantic_score`
- `recency_weight`（新しすぎる情報を即1位固定しない）
- `repeat_count_weight`
- `explicitness_weight`（「覚えて」加点）
- `stability_weight`（複数窓で一貫）

備考

- LangChainのTime-Weighted Retrieverの考え方を参考にするが、初期実装は既存Store/検索に合わせて自前rerankで十分
- ベクタDB導入/移行時に同等ロジックへ移植可能

## 9. 口調・関係性の適応仕様（漸進的）

### 9.1 変える対象

- 呼称（名前呼び / さん付け）
- 丁寧さ（ですます度）
- 応答長（短め/標準/詳しめ）
- 雑談比率（業務集中/少し雑談可）
- 絵文字/感嘆の有無（基本OFF推奨）

### 9.2 変えない対象

- 事実の正確性
- 安全ルール
- 禁止事項
- 施設/運営ポリシーに関わる表現

### 9.3 適応ルール（急変防止）

- 1セッションでの変化量を制限
- 新しいスタイル候補は `candidate` に蓄積し、即反映しない
- 昇格済みプロファイルでも減衰/再評価を行う

## 10. 実装フェーズ（非破壊優先）

### Phase 0: 計測・フラグ整備（先行）

目的: 本番挙動を変えずに観測可能にする

実装

- feature flag追加（全てデフォルトOFF）
  - `ENABLE_MEMORY_CANDIDATES`
  - `ENABLE_MEMORY_PROMOTION`
  - `ENABLE_STYLE_PROFILE`
  - `ENABLE_LONG_TERM_MEMORY_RERANK`
- ログ/メトリクス追加（抽出件数、昇格件数、latency）

破壊性

- なし（コードパスは既存維持）

### Phase 1: 候補メモリのShadow Write

目的: 長期反映なしで候補抽出品質を測る

実装

- `backend/utils/memory_extractor.py` を拡張し、`candidate` 用の型・メタデータを追加
- `format_response` 後段で candidate namespace へ保存（失敗時warn継続）
- 既存 `visitor_memories` への直接保存は現行維持（互換のため）

破壊性

- 低（additive write）

### Phase 2: 3分窓バッチPromoter導入

目的: 即時保存から段階昇格へ移行

実装

- 新規サービス `backend/services/memory_promoter.py`（提案）
- 窓集約 → 候補統合 → 昇格判定
- `visitor_memories` への書き込みをPromoter経由へ段階移行

移行方法

- まず二重書き（旧直書き + promoter結果比較）
- 差分監視後に旧直書きを停止

破壊性

- 低〜中（ただしflagで制御）

### Phase 3: Retrieval Rerank（知識ラグ反映）

目的: 新規情報の即時最優先化を避ける

実装

- `memory_loader` の `runtime.store.asearch(...)` 結果を再順位付け
- 型別ルール（事実系はラグ弱、関係性系はラグ強）
- `context.long_term_memory` は既存キー名維持

破壊性

- 低（返却形式を変えない）

### Phase 4: スタイルプロファイル適応

目的: 口調の段階的変化

実装

- `visitor_style_profile` 読み込みを `memory_loader` に追加
- プロンプト構築層に `style_profile` を入力（まずGKAのみ）
- 変化量制限/減衰を実装

破壊性

- 中（回答文面に影響）
- カナリア運用必須

## 11. 既存実装を壊さないための具体策（証拠付き）

### 11.1 互換インターフェースを維持する

維持対象

- `state["context"]["memory"]`
- `state["context"]["knowledge_results"]`
- `state["context"]["long_term_memory"]`
- `format_response` の戻り値 `{"messages": ...}`

根拠

- 既存コードがこれらのキーを前提に処理している
  - `backend/workflows/main_workflow.py:321`
  - `backend/workflows/main_workflow.py:325`
  - `backend/workflows/main_workflow.py:327`
  - `backend/workflows/main_workflow.py:634`

### 11.2 グラフ構造を初期フェーズで変更しない

根拠

- 現行のSupervisor Patternのノード/エッジは既にテスト前提
  - `backend/workflows/main_workflow.py:119`
  - `backend/workflows/main_workflow.py:141`
  - `backend/tests/workflows/test_main_workflow.py:145`

### 11.3 失敗時warn継続パターンを踏襲する

根拠

- 現行が「メモリ失敗でも応答継続」を採用しており、ユーザー体験上の可用性を優先している
  - `backend/workflows/main_workflow.py:253`
  - `backend/workflows/main_workflow.py:599`
  - `backend/workflows/main_workflow.py:627`
  - `backend/tests/workflows/test_main_workflow.py:374`
  - `backend/tests/workflows/test_streaming_memory.py:372`

## 12. テスト計画（回帰 + 品質）

### 12.1 単体テスト（必須）

- `memory_promoter` の昇格判定
  - 明示的記憶要求で昇格
  - 単発曖昧発言は昇格しない
  - 矛盾候補があると抑制
- `reranker`
  - 新規情報が必ずしも1位にならない
  - 明示的記憶要求は加点される
- `style_profile`
  - 変化量上限が効く
  - 減衰が効く

### 12.2 ワークフロー統合テスト（既存に追加）

- `memory_loader` が候補/スタイル取得に失敗しても継続
- `format_response` のcandidate保存失敗でも `messages` を返す
- `long_term_memory` のキー形式互換を維持

### 12.3 評価テスト（LangSmith/シナリオ）

- 正答率（営業時間/イベント）劣化なし
- 文脈継続性（連続質問）
- 親しみやすさ（口調の一貫性）
- 誤記憶率（存在しない嗜好を記憶する率）

## 13. 観測指標（運用）

最低限のKPI

- `memory_candidate_count`
- `memory_promotion_count`
- `promotion_accept_rate`
- `memory_retrieval_hit_rate`
- `fact_answer_regression_rate`（営業時間等）
- `style_profile_applied_rate`
- `p95_response_latency_ms`（Phase 3以降は特に監視）

アラート条件（例）

- 事実系正答率が基準より低下
- p95レイテンシが閾値超え
- 誤記憶率上昇

## 14. 既知リスクと対策

1. 誤記憶（false memory）
- 対策: 段階昇格、明示要求優先、矛盾検出、減衰

2. 事実汚染（会話メモリがRAG事実を上書き）
- 対策: 事実系はRAG/外部ソース優先、メモリは補助扱い

3. レイテンシ増加
- 対策: Phase 1はshadow writeのみ、Promoterを非同期化

4. プライバシー/PII
- 対策: 保存対象の明示、型別保存ポリシー、PII感度フラグ、削除API設計

## 15. 実装タスク一覧（初回実装の具体化）

1. `feature flags` と設定値を追加（デフォルトOFF）
2. `candidate memory schema` を定義（Store value構造）
3. `memory_extractor` を候補化対応へ拡張（型・evidence・volatility）
4. `format_response` にcandidate shadow write追加（warn継続）
5. `memory_loader` にoptional rerankフック追加（flag OFFでno-op）
6. `memory_promoter`（新規）を実装
7. `style_profile` 読み書きユーティリティ実装
8. GKAに `long_term_memory/style_profile` の実利用を追加（段階的）
9. テスト追加（unit/workflow/integration）
10. カナリア運用と評価基準の文書化

## 16. 参考資料（調査日: 2026-02-26）

### 外部（一次情報）

- RAG (Lewis et al., 2020): https://arxiv.org/abs/2005.11401
- LangGraph Thinking in LangGraph: https://docs.langchain.com/oss/python/langgraph/thinking-in-langgraph
- LangGraph Persistence: https://docs.langchain.com/oss/python/langgraph/persistence
- LangGraph Memory: https://docs.langchain.com/oss/python/langgraph/memory
- LangSmith Test: https://docs.langchain.com/langsmith/test
- LangChain Time-Weighted Retriever: https://python.langchain.com/docs/how_to/time_weighted_vectorstore/
- Pinecone Freshness / Eventual Consistency: https://docs.pinecone.io/guides/index-data/check-data-freshness

### 旧LangGraph参照URL（歴史的参照）

- https://langchain-ai.github.io/langgraph/concepts/multi_agent/
- https://langchain-ai.github.io/langgraph/concepts/persistence/

---

## 17. この計画での判断（明示）

- あなたの提案は正しい方向で、現行システムにも実装可能
- ただし、`知識（事実）` と `関係性（口調/親しみ）` を分離しないと受付品質が落ちる
- 最初は「非破壊・観測可能・flag制御」の3原則で導入する

