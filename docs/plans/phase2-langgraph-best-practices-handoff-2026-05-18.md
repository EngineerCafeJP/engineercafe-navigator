# Phase 2 LangGraph 1.0+ Best Practice Adoption — Engineer Handoff (2026-05-18)

> **対象**: Phase 2 を実装する Backend エンジニア
> **作成**: 2026-05-18, Claude Code session (terisuke 指示)
> **位置付け**: [ADR-029](../adr/029-phase2-langgraph-1.0-best-practices.md) の実装ハンドオフ。ADR-023 (Semantic Router 三段カスケード) と **同時実装** を前提とする補完スコープ
> **想定工数**: 約 6 営業日 (Backend 1-2 名、ADR-023 と並列)

---

## 0. Executive Summary

Wave 3 完了後の独立 audit で、現実装は **LangGraph 1.0 ベストプラクティスを 88% (14/16) 整合** している良好な状態だが、以下 **5 つの未採用パターン** がある:

1. ❌ `with_structured_output()` — routing 判断が型保証されていない
2. ❌ `Send` API — EventAgent 3-source fetch が直列
3. ❌ `create_supervisor` — orchestrator が ~200 行 boilerplate
4. ❌ `create_react_agent` — agent class 個別実装 (Wave 4 候補)
5. ❌ `create_forward_message_tool` — micro 最適化 (Wave 4 候補)

うち **D1〜D3 (高〜中優先)** を Phase 2 で ADR-023 と同時実装し、整合度を **≥95%** に上げる。

---

## 1. 背景: なぜ Phase 2 でやるか

### 1.1 ADR-023 (Semantic Router) と整合する設計
ADR-023 §Decision で「Semantic Router 三段カスケード + LangGraph Runtime Self-Evaluation Loop」が定義されている。

- 「Semantic routing 判断 → 構造化出力」= `with_structured_output(RouteDecision)` が **業界標準解**
- 「Critic node の self-evaluation」= `with_structured_output(CriticVerdict)` が **業界標準解**
- 「Supervisor pattern 強化」= `create_supervisor` で declarative 化が **2024 以降の主流**

→ ADR-023 と **同 PR 群で実装すれば差分が小さく、設計の一貫性も保てる**

### 1.2 観測されている悪影響 (Wave 3 監査より)
- `agent_routing` event の `fallback_general` 比率: **約 30%** (Wave 3 alert 閾値 `> 30%`)
- EventAgent latency p50: spreadsheet (3s) + connpass (1s) + calendar (0.5s) = **4.5s 直列**
- orchestrator boilerplate: `_orchestrator_node` 群で **約 200 行 dispatch 自前実装**

---

## 2. 採用済 / 未採用 詳細 (Wave 3 audit より)

### 2.1 採用済 (11 / 16) — 維持

| # | Pattern | 採用箇所 |
|---|---------|---------|
| 1 | `StateGraph` + TypedDict | main_workflow / reception / ocr |
| 2 | `Command` (routing primitive) | main_workflow:1477+ 10 箇所 |
| 3 | `RetryPolicy` (per-node retry) | LLM 依存 6 node |
| 4 | `add_messages` reducer | `Annotated[list[BaseMessage], add_messages]` 3 file |
| 5 | `AsyncPostgresSaver` (Checkpointer) | utils/checkpointer.py |
| 6 | `AsyncPostgresStore` (Store) | utils/store.py (1.0 GA) |
| 7 | Subgraph + `invoke_subgraph` | reception_workflow.invoke_reception_subgraph |
| 8 | `astream_events` | main_workflow:2443 |
| 9 | `ToolNode` + `tools_condition` | agents/ocr_agent.py |
| 10 | `@tool` decorator | agents/agent_tools.py 6 件 |
| 11 | `add_conditional_edges` | 5 箇所 |

### 2.2 未採用 (5) — Phase 2 で D1〜D3 採用

| # | Pattern | 影響 | 採用判断 |
|---|---------|------|---------|
| D1 | `with_structured_output()` | 🔴 高 routing 失敗率 | **採用** (FU-36) |
| D2 | `Send` API | 🟡 中 latency | **採用** (FU-38) |
| D3 | `create_supervisor` | 🟡 中 boilerplate | **採用** (FU-37) |
| D4 | `create_react_agent` | 🟢 lock-in リスクあり | Wave 4 評価 |
| D5 | `create_forward_message_tool` | 🟢 micro | Wave 4 評価 |

---

## 3. 全 5 sub-issues 詳細仕様

### FU-36 [P0] `with_structured_output()` で routing + critic を型保証 (1.5d)

**問題**:
- `backend/agents/orchestrator_agent.py` の `_is_memory_related_question` / `_try_fast_routing` は自前 JSON parse + try/except
- LLM 出力が `{}` や invalid JSON のとき fallback_general に流れる頻度が高い (約 30%)

**実装**:
```python
# backend/agents/orchestrator_agent.py
from pydantic import BaseModel, Field
from typing import Literal

class RouteDecision(BaseModel):
    """Routing 判断結果. LLM が自然言語で返してきても schema 準拠を強制."""
    routed_to: Literal[
        "business_info", "facility", "event", "slide",
        "general_knowledge", "farewell", "fallback_general",
    ] = Field(description="どのエージェントに転送するか")
    intent: str = Field(description="user query から抽出した意図 (短文)")
    confidence: float = Field(ge=0.0, le=1.0, description="判断確度")
    reasoning: str = Field(description="判断理由 (debug 用)")

# 既存:
#   raw = llm.invoke(prompt).content
#   try: parsed = json.loads(raw)  ← 失敗時 fallback
# 新規:
structured_llm = llm.with_structured_output(RouteDecision)
decision: RouteDecision = structured_llm.invoke(prompt)
# decision.routed_to が型保証される、Pydantic validation 自動
```

**Critic node も同様**:
```python
class CriticVerdict(BaseModel):
    """Self-eval verdict from critic_node (ADR-023)."""
    quality: Literal["pass", "needs_retry", "fail"]
    reason: str
    suggested_route: str | None = None

structured_critic = llm.with_structured_output(CriticVerdict)
```

**受入条件**:
- [ ] `pytest backend/tests/agents/test_orchestrator_structured_routing.py` PASS
- [ ] live: `gcloud logging read 'jsonPayload.event="agent_routing" jsonPayload.fallback_used=true'` の比率が **30% → 15% 以下**
- [ ] Wave 3 alert `agent_routing_skew` (fallback_general > 30%) が 7 日連続非発火
- [ ] CI: lint + typecheck + pytest 全 PASS

---

### FU-37 [P0] `create_supervisor` で orchestrator declarative 化 (2.5d)

**問題**: `main_workflow.py` 内の orchestrator 関連 dispatch コードが **約 200 行 boilerplate**

**実装**:
```bash
# Dependency
echo 'langgraph-supervisor>=0.1' >> backend/requirements.txt
# pyproject.toml にも追記
```

```python
# backend/workflows/supervisor_workflow.py (新設, 目標 < 300 行)
from langgraph_supervisor import create_supervisor
from langgraph.prebuilt import create_react_agent

# 既存 agent class はそのまま、ReAct wrapper を新設:
business_info_agent_node = create_react_agent(
    model=cerebras_llm,
    tools=[business_info_tool],
    name="business_info",
    prompt=BUSINESS_INFO_PROMPT,
)
facility_agent_node = create_react_agent(
    model=cerebras_llm,
    tools=[facility_tool],
    name="facility",
    prompt=FACILITY_PROMPT,
)
# (4 agent も同様)

supervisor_workflow = create_supervisor(
    agents=[
        business_info_agent_node,
        facility_agent_node,
        event_agent_node,
        slide_agent_node,
        general_knowledge_agent_node,
        farewell_agent_node,
    ],
    model=cerebras_llm,
    prompt=SUPERVISOR_PROMPT,
    output_mode="last_message",  # 各 agent の最終 message のみ supervisor に渡る
)
```

**移行戦略 (回帰防止)**:
1. **新 supervisor_workflow.py を main_workflow.py と並列実装** (feature flag で切替可)
2. live A/B (10% トラフィック) で routing 正確性比較
3. 等価性確認後に main_workflow.py の orchestrator dispatch を削除

**受入条件**:
- [ ] `pytest backend/tests/workflows/test_supervisor_workflow.py` PASS
- [ ] live A/B 1 週間で smoke 6 query の routing 結果が **完全一致** (regression なし)
- [ ] `main_workflow.py` の orchestrator dispatch コード **-150 行以上**削減
- [ ] CI: lint + typecheck + pytest 全 PASS

---

### FU-38 [P0] EventAgent `Send` 並列 fetch (1.0d)

**問題**: `backend/agents/event_agent.py` で `spreadsheet → connpass → calendar` を直列 await、latency 4.5s

**実装**:
```python
# backend/agents/event_agent.py
from langgraph.types import Send

def event_dispatcher(state: EventState) -> list[Send]:
    """Send で 3 source を並列 fetch."""
    return [
        Send("spreadsheet_fetcher", {"query": state["query"]}),
        Send("connpass_fetcher", {"query": state["query"]}),
        Send("calendar_fetcher", {"query": state["query"]}),
    ]

# main_workflow.py の event subgraph 構築:
event_subgraph = StateGraph(EventState)
event_subgraph.add_node("dispatcher", event_dispatcher)
event_subgraph.add_node("spreadsheet_fetcher", fetch_from_spreadsheet)
event_subgraph.add_node("connpass_fetcher", fetch_from_connpass)
event_subgraph.add_node("calendar_fetcher", fetch_from_calendar)
event_subgraph.add_node("merger", merge_event_sources)
event_subgraph.add_edge(START, "dispatcher")
# Send で fan-out した結果は merger で reduce
event_subgraph.add_edge("spreadsheet_fetcher", "merger")
event_subgraph.add_edge("connpass_fetcher", "merger")
event_subgraph.add_edge("calendar_fetcher", "merger")
event_subgraph.add_edge("merger", END)
```

**Error handling**:
- 各 fetcher は try/except で空 list を return (1 つ失敗しても他 source で継続)
- merger で全 source 失敗時のみ "イベント情報を取得できませんでした" を return

**受入条件**:
- [ ] `pytest backend/tests/agents/test_event_agent_parallel.py` PASS
- [ ] live: `voice_round_trip` event の `chat_ms` (EventAgent 経由) の **p50 -2,000ms 以上削減**
- [ ] 1 source 失敗 (e.g., spreadsheet GAS 502) でも他 source の結果が返る
- [ ] CI: lint + typecheck + pytest 全 PASS

---

### FU-39 [P1] Observability 更新 (0.5d)

**実装**:
- `agent_routing` event に新 field 追加:
  - `decision_method`: `"structured_output"` | `"json_parse"` (FU-36 前後比較用)
  - `parallel_fan_out`: bool (FU-38 適用 path フラグ)
- Wave 3 alert `agent-routing-skew` の閾値を `> 30%` から `> 15%` に下げる (FU-36 効果反映)
- Grafana dashboard に `decision_method` breakdown panel 追加

**受入条件**:
- [ ] `gcloud logging read` で新 field が見える
- [ ] Wave 3 alert policy 更新確認
- [ ] CI: lint + typecheck + pytest 全 PASS

---

### FU-40 [P1] ADR-029 採用前後の metric 比較レポート (0.5d)

**実装**:
- 採用後 1 週間運用、以下を比較するレポートを `docs/plans/phase2-langgraph-bp-impact-2026-XX-XX.md` に記載:
  - `fallback_general` 比率: Before vs After
  - `voice_round_trip.chat_ms` (EventAgent path): Before vs After
  - orchestrator dispatch 行数: Before vs After
  - CI / pytest 結果

**受入条件**:
- [ ] レポート markdown 作成
- [ ] Cloud Logging query + Prometheus query を再現可能に記述
- [ ] terisuke review

---

## 4. 想定 PR 分割 (約 5 PR)

| PR | Branch | Scope | 工数 |
|----|--------|-------|------|
| PR-P2A-1 | `feat/phase2-structured-routing` | FU-36 | 1.5d |
| PR-P2A-2 | `feat/phase2-supervisor-declarative` | FU-37 | 2.5d |
| PR-P2A-3 | `feat/phase2-event-send-parallel` | FU-38 | 1.0d |
| PR-P2A-4 | `feat/phase2-observability-updates` | FU-39 | 0.5d |
| PR-P2A-5 | `docs/phase2-langgraph-bp-impact` | FU-40 | 0.5d |

合計 5 PR, **約 6 営業日** (Backend 1-2 名)

---

## 5. ADR-023 との並行実施 schedule (推奨)

```
Day 1-3:   ADR-023 Phase 1 (routes.yaml + Semantic Router 骨格)
           並行: FU-36 (structured output for routing)
Day 4-5:   ADR-023 Phase 2 (Semantic Router cascade 完成)
           並行: FU-37 (create_supervisor) 設計レビュー
Day 6-8:   FU-37 実装 + A/B test
           並行: ADR-023 Phase 3 (critic_node 実装 — ここで FU-36 の Critic schema も使う)
Day 9:     FU-38 (EventAgent Send 並列)
Day 10:    FU-39 (observability) + FU-40 (impact report 初版)
Day 11-12: 統合検証 + 1 週間運用 buffer
```

---

## 6. Exit Criteria (Phase 2 LangGraph BP 採用完了)

- [ ] FU-36 〜 FU-40 全 close
- [ ] `with_structured_output` 採用: routing + critic 両方
- [ ] `create_supervisor` 採用: orchestrator dispatch 行数 -150 行以上
- [ ] `Send` 並列採用: EventAgent latency p50 -2,000ms 以上
- [ ] `agent_routing.fallback_used=true` 比率: 30% → 15% 以下
- [ ] Wave 3 alert `agent-routing-skew` 閾値更新
- [ ] LangGraph 1.0 best practice 整合度: 88% → **≥95%**
- [ ] CI all green / live regression なし

---

## 7. Out of Scope (本 Phase 2 LangGraph BP では実装しない)

- ❌ ADR-023 routes.yaml / critic_node 本体実装 (ADR-023 の別管理)
- ❌ ADR-024 Memory hierarchy 再設計 (別 ADR)
- ❌ ADR-025 Frontend Vite migration (別 ADR)
- ❌ `create_react_agent` 全面採用 — Wave 4 評価
- ❌ `create_forward_message_tool` 採用 — Wave 4 評価

---

## 8. Reference

- ADR-029: `docs/adr/029-phase2-langgraph-1.0-best-practices.md`
- ADR-023: `docs/adr/023-semantic-router-and-runtime-self-evaluation.md` (Phase 2 本体)
- ADR-024, ADR-025: Phase 2 関連の別スコープ ADR
- LangGraph 1.0.8 docs: https://github.com/langchain-ai/langgraph/tree/1.0.8
- LangGraph Supervisor: https://github.com/langchain-ai/langgraph-supervisor-py
- Wave 3 best practice audit (本 doc の根拠): 2026-05-18 セッション
