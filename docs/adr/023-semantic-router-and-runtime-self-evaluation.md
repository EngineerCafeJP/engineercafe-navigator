# ADR-023: Semantic Router 三段カスケード + LangGraph Runtime Self-Evaluation Loop

## Status

Proposed (2026-05-17) — 実装は次セッション以降の別エンジニア担当。本 ADR は設計合意の固定版。

## Context

### 観測されている構造的問題

Engineer Cafe Navigator のルーティング層は ADR-006 (LangGraph workflow redesign) で導入したキーワード fast-path をベースにしているが、運用 6 ヶ月で以下の悪循環が確立してしまった：

> Q-gate FAIL の発生 → 該当パターンを `*_KEYWORDS` リストに追記 → 新規 if 分岐を `intent_classifier.py` に挿入 → ルーティング表 (`CATEGORY_TO_AGENT_MAP`, `REQUEST_TYPE_TO_AGENT_MAP`) を更新 → 次の Q-gate FAIL で同じことを繰り返す。

#### 現状の規模（2026-05-17 時点）

| ファイル | 行数 | 制限 | 内容 |
|---|---|---|---|
| [`backend/workflows/main_workflow.py`](../../backend/workflows/main_workflow.py) | **2,274** | 800 | 4段ファストパス + reception bypass + clarification handler が同居 |
| [`backend/config/routing_constants.py`](../../backend/config/routing_constants.py) | **1,147** | 800 | キーワードリスト 30 種以上、`CATEGORY_TO_AGENT_MAP` 23 エントリ |
| [`backend/utils/intent_classifier.py`](../../backend/utils/intent_classifier.py) | **734** | 800 | `classify_fast_intent()` 単一関数に `if match_keywords(...)` 35 連発 |
| [`backend/utils/query_classifier.py`](../../backend/utils/query_classifier.py) | 508 | 800 | regex + キーワード手書き分類 |
| [`backend/agents/orchestrator_agent.py`](../../backend/agents/orchestrator_agent.py) | 401 | 800 | LLM ルーティングは "高速パス全部スカった時の最後" |

> 800 行制限（CLAUDE.md `~/.claude/rules/coding-style.md`）を 3 ファイルが超過。

#### 既存ルート判定パイプライン（実態）

```
START
  ↓ _input_type_decision
reception_check
  ↓ _reception_check_decision
keyword_router          ← fast-path #1: pre_memory_fast_path（facility/general_knowledge のみ直行）
  ↓
memory_loader (RAG pre-fetch)
  ↓
orchestrator
  ├── _is_memory_related_question      ← fast-path #2
  ├── _try_fast_routing (=classify_fast_intent, 35 連 if)  ← fast-path #3
  ├── _resolve_cafe_entity_for_turn (saino 強制 business_info) ← fast-path #4
  ├── LLM 呼び出し（ここでようやく動的判定）
  ├── _handle_emergency
  ├── _handle_greeting
  ├── _handle_clarification
  ├── _handle_topic_guard
  ↓
business_info / facility / event / slide / general_knowledge / farewell
  ↓
format_response → END
```

### 既存の自己評価パイプライン（致命的欠落）

| 項目 | 現状 |
|---|---|
| Online (per-turn) eval | **無し**。turn 単位で自分の出力を判定する critic ノードが存在しない |
| Offline eval | [`backend/evaluation/run_multilingual_eval.py`](../../backend/evaluation/run_multilingual_eval.py)（590 行）+ RAGAS が週1 cron ([`.github/workflows/ragas-evaluation.yml`](../../.github/workflows/ragas-evaluation.yml)) |
| Trace の入手手段 | DB を SELECT。span/trace の構造化エクスポート無し |
| LangSmith | API key フィールド (`backend/config/settings.py:81`) は定義済み。**ただし import / instrument は未配線** |
| Langfuse / OTel | **未配線** |
| Guardrail への eval feedback | 一方通行（評価結果 → 人が修正 → PR）。runtime には何も戻らない |

### 2026 年業界ベスト・プラクティス（調査結果）

- **Semantic Router (embedding-based 1st stage)**: utterance ベクトル空間で cosine 類似度判定。FastEmbed (ONNX, CPU) で 10–30ms。2026 年時点で数千ルートまで再学習不要、95% 精度・10–20ms latency 達成事例あり。
  - [aurelio-labs/semantic-router](https://github.com/aurelio-labs/semantic-router)
  - [Deepchecks: What is Semantic Router? 2026](https://www.deepchecks.com/glossary/semantic-router/)
  - [vLLM Semantic Router blog (2025/09)](https://blog.vllm.ai/2025/09/11/semantic-router.html)
- **Cascade routing**: 小モデル → 大モデルへの confidence-aware escalation。
  - [lm-sys/RouteLLM](https://github.com/lm-sys/RouteLLM)
  - [IBM Research: LLM routers (2025)](https://research.ibm.com/blog/LLM-routers)
- **Self-Reflective LangGraph**: generator → critic → revise の閉ループ、`critic_score` を trace span に直接付与。
  - [langchain-ai/langgraph-reflection](https://github.com/langchain-ai/langgraph-reflection)
  - [Building Self-Evaluating Systems With LangGraph (2026/02)](https://www.sciencetechniz.com/2026/02/building-self-evaluating-systems-with.html)
- **Online evaluation as runtime guardrail**: production trace に毎ターン自動 judge スコア付与。eval を dev で定義 → そのまま runtime guardrail。
  - [Langfuse LLM-as-a-Judge](https://langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge)
  - [LangSmith Evaluation Platform](https://www.langchain.com/langsmith/evaluation)
  - [Agent Observability 2026 ガイド](https://www.digitalapplied.com/blog/agent-observability-2026-evals-traces-cost-guide)
- **Voice / kiosk latency 設計**: cascading 構成で intent recognition >95% 精度、Stage 1+2 で 50ms 以内が voice 用途の鉄則。
  - [Hamming.ai Voice Agent Testing Guide 2026](https://hamming.ai/resources/voice-agent-testing-guide)
  - [AssemblyAI: AI voice agents 2026](https://www.assemblyai.com/blog/ai-voice-agents)

## Decision

ルーティングを **「三段カスケード Router」** に再設計し、LangGraph に **「critic ノード + 1 回 self-repair + LangSmith trace 配線」** を追加する。"キーワードを 1 つ足す" 運用を "YAML に発話例を 1 行足す" 運用に転換し、本番 100% カバレッジの自己評価ループを runtime に組み込む。

### D1: ルーティング層を三段カスケードに置換

```
                ┌───────────────────────────────────────────┐
                │  Stage 1: Deterministic safety regex      │
User query ────▶│  (emergency / farewell / PII redaction)    │── HIT → 即決
                │  ~50 行。命に関わる物・自明な hard rule のみ │
                └────────────────┬──────────────────────────┘
                                 │ MISS
                                 ▼
                ┌───────────────────────────────────────────┐
                │  Stage 2: Semantic Router                 │
                │  - aurelio-labs/semantic-router           │
                │  - FastEmbed (ONNX, CPU) ~10-30ms         │── score ≥ 0.75 → 確定
                │  - routes.yaml で utterance を管理          │
                │  - Hybrid mode (BM25 + dense) で OOV吸収   │
                └────────────────┬──────────────────────────┘
                                 │ score < 0.75 (曖昧)
                                 ▼
                ┌───────────────────────────────────────────┐
                │  Stage 3: LLM Router (現行 orchestrator)  │
                │  - Pydantic / JSON schema 構造化出力       │
                │  - gemini-flash-lite（routing 用）         │
                └───────────────────────────────────────────┘
```

#### D1a: 規模目標

| ファイル | Before | After (目標) | 削減手段 |
|---|---|---|---|
| `routing_constants.py` | 1,147 | ≤ 300 | キーワード 30 種 → `routes.yaml`（utterance 各 3–5 例）。マッピング表は維持 |
| `intent_classifier.py` | 734 | ≤ 120 | `classify_fast_intent` 35 連 if → emergency / farewell / assistant_profile / pet_policy など safety hard rule のみ残す |
| `main_workflow.py` | 2,274 | ≤ 800 (Phase 5 で subgraph 分割) | router / critic / format を subgraph に切り出し |

#### D1b: routes.yaml フォーマット（提案）

```yaml
# backend/routing/routes.yaml
version: 1
encoder: fastembed/Qwen3-Embedding-0.6B  # ONNX, CPU
threshold: 0.75
routes:
  - name: business_hours
    target_agent: business_info
    request_type: hours
    utterances:
      - "営業時間は何時まで？"
      - "今日は何時に閉まりますか"
      - "What time do you close?"
      - "週末も開いてる？"
      - "休館日はいつ"

  - name: wifi
    target_agent: facility
    request_type: wifi
    utterances:
      - "Wi-Fi のパスワード教えて"
      - "インターネットはありますか"
      - "What's the Wi-Fi password?"
      - "无线网密码"

  # ... 約 30 ルート
```

#### D1c: Voice latency budget 整合

| Stage | 想定 latency | 累積 |
|---|---|---|
| Stage 1 (regex) | < 1ms | 1ms |
| Stage 2 (FastEmbed + 30 routes cosine) | 10–30ms | ~31ms |
| Stage 3 (LLM router, fallback only) | 150–250ms | ~280ms |

→ Voice 用途の 50ms budget を Stage 1+2 で守る。Stage 3 を踏むのは曖昧クエリのみ。

### D2: LangGraph に Critic ノード + 1 回 self-repair を追加

```
existing:
  agent → format_response → END

新:
  agent → format_response → 🆕 critic_node ───┐
                                              │
            ┌──── repair (1 retry only) ◀────┤ verdict.needs_repair=true && retry==0
            │                                 │
            └──→ agent (re-execute) ─────────┘
                                              │
                                              └─→ END (verdict.passed or retry exhausted)
                                                  ↓
                                          🆕 quality_event_emitter
                                          (LangSmith trace に
                                           critic_score を非同期 emit)
```

#### D2a: Critic ノードの責務

```python
# backend/workflows/critic_node.py (新設, 目標 ≤150 行)

class CriticVerdict(BaseModel):
    groundedness: float          # RAG context への忠実度 (decision: 0.6 未満で repair)
    answer_relevancy: float      # 質問への適合度
    language_match: float        # quality_signals.language_match_score を流用
    safety: float                # PII / toxicity (既存 pii_scanner + quality_signals 流用)
    routing_correctness: float   # 選んだ agent が妥当か (LLM judge, 確信度低い時のみ)
    needs_repair: bool
    repair_hint: str | None      # "RAG context が空。general_knowledge に re-route 推奨"

async def critic_node(state: WorkflowStateDict) -> dict:
    # 1. 決定論的シグナル（無料・5ms）: 既存 quality_signals.summarize_quality_signals 流用
    deterministic = compute_deterministic_signals(state)

    # 2. LLM-as-judge（gemini-flash-lite, ~200ms, 確信度低い時のみ）
    if deterministic.groundedness < 0.7 or deterministic.language_match < 0.9:
        judge = await llm_judge.score(query, answer, contexts)
        verdict = merge(deterministic, judge)
    else:
        verdict = CriticVerdict.from_deterministic(deterministic)

    # 3. LangSmith trace に critic_score を非同期 emit (fire-and-forget)
    emit_trace_score(session_id=state["session_id"], verdict=verdict)

    return {"critic_verdict": verdict.model_dump()}
```

#### D2b: Self-repair の制約

- **最大 1 回の retry**（無限ループ防止）
- 既存 [`main_workflow.py:2134`](../../backend/workflows/main_workflow.py:2134) の `asyncio.wait_for(graph.ainvoke, timeout=30)` を尊重。critic + repair の合計でも 30s を超えない
- `repair_hint` が "re-route" を示す場合のみ別 agent を再呼び出し、それ以外は同 agent の同一実行
- repair しても improve しなければ retry をやめて元の answer を返す（`fallback_to_original=true` でログ出力）

#### D2c: LangSmith trace 配線（Phase 0 の 5 行）

```python
# backend/main.py の startup_event
if settings.langsmith_api_key:
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGSMITH_PROJECT"] = "engineer-cafe-prod"
    logger.info("LangSmith tracing enabled: project=engineer-cafe-prod")
```

→ これだけで既存 LangGraph ノード全部が **自動 trace される**。critic_node 追加後は `critic_score` カスタム metadata 付きで LangSmith ダッシュボードに並ぶ。

### D3: 既存決定論評価ロジックの runtime 再利用

`backend/evaluation/quality_signals.py` は **CI/offline で確立された決定論シグナル群** (language_match / groundedness / hallucination_risk / toxicity)。これらを critic ノードに **そのまま import して runtime 評価に流用**する。CI と runtime の評価基準が一致する点が重要。

- CI 側の thresholds（`DEFAULT_THRESHOLDS`）は変更しない
- critic 側は独自閾値（`groundedness_min=0.6` など）を持つが、CI の thresholds を **上限** として絶対超えない（CI で OK と判定したものを runtime が NG とすると不整合）

### D4: 移行は Shadow Mode を必須にする

Stage 2 (Semantic Router) を **shadow mode** で並走させ、既存 rule との不一致を 1 週間 LangSmith に蓄積してから切替。
critic ノードも初期は **記録のみ・repair off** で配置し、Phase 4 から self-repair を有効化する。

## Consequences

### Positive

- **キーワード追加運用の終焉**: 新しい言い回しは `routes.yaml` に 1 行追記、関連 PR 規模が激減
- **多言語の取りこぼし減少**: cosine 類似度で zh/ko の OOV も吸収。Q-gate FAIL の構造的削減
- **本番 100% カバレッジの quality 可視化**: LangSmith dashboard で `critic_score` を時系列観測
- **failure mode の自動修復**: groundedness 低下時 1 回 retry で UX 損失を局所化
- **ファイル規模の coding-style 整合**: 800 行制限超過の 3 ファイルが解消
- **Codex CLI 経路 C 委任が容易**: utterance 量産は典型的 Codex タスク

### Negative

- **新規依存**: `semantic-router`, `fastembed`（ONNX runtime）の追加 → Cloud Run image size 増加 (~50MB)
- **LangSmith 課金**: trace 量に応じた cost。Phase 0 で sampling 比率を 100% → 必要なら段階的に 10% へ
- **Cold start 増加**: FastEmbed model preload で +1–2s。既存 STT preload と同じパターンで吸収
- **Critic latency tail**: p99 で +200–300ms（LLM judge 経路）。ただし async fire-and-forget で平常 latency には影響しない設計
- **学習曲線**: チームに Semantic Router / LangSmith の knowledge transfer が必要

### Risk Mitigation

| Risk | Mitigation |
|---|---|
| Semantic Router が既存 rule より精度低い | Phase 2 で 1 週間 shadow 計測。不一致率 >5% なら切替延期 |
| Self-repair で無限ループ | 1 回固定上限・total 30s timeout・`fallback_to_original` の 3 層防御 |
| LangSmith 障害で本番落ちる | trace は async fire-and-forget。失敗してもユーザー応答は返す |
| Cloud Run cold start で SLO 違反 | FastEmbed の model warmup を既存 `stt_warmup_service.py` パターンで起動時実行 |
| 既存 RAGAS との二重計測 | RAGAS は週1 → nightly に降格、runtime critic と分業 |

## Rollout Plan（Phase 別、各 Phase = 1 PR 単位）

| Phase | 内容 | 期間 | 担当候補 | 完了条件 |
|---|---|---|---|---|
| **0** | LangSmith tracing 配線（`backend/main.py` startup_event に 5 行追加）+ `settings.langsmith_project` フィールド追加。RAGAS を nightly に降格 | 0.5 日 | backend-developer | 本番 100% の turn が LangSmith dashboard に出る |
| **1** | `critic_node` 追加（**決定論シグナルのみ、LLM judge off、repair off**）+ trace へ critic_score emit | 2–3 日 | backend-developer + tdd-guide | critic_score が全 turn に付く。groundedness 分布が LangSmith で観測可能 |
| **2** | `backend/routing/semantic_router.py` 新設、`routes.yaml` 初期版を **shadow mode** で並走。不一致を LangSmith カスタムスコア `routes_mismatch` で記録 | 1 週間（実装3日 + データ収集5日） | backend-developer + Codex CLI 経路 C (utterance 量産) | 1 週間 shadow 計測完了、不一致率 ≤5% |
| **3** | `routes.yaml` を正系に昇格。`classify_fast_intent` を 35 分岐 → safety hard rule 5 つに減量。`routing_constants.py` を ≤300 行・`intent_classifier.py` を ≤120 行に削減 | 1 週間 | backend-developer | Q-gate 4 FAIL → 0、CI green、ファイル行数達成 |
| **4** | LLM-as-judge を critic に追加（gemini-flash-lite）。`routing_correctness` を活用し `routes.yaml` 半自動学習データ抽出スクリプト追加。**self-repair (1 retry) を有効化** | 1 週間 | backend-developer + e2e-runner | repair 後 PASS 率 ≥70%、p95 latency 増加 ≤300ms |
| **5** | `main_workflow.py` を subgraph 分割 (routing_subgraph / critic_subgraph / format_subgraph)。各 ≤800 行 | 1 週間 | architect + backend-developer | 全 ファイル 800 行以下、subgraph 単体テスト追加、E2E green |

### Phase 別 PR 規律

- ブランチ命名: `feat/router-phase{N}-{slug}`
- 全 PR `--base develop`
- code-reviewer + Codex CLI 経路 A レビュー必須（CLAUDE.md 規約準拠）
- Phase 1 / 4 は backend Python なので `cd backend && ruff check . && black --check . && pytest -m "not ragas and not slow"` を CI gate
- Phase 0 の LangSmith trace 有効化後、各 Phase 完了時に **LangSmith dashboard スクショ** を PR 本文に添付（後工程の証跡）

## Alternatives Considered

### A1: pgvector で自作 Semantic Router

既存 Supabase pgvector を流用、新規依存ゼロ。
**却下理由**: hybrid (BM25+dense) を自前実装する工数が、`semantic-router` 採用工数を超える。voice latency 用途では FastEmbed の ONNX in-process 推論が pgvector 経由 RPC より明確に速い。pgvector は引き続き knowledge_base 用途で残す。

### A2: RouteLLM (lm-sys) を採用

LLM model selection 寄りの設計で、Engineer Cafe Navigator の "intent → agent 選択" には粒度が合わない。
**却下理由**: voice kiosk の細粒度 intent 判定には less suited。将来 LLM provider 多重化時に再検討の余地あり。

### A3: Langfuse を採用

OSS, self-host 可、OpenTelemetry ネイティブ。
**保留**: Phase 0 では LangSmith（既に `langsmith_api_key` フィールド配線済みで即時有効化可能）を採用。Phase 4 完了後にコスト・運用面で Langfuse migration を別 ADR で検討。

### A4: Self-repair なし、critic は guardrail (PII / toxicity / language mismatch) だけ

Latency tail を完全に避けたい場合の保守解。
**却下理由**: 質問に対する fail recovery を運用 PR で行う現状を維持してしまう。Phase 1 で repair off の critic を入れて十分なデータ取得後に Phase 4 で有効化、というステージングなら risk を抑えられる。

## References

### 本リポジトリ内

- [ADR-006: LangGraph workflow redesign](006-langgraph-workflow-redesign.md) — 現行 keyword fast-path 導入の経緯
- [ADR-014: Observability phase 1a](014-observability-phase1.md) — 構造化ログ基盤
- [ADR-017: Observability phase 1b](017-observability-phase1b.md) — Terraform メトリクス・アラート
- [ADR-018: Alpha fast response and assistant profile routing](018-alpha-fast-response-and-assistant-profile-routing.md) — `is_assistant_profile_question` の経緯
- [ADR-019: Alpha live RAGAS case accounting](019-alpha-live-ragas-case-accounting.md) — C-127 ケース会計
- `~/.claude/projects/-Users-teradakousuke-Developer-engineer-cafe-navigator2025/memory/MEMORY.md` — Phase 3.6 残課題（B-1〜B-4）と本 ADR の関連

### 外部

- [aurelio-labs/semantic-router](https://github.com/aurelio-labs/semantic-router)
- [aurelio-labs/semantic-router — hybrid-router example](https://github.com/aurelio-labs/semantic-router/blob/main/docs/examples/hybrid-router.ipynb)
- [aurelio-labs/semantic-router — FastEmbed integration](https://github.com/aurelio-labs/semantic-router/blob/main/docs/encoders/fastembed.ipynb)
- [Deepchecks: What is Semantic Router? (2026)](https://www.deepchecks.com/glossary/semantic-router/)
- [vLLM Semantic Router blog (2025/09)](https://blog.vllm.ai/2025/09/11/semantic-router.html)
- [Red Hat Developer: LLM Semantic Router (2025/05)](https://developers.redhat.com/articles/2025/05/20/llm-semantic-router-intelligent-request-routing)
- [lm-sys/RouteLLM](https://github.com/lm-sys/RouteLLM)
- [withmartian/routerbench](https://github.com/withmartian/routerbench)
- [IBM Research: LLM routers](https://research.ibm.com/blog/LLM-routers)
- [langchain-ai/langgraph-reflection](https://github.com/langchain-ai/langgraph-reflection)
- [Building Self-Evaluating Systems With LangGraph (Science Techniz, 2026/02)](https://www.sciencetechniz.com/2026/02/building-self-evaluating-systems-with.html)
- [Next-Generation Agentic RAG with LangGraph (Medium, 2026/03)](https://medium.com/@vinodkrane/next-generation-agentic-rag-with-langgraph-2026-edition-d1c4c068d2b8)
- [LangSmith Evaluation Platform](https://www.langchain.com/langsmith/evaluation)
- [Langfuse LLM-as-a-Judge](https://langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge)
- [Agent Observability 2026 ガイド](https://www.digitalapplied.com/blog/agent-observability-2026-evals-traces-cost-guide)
- [Galileo Runtime Protection (2026)](https://galileo.ai/blog/best-ai-agent-evaluation-platforms)
- [Hamming.ai Voice Agent Testing Guide 2026](https://hamming.ai/resources/voice-agent-testing-guide)
- [AssemblyAI: AI voice agents 2026](https://www.assemblyai.com/blog/ai-voice-agents)

## Approvals

- Proposed: Claude Code session (2026-05-17, ツンデレ後輩女子モード) — 設計検討と stack 選定
- Decided: Terada Kousuke (terisuke) — Router=semantic-router / Eval=LangSmith / Self-repair=1 retry/30s budget
- Pending: 担当エンジニアによる Phase 0 PR 起票、Epic GitHub Issue 起票
