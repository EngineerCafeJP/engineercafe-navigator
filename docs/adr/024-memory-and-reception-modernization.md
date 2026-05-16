# ADR-024: Memory & Reception Modernization

## Status

Accepted (2026-05-17) — 実装は次セッション以降。本 ADR は設計合意の固定版。

## Context

ADR-023 (Semantic Router + Critic node) はルーティング層の肥大化を解くが、2026-05-17 に行った GCP Cloud Logging 17 日分（2026-05-01〜2026-05-17, n≈2,000 chat_response events）と静的コード解析の結果、ルーティング層と**並列で解くべき構造的負債が 3 系統**存在することが判明した。

詳細な事実調査は [`docs/plans/post-adr023-investigation-2026-05-17.md`](../plans/post-adr023-investigation-2026-05-17.md) を参照。本 ADR はそのうちメモリ系統 (A) と受付系統 (B) に絞った決定を記録する。

### 観測された問題（GCP ログ実測）

#### A. メモリ系統

| ID | 問題 | 観測事実 |
|---|---|---|
| A1 | LTM 書き込みが production で 100% skip | `chat_response.ltm_store_write` が 2000/2000 件で "skipped"。setter が production code に存在せず、[`backend/observability/structured_logger.py:170`](../../backend/observability/structured_logger.py:170) のデフォルト "skipped" が常に返っているだけ |
| A2 | agent_memory が O(N) 全件 scan | [`backend/utils/memory_helper.py:267-275`](../../backend/utils/memory_helper.py:267) で 300 行 pull → Python 側 sessionId filter。`value->>'sessionId'` への index 無し |
| A3 | STM が二重保存 | LangGraph Checkpointer (BaseMessage list) と SimplifiedMemoryHelper (agent_memory) が同じ会話を 2 重保存 |
| A4 | memory_extractor / purpose_classifier が regex 拘束 | [`backend/utils/memory_extractor.py`](../../backend/utils/memory_extractor.py) と [`backend/utils/purpose_classifier.py`](../../backend/utils/purpose_classifier.py) が ADR-023 で潰そうとしている router キーワード爆発と同じパターン |
| A5 | 観測性ゼロ | 17 日間で `memory_*` / `reception_transition` / `ltm_promote` event は 0 件 emit |

#### B. 受付系統

| ID | 問題 | 観測事実 |
|---|---|---|
| B1 | `/api/reception/respond` が dead code | 17 日間で 0 calls。frontend proxy ([`frontend/src/app/api/reception/respond/route.ts`](../../frontend/src/app/api/reception/respond/route.ts)) も合わせて死んでいる。実態は [`backend/workflows/main_workflow.py`](../../backend/workflows/main_workflow.py) の `invoke_reception_subgraph()` が全部担当 |
| B2 | `/api/reception/complete` も dead code | 同上、0 calls |
| B3 | `public.users` テーブルが migration に存在しない | [`backend/services/visitor_identification_service.py:239-259`](../../backend/services/visitor_identification_service.py:239) が "users_table_unavailable" を返し続ける。NFC / member 番号で identify を試みると毎回失敗 |
| B4 | reception 完了率 24% | `/api/reception/start` 158 件に対し chat_response で `route=reception` は 38 件 = 76% は途中で諦められている可能性 |

### 2026/05 ベスト・プラクティス対比

| 軸 | 現状 | 2026/05 標準 |
|---|---|---|
| memory backend | session-bound flat DB | Mem0 v2 (2026/04) / Letta / Zep の hierarchical (episodic / semantic / procedural) |
| extraction | regex | LLM extract + semantic dedupe |
| storage hierarchy | flat agent_memory | LangGraph 公式 `("users", id, "facts" / "episodes" / "preferences")` |
| forgetting | session-end で全削 | active forgetting (temporal decay + relevance scoring) |
| search | bigram 自前 | hybrid (semantic + BM25 + entity) |
| benchmark | unit / integration | LoCoMo / LongMemEval (ICLR 2025) |

参考: [Mem0 State 2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026), [Letta Benchmarking](https://www.letta.com/blog/benchmarking-ai-agent-memory), [LangChain long-term memory](https://docs.langchain.com/oss/python/langchain/long-term-memory)

## Decision

メモリと受付の構造的負債を **5 Phase に分割し、ADR-023 と並列実行** する。Phase A0 は ADR-023 Phase 0 に同梱し、observability の二重 PR 化を避ける。Phase A4 では reception/respond dead code を**削除**し、public.users は**作らず visits ベースに統一**する（terisuke 2026-05-17 決定）。

### D1: Phase A0 — Observability bridging (ADR-023 Phase 0 同梱推奨)

#### スコープ
- [`backend/observability/structured_logger.py`](../../backend/observability/structured_logger.py) に `memory_*` / `reception_*` event family を追加
- LTM write 結果を必ず `metadata["ltm_store_write"]` に inject — `_write_long_term_memory` の **定義** は [`backend/workflows/main_workflow.py:1835`](../../backend/workflows/main_workflow.py:1835)、**呼び出し** は L1876 (`candidate_fast_path`) と L1901 (`legacy_direct`)、`extract_memories` 呼び出しは [`backend/workflows/main_workflow.py:1898`](../../backend/workflows/main_workflow.py:1898)。3 箇所すべてで metadata に成功/失敗を反映
- `chat_response.route` フィールドに class 名が漏れている問題（17日中 629件 `BusinessInfoAgent` 等）を [`backend/observability/structured_logger.py:148`](../../backend/observability/structured_logger.py:148) の優先順位修正で解消
  - `route = metadata["route"]` を呼び出し側で必ず set
  - 命名規約は ADR-023 の routes.yaml と一致させる

#### 完了条件
- LangSmith dashboard で `ltm_store_write="success"` が 0% → 名前明示ターンで ≥ 95%
- `memory_*` event が 5 種類以上 emit される
- `route="unknown"` 出現率 ≤ 0.5%

### D2: Phase A1 — agent_memory schema 最適化

#### スコープ
- migration 追加: `CREATE INDEX idx_agent_memory_session ON agent_memory ((value->>'sessionId'));`
- [`backend/utils/memory_helper.py`](../../backend/utils/memory_helper.py) の以下メソッドを SQL 側 filter に書き換え:
  - `_get_recent_messages` (L244-307)
  - `get_previous_request_type` (L102-147)
  - `cleanup_session` (L559-603) — N+1 delete loop を bulk delete に
  - `cleanup` (L605-657) — グローバル全件 scan を per-session に
- [`backend/utils/memory_helper.py:55`](../../backend/utils/memory_helper.py:55) の `max_entries = 100` を sessionId index 前提に再設計

#### 完了条件
- memory loader p95 latency ≤ 100ms — 計測 probe は Phase A0 で `memory_loader_get_recent_messages_duration_ms` event family として emit（LangSmith dashboard の `event="memory_loader_get_recent_messages"` で p95 算出）
- agent_memory total rows × 1000 件規模で線形時間に依存しないことを benchmark

### D3: Phase A2 — Hierarchical Store namespace 移行

#### スコープ
- LangGraph Store namespace を以下に階層化:
  ```
  ("users", visitor_id, "facts")        — visitor_name / visitor_affiliation
  ("users", visitor_id, "episodes")     — episode_incident / past visits
  ("users", visitor_id, "preferences")  — language / location preference
  ("global", "config")                  — shared config
  ```
- 現状 [`backend/workflows/main_workflow.py`](../../backend/workflows/main_workflow.py) の `("visitor_memories", user_id)` / `("visitor_memory_candidates", user_id)` 2 namespace から移行
- AsyncPostgresStore で 1 transaction で読み書き可能なように
- A3 で STM 二重保存 (Checkpointer × SimplifiedMemoryHelper) を統一する事前段階

#### 完了条件
- 全 LTM write が新 namespace 階層に着地（移行 script 含む）
- Shadow mode で 1 週間並走後切替
- LangGraph Store 公式パターンに準拠

### D4: Phase A3 — Semantic extractor 統合（ADR-023 router cascade に乗せる）

#### スコープ
- [`backend/utils/memory_extractor.py`](../../backend/utils/memory_extractor.py) の regex 抽出を **ADR-023 三段カスケード router の Stage 3 (LLM)** に統合
- [`backend/utils/purpose_classifier.py`](../../backend/utils/purpose_classifier.py) の `_PURPOSE_KEYWORDS` 80+ token を `routes.yaml` の purpose ルート群に統合
- STM 二重保存（A3 問題）の解消: LangGraph Checkpointer を SSOT として SimplifiedMemoryHelper.store_message を deprecated 化
- memory eval suite 追加: LongMemEval pattern を RAGAS の case suite に組み込み (temporal queries / multi-hop reasoning)

#### 完了条件
- memory_extractor + purpose_classifier の合計行数 700+ → ≤ 200
- `regex` ベース抽出 = 0、Stage 1 (safety regex) + Stage 2 (semantic) + Stage 3 (LLM judge) に統一
- RAGAS suite に memory recall case が追加され週次レポートに反映
- STM 二重保存解消、Checkpointer 単一 source of truth

### D5: Phase A4 — Reception dead code 削除 + visits ベース統一

#### スコープ（decisive）
- [`backend/api/reception.py:501-598`](../../backend/api/reception.py:501) `respond_reception` ハンドラ削除
- [`backend/api/reception.py:601+`](../../backend/api/reception.py:601) `complete_reception` ハンドラ削除
- [`frontend/src/app/api/reception/respond/route.ts`](../../frontend/src/app/api/reception/respond/route.ts) 削除
- [`frontend/src/app/api/reception/complete/route.ts`](../../frontend/src/app/api/reception/complete/route.ts) 削除
- 関連 model (ReceptionRespondRequest / Response / ReceptionCompleteRequest / Response) 削除
- [`backend/services/visitor_identification_service.py`](../../backend/services/visitor_identification_service.py) の users table 参照を全削除:
  - `identify_by_nfc` (L48-68) は NFC スキーマを別途設計するまで stub に
  - `identify_by_member_number` / `identify_by_member_number_with_lookup` 削除
  - `_get_user_profile` / `_get_user_profile_lookup` 削除
- `visitor_type` の判定を visits テーブル単独で行う（`returning` = visits に同じ visitor_id がある、`new` = ない）
- OCR / NFC / 会員番号機能の将来パスは別 ADR で議論

#### 完了条件
- reception 関連 dead code 約 200+ 行削除
- `public.users` への参照ゼロ
- `users_table_unavailable` warning が起動毎に出ない
- `/api/reception/start` → reception 完了率 24% → ≥ 60% (**aspirational**: UX / sensor reliability / visitor engagement にも依存する外生要因あり。controllable な指標は「instrumentation 完全性 = reception_transition event が全 stage で emit」を別途確認する)
- E2E test (Playwright) で reception flow がフル経路通る

## Consequences

### Positive
- **LTM が本番で動いているか観測可能になる**（A1）
- **agent_memory が線形 slowdown から解放**（A2）
- **STM 二重保存解消**で Checkpointer 単一化（A3 後段）
- **memory_extractor / purpose_classifier がキーワード爆発から解放**（A3）
- **dead code 200+ 行削除**で reception flow の認知負荷低下（A4）
- **ADR-023 と Phase A0 同梱**で observability の二重 PR 化を回避
- **business intelligence 可能化** — chat_response.route が cleanup されて class 名が漏れなくなる

### Negative
- Phase A2 (hierarchical namespace) は schema 変更を含む = migration リスク
- Phase A4 で NFC / 会員番号機能を一時的に失う = OCR flow に依存している既存 PR があれば調整必須
- Phase A3 で SimplifiedMemoryHelper を deprecated 化する際、既存テスト ([`backend/tests/utils/test_memory_helper.py`](../../backend/tests/utils/test_memory_helper.py) など) の大幅修正
- LangSmith trace 量増加 = コスト微増

### Risk Mitigation
| Risk | Mitigation |
|---|---|
| Hierarchical namespace 移行で既存 LTM データが見えなくなる | shadow mode で 1 週間並走、移行 script で旧 → 新 namespace へコピー、ロールバック手順を ADR に併記 |
| Reception dead code 削除で隠れた依存破壊 | Phase A4 を最後にする、削除前に `grep` 全件確認、Playwright E2E で reception フル経路を回す |
| public.users 削除で OCR 統合 PR と競合 | A4 着手前に PM (terisuke) に「会員番号 OCR の今後扱い」を確認、未確定なら A4 を後ろ倒し |
| STM 二重保存解消の機能リグレッション | Checkpointer 単独で `recent_messages` が引けることを A3 内で benchmark + A/B test |
| Phase A0 を ADR-023 Phase 0 と同梱した PR が複雑化 | observability 配線のみに絞る (5 行 LangSmith + structured_logger fix)、Phase A1 以降を別 PR で展開 |

## Rollout Plan

| Phase | 内容 | 期間 | 担当候補 | 完了条件 |
|---|---|---|---|---|
| **A0** | observability bridging + ltm_store_write setter | 0.5–1日 | backend-developer (ADR-023 Phase 0 と同 PR) | `ltm_store_write="success"` が出る、`memory_*` event family ≥ 5 種類 |
| **A1** | agent_memory schema 最適化 (GIN index + SQL filter) | 2–3日 | backend-developer + tdd-guide + database-optimizer | memory loader p95 ≤ 100ms |
| **A2** | hierarchical Store namespace 移行 | 1週間 (実装3日 + shadow 5日) | backend-developer + Codex CLI 経路C (migration script) | shadow 並走で discrepancy ≤ 1% |
| **A3** | semantic extractor 統合 + STM 二重保存解消 | 1週間 | backend-developer + ADR-023 担当者と協調 | memory_extractor + purpose_classifier 合計 ≤ 200 行 |
| **A4** | reception dead code 削除 + visits ベース統一 | 2–3日 | backend-developer + frontend-developer | reception 関連 200+ 行削除、CI green |

### Phase 別 PR 規律 (CLAUDE.md / ADR-023 と同じ)
- ブランチ命名: `feat/memory-phase{N}-{slug}`
- 全 PR `--base develop`
- code-reviewer + Codex CLI 経路 A レビュー必須
- 各 Phase 完了時に `MEMORY.md` の Session Status 更新

## Alternatives Considered

### A1: ADR-024 を起票せず Epic + sub-issue だけで進める
**却下理由**: ADR 化することで「なぜ」が記録される。3 系統の構造的負債を ADR-023 と同等扱いで明示する方が後継メンバーに優しい。

### A2: Phase A0 を ADR-023 Phase 0 と分ける
**却下理由**: observability 配線が二重 PR になり work 量がほぼ倍。LTM 観測性と LangSmith trace は同じ structured_logger 上に乗るため統合の方が自然。

### A3: reception/respond を残して main_workflow と「互換」で運用
**却下理由**: 17 日間 0 calls の事実。残しても confusion を生むだけ。Phase A4 で削除（terisuke 2026-05-17 決定）。

### A4: public.users テーブルを新規作成
**却下理由**: visits ベースで visitor_id だけ追跡すれば returning 判定は可能。会員番号 OCR / NFC は将来別 ADR で改めて議論（terisuke 2026-05-17 決定）。

### A5: Mem0 / Letta / Zep を採用
**保留**: Phase A2 完了後にコスト・運用面で再評価。現状 LangGraph Store + AsyncPostgresStore に hierarchical namespace を載せる方が依存追加なし。

## Approvals

- Proposed: Claude Code (2026-05-17) — GCP ログ 17 日分実測 + コード静的解析 + 2026/05 web research
- Accepted: Terada Kousuke (terisuke, 2026-05-17) — ADR-024 起票 / Phase A0 ADR-023 同梱 / Phase A4 削除 / visits ベース統一 すべて推奨案を選択

## References

### 本リポジトリ内
- [docs/plans/post-adr023-investigation-2026-05-17.md](../plans/post-adr023-investigation-2026-05-17.md) — 本 ADR の根拠調査報告書
- [ADR-006: LangGraph workflow redesign](006-langgraph-workflow-redesign.md)
- [ADR-011: LTM cross-session design](011-ltm-cross-session-design.md)
- [ADR-012: LTM connection pool migration](012-ltm-connection-pool-migration.md)
- [ADR-014: Observability phase 1a](014-observability-phase1.md)
- [ADR-017: Observability phase 1b](017-observability-phase1b.md)
- [ADR-018: Alpha fast response and assistant profile routing](018-alpha-fast-response-and-assistant-profile-routing.md)
- [ADR-023: Semantic Router + LangGraph runtime self-evaluation](023-semantic-router-and-runtime-self-evaluation.md)
- [docs/plans/semantic-router-self-eval-2026-05-17.md](../plans/semantic-router-self-eval-2026-05-17.md) — ADR-023 ハンドオフ計画
- MEMORY.md Phase 3.6 (`B-1〜B-4`) — 本 ADR で並行解消候補

### 外部 (2026/05 時点)

> **Note:** 外部リンクは 2026-05-17 時点で domain-plausible だが、各 Phase 着手時に実装担当が再到達性を確認すること。リンク切れの場合は WebSearch で同等資料を再取得する。

- [Mem0: State of AI Agent Memory 2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026)
- [Letta: Benchmarking AI Agent Memory (LongMemEval)](https://www.letta.com/blog/benchmarking-ai-agent-memory)
- [LangChain: Long-term memory docs](https://docs.langchain.com/oss/python/langchain/long-term-memory)
- [Analytics Vidhya: Architecture and Orchestration of Memory Systems in AI Agents (2026/04)](https://www.analyticsvidhya.com/blog/2026/04/memory-systems-in-ai-agents/)
- [arxiv 2510.27246: Benchmarking and Enhancing Long-Term Memory in LLMs](https://arxiv.org/pdf/2510.27246)
- [GitHub: NirDiamant/Agent_Memory_Techniques](https://github.com/NirDiamant/Agent_Memory_Techniques)
- [Five Agent Memory Types in LangGraph (dev.to)](https://dev.to/sreeni5018/five-agent-memory-types-in-langgraph-a-deep-code-walkthrough-part-2-17kb)
- [LangMem Hot Path Quickstart](https://langchain-ai.github.io/langmem/hot_path_quickstart/)
- [RAGAS × LangSmith integration](https://docs.ragas.io/en/stable/howtos/integrations/langsmith/)
- [Hamming.ai Voice Agent Testing Guide 2026](https://hamming.ai/resources/voice-agent-testing-guide)
