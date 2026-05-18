# ADR-029: Phase 2 LangGraph 1.0+ Best Practice Adoption (Core Scope)

## Status

Proposed (2026-05-18) — ADR-023 (Semantic Router 三段カスケード) の **同時着手スコープ** として起草。Phase 2 で Semantic Router を実装する際に 1.0+ ベストプラクティス未採用パターンを併せて採用する。

## Context

### Wave 3 完了後の独立 audit で判明 (2026-05-18)

LangGraph `1.0.x` を採用しているが、Context7 `/langchain-ai/langgraph/1.0.8` + `/langchain-ai/langgraph-supervisor-py` の 2026-05 ドキュメントと照合した結果、**5 つの 1.0+ 推奨パターンが未採用**:

#### 採用済 (11 / 16 modern patterns) — 良好
- ✅ `StateGraph` + TypedDict state
- ✅ `Command` (modern routing primitive) — 10+ 箇所
- ✅ `RetryPolicy` (per-node retry) — LLM 依存 6 node
- ✅ `add_messages` reducer — `Annotated[list[BaseMessage], add_messages]`
- ✅ `AsyncPostgresSaver` (Checkpointer)
- ✅ `AsyncPostgresStore` (Store) — LangGraph 1.0 GA feature
- ✅ Subgraph + `invoke_subgraph` — reception_workflow ↔ main_workflow
- ✅ `astream_events` (1.0 推奨 streaming)
- ✅ `ToolNode` + `tools_condition` — ocr_agent.py
- ✅ `@tool` decorator
- ✅ `add_conditional_edges` — 5 箇所

#### 未採用 (5 / 16, **改善対象**)

| # | Pattern | 影響度 | 既存代替 | 推奨採用タイミング |
|---|---------|------:|---------|------------------|
| 1 | **`with_structured_output()`** for routing decision | 🔴 高 | 自前 JSON parse + try/except (orchestrator_agent.py) | **ADR-023 Semantic Router と同時** |
| 2 | **`Send` API** (Map-Reduce / fan-out) | 🟡 中 | EventAgent の 3 source (spreadsheet + connpass + calendar) を順次 await | ADR-023 Phase 4 (parallel optimization) |
| 3 | **`create_supervisor` (langgraph_supervisor)** | 🟡 中 | `_orchestrator_node` + `add_conditional_edges` で自前実装 (~200 行 boilerplate) | ADR-023 Phase 2-3 で並行採用 |
| 4 | **`create_react_agent` (prebuilt ReAct)** | 🟡 中 | 各 agent class で個別実装 | Wave 4 で評価 (lock-in リスクあり) |
| 5 | **`create_forward_message_tool`** | 🟢 小 | 自前で full message を return | Wave 4 で評価 (微小 latency 改善) |

### 当該未採用パターンが ADR-023 と整合する根拠

ADR-023 §Decision で「**Semantic Router 三段カスケード + LangGraph Runtime Self-Evaluation Loop**」が定義されている。この設計を実装する際、以下が自然に必要になる:

- **Semantic routing 判断 → 構造化出力** = `with_structured_output(RouteDecision)` が標準解
- **Critic node の self-evaluation** = `with_structured_output(CriticVerdict)` が標準解
- **Supervisor pattern 強化** = `create_supervisor` が宣言的に書ける

→ ADR-023 と **同 PR で実装すれば差分が小さく、設計の一貫性も保てる**。本 ADR は ADR-023 を補完する。

### 観測されている悪影響 (Wave 3 audit より)

- `agent_routing` event の `fallback_general` 比率: **約 30% (Wave 3 alert 閾値 fallback_general > 30%)** — routing 判断の不安定さの裏返し
- EventAgent latency p50: 3 source 順次 await のため、**spreadsheet (3s) + connpass (1s) + calendar (0.5s) = 4.5s** が直列。`Send` 並列化で **約 -3s 削減見込**
- orchestrator boilerplate: `_orchestrator_node` 関数群で約 200 行の routing dispatch 自前実装

## Decision

### D1: 構造化出力 routing を全面採用 (★★★ 高優先度)
- ADR-023 Phase 1 (`backend/routing/routes.yaml` + Semantic Router) の判断層を `with_structured_output(RouteDecision: BaseModel)` で実装
- `orchestrator_agent._is_memory_related_question` / `_try_fast_routing` を Pydantic schema-driven に置換
- Critic node (`backend/workflows/critic_node.py`) も `with_structured_output(CriticVerdict)` で実装
- 期待効果: routing 失敗率 30% → 10% 程度、fallback_general 比率低下

### D2: EventAgent 3-source fetch を `Send` で並列化 (★★ 中優先度)
- `backend/agents/event_agent.py` の fetch 段を `Send("spreadsheet_fetcher", state)` + `Send("connpass_fetcher", state)` + `Send("calendar_fetcher", state)` に分解
- merge node が 3 結果を待ち合わせて統合
- 期待効果: EventAgent latency p50 -2〜3 秒

### D3: Supervisor pattern を `create_supervisor` で declarative 化 (★★ 中優先度)
- `langgraph_supervisor>=0.1` を `backend/pyproject.toml` に追加
- `_orchestrator_node` + 6 agent dispatch を `create_supervisor([agents], model, prompt)` で書き換え
- 既存 `Command` 利用は維持 (handoff tool が自動生成される)
- 期待効果: 約 -150 行 boilerplate 削減、可読性向上、Phase 3+ で agent 追加が容易

### D4: `create_react_agent` 採用は Wave 4 で評価 (★ 低優先度)
- 現状 11 agent class の半分は `create_react_agent` で書き換え可能
- ただし agent 個別の prompt engineering / RAG fallback 等の柔軟性を失うリスクあり
- ADR-023 完了後の Wave 4 で個別 agent 単位で評価

### D5: `create_forward_message_tool` は Wave 4 で評価 (★ 低優先度)
- LLM token 削減 + 微小 latency 改善
- ADR-023 完了後の Wave 4 で評価

## Consequences

### Positive
- routing 判断が型保証され、`fallback_general` 過剰発火が抑制
- EventAgent latency が体感できるレベルで短縮
- Supervisor 実装が宣言的になり、Phase 3+ での agent 追加が容易
- ADR-023 / ADR-024 / Wave 3 の observability (agent_routing event) と整合
- LangGraph 1.0 best practice 整合度: 88% → **≥95%**

### Negative
- `langgraph_supervisor` 依存追加 (現状 pyproject になし)
- `with_structured_output` 採用で Pydantic schema 定義が増える
- `Send` 並列化で 3 fetcher の error handling が複雑化 (1 つ失敗時の fallback ロジック要設計)

### Out of Scope (本 ADR では実装しない)
- ADR-023 の routes.yaml / critic_node 本体実装 — ADR-023 で別管理
- ADR-024 の memory hierarchy 再設計 — 別 ADR
- ADR-025 の Vite migration — 別 ADR
- `create_react_agent` 全面採用 / `create_forward_message_tool` 採用 — Wave 4 候補

## Rollout Plan

| Phase | 内容 | 対応 sub-issue | 工数 |
|-------|------|--------------|-----|
| Phase 2-α | ADR-023 routes.yaml + Semantic Router 実装 (既存 ADR-023 範囲) | (ADR-023 issue) | (既定) |
| **Phase 2-β** | **D1: `with_structured_output` で routing + critic** | FU-36 | **1.5 day** |
| **Phase 2-γ** | **D3: `create_supervisor` で orchestrator declarative 化** | FU-37 | **2.5 day** |
| Phase 2-δ | D2: EventAgent `Send` 並列化 | FU-38 | 1.0 day |
| Phase 2-ε | Observability 更新 (agent_routing event の field 拡張 + alert 閾値調整) | FU-39 | 0.5 day |
| Phase 2-ζ | (任意) ADR-029 自己再評価レポート (採用前後 metric 比較) | FU-40 | 0.5 day |

合計 工数: **約 6 営業日** (ADR-023 と並列で実施、Backend 1-2 名)

## Approvals

- Proposed: Claude (2026-05-18) — Wave 3 完了後の LangGraph 1.0+ ベストプラクティス整合度監査の結果
- 承認待ち: Terada Kousuke (terisuke)

## References

- [ADR-023 Semantic Router 三段カスケード + Runtime Self-Evaluation](./023-semantic-router-and-runtime-self-evaluation.md)
- [ADR-024 Memory & Reception Modernization](./024-memory-and-reception-modernization.md)
- [ADR-025 Frontend Proxy Deletion → Vite Migration](./025-frontend-proxy-deletion-and-vite-migration.md)
- [ADR-027 Wave 3 Foundation Hardening](./027-wave3-observability-and-refactor-foundation.md)
- [ADR-028 OSS-Portable Observability](./028-oss-portable-observability-and-infrastructure.md)
- LangGraph 1.0.8 docs: https://github.com/langchain-ai/langgraph/tree/1.0.8
- LangGraph Supervisor: https://github.com/langchain-ai/langgraph-supervisor-py
- Phase 2 handoff: `docs/plans/phase2-langgraph-best-practices-handoff-2026-05-18.md`
