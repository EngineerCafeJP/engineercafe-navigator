# Semantic Router + Runtime Self-Evaluation 実装ハンドオフ計画

> **対象 ADR**: [ADR-023](../adr/023-semantic-router-and-runtime-self-evaluation.md)
> **作成**: 2026-05-17 (Claude Code session — terisuke 承認)
> **対象**: 次セッション以降の担当エンジニア
> **前提**: ADR-023 を必読の上、Phase 0 → 5 を順次 PR 化する

本書は ADR-023 の「具体的修正箇所」と「PR ボディ雛形」を提供する**作業手引き**。設計判断の根拠は ADR を参照すること。

---

## 共通ルール（全 Phase 通じて）

### ブランチ・PR
- ブランチ命名: `feat/router-phase{N}-{slug}` 例: `feat/router-phase0-langsmith-tracing`
- 全 PR `--base develop`（CLAUDE.md 規約）
- 1 Phase = 1 PR、複数意図混在禁止
- PR body 必須項目:
  - ADR-023 へのリンク
  - 対象 Phase の "完了条件" を満たした証跡（CI green / ファイル行数 / dashboard スクショ）
  - `Co-Authored-By:` 行

### CI 必須
```bash
cd backend
ruff check .
black --check .
pytest -m "not ragas and not slow" --tb=short -q
```

### レビューパイプライン
1. code-reviewer agent (FULL — Python ソース変更を含むため)
2. Codex CLI 経路 A (`codex exec review`)
3. 両者 LGTM 後にマージ。CRITICAL/HIGH ゼロ必須

### Memory / docs 同時更新（CLAUDE.md hook 強制）
- 各 Phase 完了時に `MEMORY.md` の "Session Status" を更新
- 関連ドキュメント（`docs/architecture/SYSTEM-ARCHITECTURE.md` 等）に router 章を追記

---

## Phase 0: LangSmith Tracing 配線

**期間目安**: 0.5 日
**ブランチ**: `feat/router-phase0-langsmith-tracing`
**目的**: 100% の本番 turn を LangSmith に流す。以降の Phase の数値検証基盤を作る。

### 修正対象

| ファイル | 行 | 変更内容 |
|---|---|---|
| `backend/main.py` | startup_event 内 | LangSmith 環境変数を 3 つ export、log 1 行追加 |
| `backend/config/settings.py` | 既存 `langsmith_api_key` フィールド付近 | `langsmith_project: str = "engineer-cafe-prod"` を追加 |
| `.github/workflows/ragas-evaluation.yml` | cron 行 | `'0 9 * * 1'` → `'0 17 * * *'` (毎日 02:00 JST) に降格 |
| `MEMORY.md` | Session Status | Phase 0 完了を記録 |
| `docs/architecture/SYSTEM-ARCHITECTURE.md` | 観測章 | LangSmith 配線を 1 段落追記 |

### 実装スニペット

```python
# backend/main.py の startup_event 末尾に追加
if settings.langsmith_api_key:
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    logger.info(
        "LangSmith tracing enabled: project=%s",
        settings.langsmith_project,
    )
else:
    logger.info("LangSmith tracing disabled (no api_key)")
```

### Secret Manager

```bash
# GCP Secret Manager に LANGSMITH_API_KEY を追加
echo -n "lsv2_..." | gcloud secrets create LANGSMITH_API_KEY --data-file=-

# Cloud Run へ反映（--update-secrets で既存上書きしない）
gcloud run services update engineer-cafe-backend \
  --region=asia-northeast1 \
  --update-secrets="LANGSMITH_API_KEY=LANGSMITH_API_KEY:latest"
```

### 完了条件
- [ ] Cloud Run revision がデプロイされ、`gcloud run services logs read` で `LangSmith tracing enabled` が確認できる
- [ ] LangSmith dashboard で `engineer-cafe-prod` プロジェクトに live trace が流れている（本番1ターン後にスクショ）
- [ ] CI green、code-reviewer + Codex CLI 経路 A LGTM
- [ ] MEMORY.md に Phase 0 完了記録

### PR ボディ雛形

```markdown
## Summary
ADR-023 Phase 0: LangSmith tracing を本番 backend に配線。以降の semantic router / critic node 実装で必要な observability 基盤を立ち上げる。

## Changes
- `backend/main.py`: startup_event で LangSmith 環境変数を export
- `backend/config/settings.py`: `langsmith_project` フィールド追加
- `.github/workflows/ragas-evaluation.yml`: cron 週1 → 日次に降格

## Evidence
- LangSmith dashboard スクショ (本番 1 turn の trace 表示)
- Cloud Run logs: `LangSmith tracing enabled` 行
- CI green: <CI URL>

## ADR
[ADR-023](docs/adr/023-semantic-router-and-runtime-self-evaluation.md) Phase 0

🤖 Generated with [Claude Code](https://claude.com/claude-code)
Co-Authored-By: Claude <noreply@anthropic.com>
```

---

## Phase 1: critic_node 追加（決定論シグナルのみ）

**期間目安**: 2–3 日
**ブランチ**: `feat/router-phase1-critic-node-deterministic`
**目的**: 全 turn に `critic_score` を付与し、groundedness 分布を LangSmith で観測可能にする。**LLM judge は使わず、self-repair も off**。

### 修正対象

| ファイル | 変更内容 |
|---|---|
| `backend/workflows/critic_node.py` (新設, ≤150行) | `CriticVerdict` Pydantic + `critic_node()` 関数 |
| `backend/workflows/main_workflow.py` | `_build_graph` に critic_node を追加、format_response → critic → END に変更 |
| `backend/workflows/critic_metrics.py` (新設, ≤80行) | LangSmith trace に `critic_score` を非同期 emit するヘルパー |
| `backend/tests/workflows/test_critic_node.py` (新設) | tdd-guide で先に書く。groundedness 0.6/0.8/1.0 の境界テスト |

### 実装スケルトン

```python
# backend/workflows/critic_node.py
from pydantic import BaseModel, Field
from backend.evaluation.quality_signals import (
    language_match_score,
    groundedness_score,  # quality_signals から流用
)
from backend.workflows.critic_metrics import emit_critic_score

class CriticVerdict(BaseModel):
    groundedness: float = Field(ge=0, le=1)
    answer_relevancy: float = Field(ge=0, le=1)
    language_match: float = Field(ge=0, le=1)
    safety: float = Field(ge=0, le=1)
    routing_correctness: float = Field(ge=0, le=1, default=1.0)  # Phase 4 まで 1.0
    needs_repair: bool = False
    repair_hint: str | None = None

async def critic_node(state: dict) -> dict:
    query = state.get("query", "")
    answer = state.get("answer", "")
    language = state.get("language", "ja")
    contexts = state.get("context", {}).get("knowledge_results", {}).get("results", [])

    verdict = CriticVerdict(
        groundedness=groundedness_score(answer, contexts),
        answer_relevancy=1.0,  # Phase 4 で LLM judge 実装
        language_match=language_match_score(answer, language),
        safety=1.0,  # 既存 PII scanner が format_response で処理済み
        needs_repair=False,  # Phase 4 まで always False
    )

    # 非同期 fire-and-forget で trace に emit（応答 latency に影響させない）
    asyncio.create_task(emit_critic_score(state["session_id"], verdict))

    return {"critic_verdict": verdict.model_dump()}
```

```python
# backend/workflows/critic_metrics.py
from langsmith import Client

_client = Client()

async def emit_critic_score(session_id: str, verdict: CriticVerdict) -> None:
    """LangSmith trace に critic_score を non-blocking で emit."""
    try:
        # 既存 trace に metadata 追加
        _client.update_run(
            run_id=...,  # 現在の run_id を thread-local から取得
            extra={"metadata": {"critic": verdict.model_dump()}},
        )
    except Exception as exc:
        logger.warning("critic_score emit failed: %s", exc)
```

### 完了条件
- [ ] tdd-guide で書いた critic_node のテスト 80% カバレッジ達成
- [ ] LangSmith dashboard で全 turn に `critic.groundedness` が表示される
- [ ] 本番 100 turn で `critic.groundedness` 平均値・分布を PR body に記載
- [ ] p95 latency 増加 < 50ms（fire-and-forget なので原則ゼロ）
- [ ] CI green、code-reviewer + Codex CLI 経路 A LGTM

### 注意点
- `groundedness_score` は `quality_signals.py` に既に類似ロジックあり。**新規に書かず、流用する**こと
- `critic_node` 内で例外が起きてもグラフ全体を止めない（try/except で握って WARN log）
- `asyncio.create_task` で fire-and-forget するが、unhandled exception を握り潰さないよう `_log_task_exception` ヘルパー追加

---

## Phase 2: Semantic Router shadow mode

**期間目安**: 1 週間（実装3日 + データ収集5日）
**ブランチ**: `feat/router-phase2-semantic-router-shadow`
**目的**: `aurelio-labs/semantic-router` を導入し、既存 rule と並走させ不一致を計測。

### 修正対象

| ファイル | 変更内容 |
|---|---|
| `backend/pyproject.toml` | `semantic-router[fastembed]>=0.1.x` を追加 |
| `backend/routing/__init__.py` (新設) | パッケージ初期化 |
| `backend/routing/semantic_router.py` (新設, ≤200行) | RouteLayer 初期化、`classify_intent(query) -> RouteHit` |
| `backend/routing/routes.yaml` (新設) | 約 30 ルート、各 utterance 3–5 例 |
| `backend/workflows/main_workflow.py` | `_keyword_router_node` 内で shadow 呼び出し、不一致を `critic_metrics.emit_routes_mismatch` で記録 |
| `backend/services/stt_warmup_service.py` 参考 | FastEmbed model warmup を起動時実行する pattern を流用 |
| `backend/tests/routing/test_semantic_router.py` (新設) | 30 ルート全てに対する正例 + 反例テスト |

### routes.yaml 初期データ作成

**Codex CLI 経路 C 委任候補**: routing_constants.py の各 `*_KEYWORDS` リストから 30 ルート分の代表発話 3–5 例を抽出する単純作業。

```bash
# 経路 C 委任スニペット例（次セッションで担当が実行）
codex orchestrate \
  --task "backend/routing/routes.yaml を作成。backend/config/routing_constants.py の WIFI_KEYWORDS, BUSINESS_HOURS_KEYWORDS, ... 各リストを参照し、ルート名 / target_agent / request_type / utterances (各 3-5 例, ja/en/zh/ko 混在 OK) を yaml で記述"
```

### Shadow mode 実装パターン

```python
# backend/workflows/main_workflow.py の _keyword_router_node 内
fast_route = RoutingLogicAgent._try_fast_routing(self, query)

# Shadow: Semantic Router も呼び出して不一致を記録
try:
    shadow_hit = await semantic_router_classifier.classify_intent(query)
    if fast_route and shadow_hit and fast_route.get("agent") != shadow_hit.target_agent:
        await emit_routes_mismatch(
            session_id=session_id,
            query=query,
            rule_agent=fast_route.get("agent"),
            semantic_agent=shadow_hit.target_agent,
            semantic_score=shadow_hit.score,
        )
except Exception as exc:
    logger.warning("Semantic router shadow failed: %s", exc)

# 既存 rule の結果をそのまま使う（shadow なので動作変更なし）
```

### 完了条件
- [ ] `routes.yaml` に 30 ルート以上、ja/en/zh/ko すべての utterance を含む
- [ ] FastEmbed model が Cloud Run 起動時に preload される（cold start +2s 程度想定）
- [ ] 1 週間 shadow 計測結果を PR body に記載: **不一致率 ≤ 5%** が目標
- [ ] 不一致 case を analytical に grouping し、`routes.yaml` 改善案 issue を起票
- [ ] CI green、code-reviewer + Codex CLI 経路 A LGTM

---

## Phase 3: routes.yaml 正系昇格 + intent_classifier 減量

**期間目安**: 1 週間
**ブランチ**: `feat/router-phase3-cutover-and-shrink`
**目的**: Semantic Router を正系にし、`intent_classifier.py` を 734 → ≤120 行・`routing_constants.py` を 1147 → ≤300 行に削減。

### 修正対象

| ファイル | Before | After | 変更内容 |
|---|---|---|---|
| `backend/utils/intent_classifier.py` | 734 | ≤120 | `classify_fast_intent` を safety hard rule 5 つに減量 (emergency / farewell / assistant_profile / pet_policy / lost_found) |
| `backend/config/routing_constants.py` | 1147 | ≤300 | キーワードリストを削除、`CATEGORY_TO_AGENT_MAP` と `REQUEST_TYPE_TO_AGENT_MAP` のみ維持 |
| `backend/workflows/main_workflow.py` | 2274 | (Phase 5 で対応) | `_keyword_router_node` を Stage 1+2 (regex → semantic_router) 呼び出しに置換 |
| `backend/agents/orchestrator_agent.py` | 401 | 同等 | `_try_fast_routing` を Stage 2 (semantic_router) に置換、`_is_memory_related_question` も semantic で吸収可能か検証 |
| `backend/tests/utils/test_intent_classifier.py` | 既存 | 該当 hard rule のみ残す | 削除した 30 ルートのテストは Phase 2 で routes.yaml 側に移譲済み |

### 安全策

- 1 PR の中で **rule 削除と semantic_router 昇格を同時に行う**（並走を絶つ）
- shadow 期間で確認した不一致 ≤ 5% を超えていたら Phase 3 を延期
- Phase 4 で routing_correctness を計測予定なので、Phase 3 完了直後に Q-gate を手動 1 回回し FAIL ≤ 1 を確認

### 完了条件
- [ ] `intent_classifier.py` ≤120 行、`routing_constants.py` ≤300 行
- [ ] Q-gate（BIZ-JA-002 / RECV-JA-002 / SAFE-JA-001 / SAFE-EN-001 含む）すべて PASS
- [ ] LangSmith dashboard で routing 経路（regex / semantic / llm fallback）の割合を可視化、LLM fallback 比率 ≤ 10% 目標
- [ ] CI green、code-reviewer + Codex CLI 経路 A LGTM

---

## Phase 4: LLM-as-judge + self-repair 有効化 + routes 半自動学習

**期間目安**: 1 週間
**ブランチ**: `feat/router-phase4-llm-judge-and-repair`
**目的**: critic に LLM judge を追加し、`needs_repair=true` 時に 1 回 retry。`routes.yaml` の改善 PR を半自動生成。

### 修正対象

| ファイル | 変更内容 |
|---|---|
| `backend/workflows/critic_node.py` | gemini-flash-lite で answer_relevancy + routing_correctness を判定 |
| `backend/workflows/main_workflow.py` | critic → conditional_edge → (repair branch | END)、retry counter を state に追加 |
| `backend/workflows/repair_branch.py` (新設) | `repair_hint` に応じて agent 再選択 or context 拡張 |
| `scripts/extract_route_improvements.py` (新設) | LangSmith trace から `routing_correctness < 0.7` の case を抽出し routes.yaml 追加候補を生成 |
| `.github/workflows/route-improvement-pr.yml` (新設) | 週1 cron で上記スクリプト実行 → PR 自動起票 |

### 完了条件
- [ ] Self-repair 後 PASS 率 ≥ 70%（Phase 1 で計測した baseline と比較）
- [ ] p95 latency 増加 ≤ 300ms（repair branch 経路）
- [ ] `total_timeout=30s` を 1 turn でも破らない（既存 `asyncio.wait_for` で担保）
- [ ] 週1 で route_improvement PR が自動起票され、人がレビュー・マージ
- [ ] CI green、code-reviewer + Codex CLI 経路 A LGTM

---

## Phase 5: main_workflow.py を subgraph 分割

**期間目安**: 1 週間
**ブランチ**: `feat/router-phase5-subgraph-split`
**目的**: 800 行制限超過の解消。テスト性回復。

### 修正対象

| ファイル | Before | After |
|---|---|---|
| `backend/workflows/main_workflow.py` | 2274+ (Phase 4 で 100行程度増加見込み) | ≤ 800 |
| `backend/workflows/subgraphs/routing_subgraph.py` (新設) | — | ≤ 400 |
| `backend/workflows/subgraphs/critic_subgraph.py` (新設) | — | ≤ 300 |
| `backend/workflows/subgraphs/format_subgraph.py` (新設) | — | ≤ 400 |
| `backend/tests/workflows/subgraphs/*` (新設) | — | 各 subgraph 単体テスト |

### 完了条件
- [ ] 全ファイル 800 行以下
- [ ] 各 subgraph の単体テスト追加、カバレッジ 80% 以上
- [ ] E2E (Playwright `voice-e2e-nightly.yml`) green
- [ ] CI green、code-reviewer + Codex CLI 経路 A LGTM

---

## GitHub Epic & Sub-Issue 起票案

Epic 1 件 + Phase ごとの sub-issue 6 件を起票する。雛形：

### Epic タイトル
> `[Epic] Routing modernization & runtime self-evaluation (ADR-023)`

### Epic 本文（雛形）
```markdown
ADR-023 に基づき、キーワード爆発状態のルーティング層を Semantic Router 三段カスケードに置換し、LangGraph に runtime self-evaluation ループ (critic_node + 1 回 self-repair + LangSmith trace) を追加する。

## なぜ今やるか
- routing_constants.py 1147 行、intent_classifier.py 734 行、main_workflow.py 2274 行 (800 行制限の 2.8 倍)
- Q-gate FAIL が出るたびにキーワード追加 → 永久肥大化
- LLM オーケストレーターがあるのに自己評価ループが無く、評価は DB SELECT + 週1 RAGAS のみ

## 設計判断
- ADR-023 (docs/adr/023-semantic-router-and-runtime-self-evaluation.md) — Accepted
- Router lib: aurelio-labs/semantic-router + FastEmbed
- Eval backend: LangSmith (Phase 0 即時有効化)
- Self-repair: 1 retry, 30s total budget

## Phase 別 sub-issue
- [ ] #NN Phase 0: LangSmith tracing 配線
- [ ] #NN Phase 1: critic_node 追加（決定論シグナルのみ）
- [ ] #NN Phase 2: Semantic Router shadow mode
- [ ] #NN Phase 3: routes.yaml 正系昇格 + intent_classifier 減量
- [ ] #NN Phase 4: LLM-as-judge + self-repair 有効化
- [ ] #NN Phase 5: main_workflow.py subgraph 分割

## 関連
- docs/plans/semantic-router-self-eval-2026-05-17.md (実装ハンドオフ計画)
- 関連 ADR: 006, 014, 017, 018
- MEMORY.md Phase 3.6 残課題 (B-1〜B-4) と本 Epic で並行解消可能
```

### Sub-issue 雛形（Phase N 用）
```markdown
## Epic
#<Epic 番号>

## ADR
docs/adr/023-semantic-router-and-runtime-self-evaluation.md — Phase N

## 詳細
docs/plans/semantic-router-self-eval-2026-05-17.md の "Phase N" セクション参照。

## 完了条件
- (ハンドオフ計画書の Phase N "完了条件" 全てを転記)

## 推定工数
N 日

## 担当ロール
backend-developer (+ tdd-guide / Codex CLI 経路 C を使う場合は明記)
```

### 起票コマンド例
```bash
# Epic
gh issue create \
  --repo EngineerCafeJP/engineer-cafe-navigator2025 \
  --title "[Epic] Routing modernization & runtime self-evaluation (ADR-023)" \
  --body-file <(cat <<'EOF'
...Epic 本文...
EOF
) \
  --label "epic,architecture,routing"

# Phase 0 sub-issue
gh issue create \
  --repo EngineerCafeJP/engineer-cafe-navigator2025 \
  --title "[Phase 0] LangSmith tracing 配線 (ADR-023)" \
  --body-file <(cat <<'EOF'
## Epic
#<Epic 番号>
...
EOF
) \
  --label "phase-0,observability,routing"

# Phase 1〜5 も同パターン
```

---

## 引き継ぎチェックリスト（担当エンジニア向け）

着手前に以下を完了：

- [ ] ADR-023 を通読
- [ ] 本ハンドオフ計画書を通読
- [ ] `git pull origin develop` 最新化
- [ ] 該当 Phase のブランチを切る (`git checkout -b feat/router-phaseN-...`)
- [ ] `cd backend && pytest -m "not ragas and not slow" --tb=short -q` が手元で green
- [ ] LangSmith アカウント作成（Phase 0 担当者のみ）
- [ ] GCP `LANGSMITH_API_KEY` シークレット権限確認（Phase 0 担当者のみ）
- [ ] Codex CLI 経路 C の utterance 量産依頼を準備（Phase 2 担当者のみ）

着手後：

- [ ] tdd-guide で先にテストを書く（Phase 1, 4, 5）
- [ ] 各 Phase 完了時に MEMORY.md の "Session Status" を更新
- [ ] PR body にハンドオフ計画書の "完了条件" チェックを転記し、すべて埋める
- [ ] code-reviewer + Codex CLI 経路 A の両 LGTM を得る
- [ ] 次 Phase の sub-issue へ進捗を引き継ぐ

---

## 関連ドキュメント

- [ADR-023](../adr/023-semantic-router-and-runtime-self-evaluation.md) — 本計画の設計判断記録
- [ADR-006](../adr/006-langgraph-workflow-redesign.md) — 現行 keyword fast-path 導入経緯
- [ADR-014](../adr/014-observability-phase1.md) — 構造化ログ
- [ADR-017](../adr/017-observability-phase1b.md) — Terraform メトリクス
- [`CLAUDE.md`](../../CLAUDE.md) — リポジトリ全体規約
- [`.claude/rules/workflow.md`](../../.claude/rules/workflow.md) — 2-Agent ワークフロー
- `MEMORY.md` (project root) — セッション継続情報
