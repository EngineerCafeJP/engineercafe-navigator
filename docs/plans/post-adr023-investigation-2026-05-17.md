# Post-ADR-023 Investigation Report — Memory / Reception / Frontend / Evaluation

> **作成**: 2026-05-17, Claude Code session (terisuke と対話)
> **位置付け**: ADR-023 採択後、ユーザー指示による次フェーズの調査報告 (実装前ファクトファインディング)
> **対象**: 次セッション以降の担当エンジニア・PM
> **方針**: 本書はあくまで「事実 + 提案」のレポート。コード変更ゼロ。意思決定後に ADR-024 / ADR-025 として正式化する。
> **証跡**: GCP Cloud Logging 直接クエリ (2026-05-01 〜 2026-05-17, ~2,000 chat_response events)、コード grep、2026/05 時点 web research

---

## 0. Executive Summary

ADR-023 (Semantic Router + Critic node) はルーティングの肥大化を解くが、**それと並走で解くべき構造的負債が 3 系統ある**：

| 系統 | 重症度 | 1 行サマリ |
|---|---|---|
| **メモリ (STM/LTM)** | 🔴 Critical | LTM は 17 日間 **100% skip**、agent_memory は **O(N) 全件 scan**、観測性 **ゼロ** |
| **受付システム** | 🟠 High | `/api/reception/respond` が 17 日間 **0 calls**（dead code）、`public.users` テーブル未存在で起動毎 warning |
| **フロントエンド proxy** | 🟡 Medium | ADR-021 の方針通り FE/BE 分離が先。Vite 化はその後（28 proxy route が残るうちは意味薄） |

→ **ADR-024 (Memory & Reception Modernization)** と **ADR-025 (Frontend Proxy Deletion → Vite)** を新規起票し、ADR-023 と並列実行する Phase 計画を作るのが推奨。

---

## 1. 調査手法

### 1.1 静的解析対象
- [`backend/utils/memory_helper.py`](../../backend/utils/memory_helper.py) (780 行)
- [`backend/services/memory_promoter.py`](../../backend/services/memory_promoter.py) (280 行)
- [`backend/utils/memory_extractor.py`](../../backend/utils/memory_extractor.py) (353 行)
- [`backend/workflows/reception_workflow.py`](../../backend/workflows/reception_workflow.py) (598 行)
- [`backend/services/reception_handoff_service.py`](../../backend/services/reception_handoff_service.py) (193 行)
- [`backend/services/purpose_flow_service.py`](../../backend/services/purpose_flow_service.py) (445 行)
- [`backend/services/visitor_identification_service.py`](../../backend/services/visitor_identification_service.py) (288 行)
- [`backend/utils/purpose_classifier.py`](../../backend/utils/purpose_classifier.py) (200+ 行)
- [`backend/observability/structured_logger.py`](../../backend/observability/structured_logger.py)
- [`backend/api/reception.py`](../../backend/api/reception.py)
- [`backend/supabase/migrations/20250529005253_init_engineer_cafe_navigator.sql`](../../backend/supabase/migrations/20250529005253_init_engineer_cafe_navigator.sql) (agent_memory / conversation_* schema)
- [`backend/supabase/migrations/20260308000001_add_reception_tables.sql`](../../backend/supabase/migrations/20260308000001_add_reception_tables.sql) (visits schema)
- [`docs/adr/021-frontend-backend-separation-before-react-vite.md`](../adr/021-frontend-backend-separation-before-react-vite.md)
- frontend tree (178 .ts/.tsx, 28 API route handlers)

### 1.2 動的解析対象（GCP Cloud Logging）
- 期間: **2026-05-01 〜 2026-05-17 (17 日間)**
- service: `engineer-cafe-backend` (Cloud Run, `asia-northeast1`, project `aipartner-426616`)
- サンプル: chat_response ~2,000 events / request log ~3,000 / stdout structured ~3,000

### 1.3 外部 research (2026/05 時点)
- AI agent memory: Mem0 v2 (2026/04 release), Letta, Zep, MemGPT 比較
- LangGraph Store: hierarchical namespace pattern, AsyncPostgresStore
- 評価: LangSmith × RAGAS 自動 trace 連携 (公式)
- Voice receptionist: 2026 production architecture surveys
- Next → Vite migration (kiosk / static dashboard 用途)

---

## 2. 系統 A: メモリ (STM/LTM) — Critical

### 2.1 [A1] LTM 書き込みが production で **100% skip** されている

#### 観測事実
GCP 17 日間、`chat_response` event の `ltm_store_write` フィールド：

```
=== chat_response ltm_store_write 分布 (n=2000) ===
2000  skipped
   0  success
   0  failed
```

#### 根本原因
[`backend/observability/structured_logger.py:131-138`](../../backend/observability/structured_logger.py:131) `_coerce_ltm_store_write` は `metadata.get("ltm_store_write")` を読むだけ。grep で全 production code を調べると：

```bash
grep -rn 'metadata\["ltm_store_write"\]\|"ltm_store_write":' backend/ --include="*.py" | grep -v test
# → backend/observability/structured_logger.py:170 (consumer side) のみ
```

**setter が production code に存在しない**。LTM write を行う [`backend/workflows/main_workflow.py:1893-1906`](../../backend/workflows/main_workflow.py:1893) (`_write_long_term_memory` / `extract_memories`) は呼ばれているはずだが、結果を `metadata["ltm_store_write"]` に reflect していない。

#### 影響
- 「LTM が動いているか」を本番で観測する手段が **ゼロ**
- ADR-011 (LTM cross-session design) の Exit Criterion #3「LTM write を trace で確認」が **未達**
- MEMORY.md "Phase 3.6" の `M-LTM-003`（cross-session recall）が出続けている根本原因の一つ

#### 影響を受けるユーザーケース
- 訪問者の「私の名前は○○です」が次回来訪時に思い出されない（LTM 書き込み失敗の可能性高）
- 「前回お話しした件ですが…」がノーコンテキストで返される

### 2.2 [A2] agent_memory が O(N) 全件 scan アンチパターン

#### 観測事実
[`backend/utils/memory_helper.py:267-275`](../../backend/utils/memory_helper.py:267) `_get_recent_messages`:

```python
response = (
    self.supabase.table("agent_memory")
    .select("*")
    .eq("agent_name", self.agent_name)       # all messages globally
    .like("key", "message_%")                # all messages
    .order("created_at", desc=True)
    .limit(self.max_entries * 3)             # 300 rows pulled
    .execute()
)

if not response.data:
    return []

# session_idでフィルタリングしてメッセージを整形
messages = []
for item in response.data:
    value = item.get("value", {})
    if value.get("sessionId") == session_id:  # Python-side filter!
        ...
```

#### スキーマ証跡
[`backend/supabase/migrations/20250529005253_init_engineer_cafe_navigator.sql`](../../backend/supabase/migrations/20250529005253_init_engineer_cafe_navigator.sql) より:

```sql
CREATE TABLE agent_memory (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  agent_name varchar(100) NOT NULL,
  key varchar(255) NOT NULL,
  value jsonb NOT NULL,
  ...
);
CREATE INDEX idx_agent_memory_agent_key ON agent_memory(agent_name, key);
```

**`value->>'sessionId'` への index 無し**。

#### 影響
- 同じパターンを [`backend/utils/memory_helper.py:559-603`](../../backend/utils/memory_helper.py:559) `cleanup_session`、[`backend/utils/memory_helper.py:605-657`](../../backend/utils/memory_helper.py:605) `cleanup` (グローバル) も繰り返す
- `cleanup()` は全 `ended` セッション × 全 message を Python で join → delete を **1 件ずつループ** で呼ぶ
- kiosk 運用が続けば agent_memory レコード数に対し線形 slowdown
- 1 turn の `get_context` で 300 件 pull → Python filter で 5-10 件残す = ネットワーク I/O と JSON parse が **30-60 倍の無駄**

#### 影響を受けるユーザーケース
- セッション持続時間に応じて memory loader latency が悪化 (chat p95=7.36s の主因の一つ候補)

### 2.3 [A3] STM が二重保存

- LangGraph Checkpointer (AsyncPostgresSaver) は会話を `messages: Annotated[list[BaseMessage], add_messages]` として保持 (`backend/workflows/main_workflow.py:361`)
- 並列で `SimplifiedMemoryHelper.store_message` が agent_memory に同じ会話を保存 (`backend/workflows/main_workflow.py:1786-1791`)

→ **同じデータを 2 つの異なるストレージに 2 重保存**。整合性が取れない。

### 2.4 [A4] memory_extractor は regex 拘束 — Semantic 解釈ゼロ

[`backend/utils/memory_extractor.py:164-199`](../../backend/utils/memory_extractor.py:164) `_extract_name`:

```python
patterns = [
    r"(?:私は|僕は|わたしは|ぼくは|俺は|おれは|名前は)\s*([^\s、。,\.]+)",
    r"([^\s、。,\.]+)\s*(?:です|だよ|と申します|といいます)",
]
```

[`backend/utils/memory_extractor.py:265-286`](../../backend/utils/memory_extractor.py:265) `_extract_episode_incident`:

```python
patterns = [
    r"(?:今日は|本日は)\s*(.+?)(?:で来ました|で参りました|のために来ました)",
    r"(.+?)(?:をしに来ました|しに来ました)",
    r"(?:もくもく会|ハッカソン|勉強会|ミートアップ|イベント)(?:で|に)(.+)",
]
```

→ ADR-023 で潰そうとしている routing keyword 爆発と **完全に同じアンチパターン**。「新しい言い回し → regex 追加 → さらに追加…」の地獄。

### 2.5 メモリ系の 2026/05 ベスト・プラクティス対比

| 比較軸 | 現状 (Engineer Cafe Navigator) | 2026/05 業界水準 |
|---|---|---|
| **アーキテクチャ** | session-bound 単純 DB + 候補昇格 | Mem0 / Letta / Zep の hierarchical (episodic / semantic / procedural) |
| **抽出手法** | regex | LLM extract + semantic dedupe |
| **storage** | flat agent_memory + LangGraph Store の 2 系統並存 | 階層 namespace (`("users", id, "facts" / "episodes" / "preferences")`) |
| **forgetting** | session ended で全削除 (アクティブな compress 無し) | active forgetting (temporal decay + relevance scoring) |
| **search** | bigram cosine 自前実装 ([memory_helper.py:367-392](../../backend/utils/memory_helper.py:367)) | hybrid (semantic + BM25 + entity) |
| **観測性** | ゼロ | LangSmith / Langfuse trace span に critic_score を付ける |
| **benchmark** | unit / integration tests のみ | LoCoMo / LongMemEval (ICLR 2025) |

参考 references:
- [Mem0: State of AI Agent Memory 2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026)
- [Letta: Benchmarking AI Agent Memory (LongMemEval)](https://www.letta.com/blog/benchmarking-ai-agent-memory)
- [LangChain: Long-term memory docs](https://docs.langchain.com/oss/python/langchain/long-term-memory)
- [Five Agent Memory Types in LangGraph (dev.to)](https://dev.to/sreeni5018/five-agent-memory-types-in-langgraph-a-deep-code-walkthrough-part-2-17kb)
- [arxiv 2510.27246: Benchmarking and Enhancing Long-Term Memory in LLMs](https://arxiv.org/pdf/2510.27246)
- [Analytics Vidhya: Architecture and Orchestration of Memory Systems in AI Agents](https://www.analyticsvidhya.com/blog/2026/04/memory-systems-in-ai-agents/)

---

## 3. 系統 B: 受付システム — High

### 3.1 [B1] `/api/reception/respond` は 17 日間 **0 calls** = dead code

#### 観測事実
```
=== Reception endpoints traffic (17 days) ===
/api/reception/start          158 calls (200 OK)
/api/reception/sensor-status  134 calls (polling)
/api/reception/sensor-trigger  16 calls (200 OK)
/api/reception/status/<id>      1 call
/api/reception/respond          0 calls  ← DEAD
/api/reception/complete         0 calls  ← DEAD
```

#### 静的証跡
- [`backend/api/reception.py:501-598`](../../backend/api/reception.py:501) `respond_reception` handler は実装済み
- [`backend/api/reception.py:601+`](../../backend/api/reception.py:601) `complete_reception` も実装済み
- frontend proxy も存在: [`frontend/src/app/api/reception/respond/route.ts`](../../frontend/src/app/api/reception/respond/route.ts), [`frontend/src/app/api/reception/complete/route.ts`](../../frontend/src/app/api/reception/complete/route.ts)

#### 実態
受付の stage 遷移は **main_workflow.py 内の `invoke_reception_subgraph()` で全部処理されている** (chat_response の `route=reception` が 38 件出ている → 進んでいる)。`/api/reception/respond` は誰も呼ばない仕様になっている。

#### 影響
- ADR-006 が宣言した「Reception 一本化」は **半分しか達成されていない**
- backend/api/reception.py 約 700 行のうち、respond / complete ハンドラ (約 200 行) は **dead code**
- 新規メンバーが reception flow を読み解くとき、2 つの実装を読まされる

### 3.2 [B2] `public.users` テーブル未存在で起動毎 warning

[`backend/services/visitor_identification_service.py:239-259`](../../backend/services/visitor_identification_service.py:239):

```python
@staticmethod
def _classify_user_lookup_error(exc: Exception) -> str:
    ...
    missing_table_markers = (
        "pgrst205",
        "42p01",
        "could not find the table",
        "schema cache",
        'relation "public.users" does not exist',
        'relation "users" does not exist',
    )
    if any(marker in error_text for marker in missing_table_markers):
        return "users_table_unavailable"
```

**`public.users` テーブルは backend/supabase/migrations/ に存在しない**:

```bash
grep -rn "CREATE TABLE.*users" backend/supabase/migrations/
# → reception tables 内に users への外部キー言及はあるが、users 本体の DDL は無し
```

→ NFC / member 番号で identify_by_member_number_with_lookup が呼ばれる度に Supabase 例外 → warning ログが永続的に出続けている (実観測: 警告は他の noise に埋もれているが、機能としては未実装)。

### 3.3 [B3] 受付 start から先に進む率が低い

- `/api/reception/start` 158 件 (200 OK)
- chat_response で `route=reception` 38 件 = **start から先に進む率 24%**
- sensor-status polling 134 件 — start を踏まない待機ポーリングが多い

→ 「ボタンを押した / センサーが鳴った → 何も応答が返ってこない / 諦められた」セッションが 76% 存在する可能性。

### 3.4 [B4] purpose_classifier も同じキーワード爆発パターン

[`backend/utils/purpose_classifier.py:36-95`](../../backend/utils/purpose_classifier.py:36) `_PURPOSE_KEYWORDS`:

```python
"facility_use": ["作業", "仕事", "勉強", "コーディング", "プログラミング", "work", "study",
                  "coding", "programming", "coworking", "Wi-Fi", "wifi", "電源", "power",
                  "席", "seat", "利用", "使いたい"],
"event_participation": ["イベント", "勉強会", "セミナー", "ワークショップ", "ハッカソン",
                         "もくもく会", "LT", "ミートアップ", "meetup", "event", "seminar",
                         "workshop", "hackathon", "参加", "申し込み", "register", "attend"],
"tour": ["見学", "見て", "案内", "ツアー", "tour", "visit", "look around", "show me"],
"consultation": ["相談", "アドバイス", "メンタリング", "技術相談", "consult", "advice",
                  "mentoring"],
```

→ ADR-023 で潰そうとしている問題と **同じ構造**。Semantic router に統合するのが筋。

---

## 4. 系統 C: 観測性ギャップ

### 4.1 structured logger は 3 event family しか持たない

GCP 17 日間、stdout structured event 種別の全集計:

```
487  chat_response
272  tts_complete / tts_cache
238  stt_model_load_complete
... (全て stt_* / tts_* / chat_response 系統)
  0  memory_*
  0  reception_transition
  0  ltm_promote
  0  candidate_aggregate
```

→ memory / reception の構造化イベントは **一切 emit されていない**。

### 4.2 route フィールドに class 名が漏れている

chat_response の `route` 分布:

```
712  facility-info       ← category
629  BusinessInfoAgent   ← agent class 名がそのまま！
156  ...                   (en / ja 別)
137  EventAgent          ← 同上
132  general_knowledge
119  general
 48  unknown
 38  reception
```

[`backend/observability/structured_logger.py:148-154`](../../backend/observability/structured_logger.py:148):

```python
route = (
    metadata.get("route")
    or metadata.get("category")
    or metadata.get("agent")         # ← class 名が漏れる
    or metadata.get("request_type")
    or "unknown"
)
```

→ `metadata["route"]` を呼び出し側で必ず set していないために class 名や `unknown` が混じる。analytics 不能。

### 4.3 chat latency tail が 30s budget の限界

```
chat_response (17 days, n=2000):
  p50  = 1,616 ms
  p90  = 4,873 ms
  p95  = 7,350 ms
  p99  = 12,793 ms
  max  = 26,702 ms  ← 30s budget まで残り 3.3s
```

5000ms 超え route 内訳: `general` 188件 / `BusinessInfoAgent` 83件 / `general_knowledge` 50件 / `facility-info` 42件 / `EventAgent` 26件

→ ADR-023 で critic / self-repair を入れると確実に budget 内で収まらないケースが出る。
→ critic は **必ず fire-and-forget**、self-repair の latency 上限を明示する必要がある (既に ADR-023 で 1 retry/30s で守る方針)。

---

## 5. 系統 D: フロントエンド

### 5.1 現状定量

| 項目 | 値 |
|---|---|
| `frontend/src/**/*.{ts,tsx}` ファイル数 (excl. tests) | 178 |
| 総行数 | 35,348 |
| `frontend/src/app/api/**/route.ts` 数 | **28** (ADR-021 時点 29 から 1 減) |
| Top 3 巨大ファイル | `VoiceInterface.tsx` 1,824 / `CharacterAvatar.tsx` 1,555 / `ReceptionPdfGuide.tsx` 1,304 |
| Next.js | 15.3.9 (App Router) |
| React | 19.1.0 |
| Tailwind | 3.4.17 (重要: v4 にしない) |

### 5.2 ADR-021 既存方針が正しい

[`docs/adr/021-frontend-backend-separation-before-react-vite.md`](../adr/021-frontend-backend-separation-before-react-vite.md) で **"Vite 化より先に FE/BE 分離を行う"** とすでに Accept されている。

理由:
- proxy routes 28 ファイルが**主たる削除可能サーフェス**であり、Vite 化単体ではこれが消えない
- backend がまず auth / CORS / rate limit / public API contract を所有する必要

### 5.3 ADR-023 / 024 との依存関係

- ADR-023 Phase 0 で BE が **LangSmith 観測性とガードレール** を runtime で持つようになる
- ADR-024 (本書提案) で BE が **memory ownership** をさらに固める
- → BE responsibilities が増えるタイミングで FE proxy 削除を進めると、`/api/qa` / `/api/voice` の直接呼び出しが楽になる
- Vite 移行は proxy が 0 になってから判断 (bundle 92KB → 42KB の効果はあるが、kiosk 用途で SEO 不要 = SSR 不要)

参考:
- [Designrevision: Vite vs Next.js Complete Comparison (2026)](https://designrevision.com/blog/vite-vs-nextjs)
- [TECHSY: Next.js vs React + Vite 2026 — Need a Framework?](https://techsy.io/en/blog/nextjs-vs-react-vite)

→ **「極論 Vite」は方向性として正しいが、Phase 順序を ADR-021 と整合させること**。

---

## 6. 系統 E: 評価パイプライン (2026/05 ベスト・プラクティス)

### 6.1 現状 vs ベスト・プラクティス対比

| 項目 | 現状 | 2026/05 標準 |
|---|---|---|
| Online (per-turn) | 無し | LangSmith / Langfuse で 100% trace + LLM-as-Judge auto-scoring |
| RAGAS | 週 1 cron + offline | RAGAS × LangSmith 自動 trace 連携 (公式 docs) |
| memory benchmark | 無し | LoCoMo / LongMemEval (ICLR 2025) |
| critic | 無し (ADR-023 Phase 1 で導入予定) | generator → critic → revise 閉ループ |
| 観測 dashboard | 無し (DB SELECT) | LangSmith dashboard with custom critic_score columns |

参考:
- [Langfuse: LLM-as-a-Judge](https://langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge)
- [LangSmith Evaluation](https://www.langchain.com/langsmith/evaluation)
- [RAGAS × LangSmith integration](https://docs.ragas.io/en/stable/howtos/integrations/langsmith/)
- [Agent Observability 2026 ガイド](https://www.digitalapplied.com/blog/agent-observability-2026-evals-traces-cost-guide)

### 6.2 ADR-023 で計画済みの部分

ADR-023 Phase 0 (LangSmith trace 配線) + Phase 1 (critic node 決定論シグナル) + Phase 4 (LLM-as-judge) で評価層の骨格はカバーされる。

### 6.3 ADR-024 で **追加で必要** な評価要素

- **memory eval suite**: LongMemEval / LoCoMo パターンを RAGAS evaluation に追加 (temporal queries / multi-hop reasoning)
- **reception flow eval**: greeting → purpose_hearing → routing → completed の遷移率を online metric として LangSmith に push
- **regression eval for LTM write rate**: `ltm_store_write="success"` の rate を SLO 化 (例: 名前明示ターンで >=95%)

---

## 7. 提案: ADR-024 と ADR-025 を ADR-023 と並列起票

### 7.1 ADR-024 (proposed): Memory & Reception Modernization

```
ADR-024 ─── Phase A0:  observability bridging
        │              - ltm_store_write を setter で必ず set
        │              - memory_* / reception_* event family を structured_logger に追加
        │              - chat_response.route の metadata 命名規約を強制
        │              (ADR-023 Phase 0 と同 PR に同梱可能)
        │
        ├── Phase A1:  agent_memory schema 最適化
        │              - migration: GIN index on (value->>'sessionId')
        │              - SimplifiedMemoryHelper のクエリを sessionId filter SQL 側に押す
        │              - cleanup の N+1 delete を bulk delete に
        │
        ├── Phase A2:  hierarchical Store namespace 移行
        │              - ("users", visitor_id, "facts" | "episodes" | "preferences")
        │              - ("global", "config") for shared
        │              - LangGraph Store の AsyncPostgresStore に統合
        │
        ├── Phase A3:  memory_extractor / purpose_classifier の Semantic 化
        │              - regex → ADR-023 の三段カスケード router に乗せる
        │              - LLM extract (gemini-flash-lite) + semantic dedupe
        │              - LongMemEval pattern を RAGAS suite に追加
        │
        └── Phase A4:  dead reception path の決定
                       - /api/reception/respond / complete の保持 or 削除
                       - public.users テーブルの新設 or visit ベース統一
                       - autonomous reception path の整理
```

#### 期間目安・スコープ
- Phase A0: 0.5-1 日 (ADR-023 Phase 0 にバンドル推奨)
- Phase A1: 2-3 日 (migration + クエリ書き換え + tests)
- Phase A2: 1 週間 (大きい設計変更、shadow mode 必須)
- Phase A3: 1 週間 (ADR-023 router cascade と統合)
- Phase A4: 2-3 日 (決定が必要、コードは少ない)

### 7.2 ADR-025 (proposed): Frontend Proxy Deletion → Vite Migration

ADR-021 の Acceptedをそのまま **実装計画 Phase に分解**:

```
ADR-025 ─── Phase B0:  /api/qa proxy 廃止 (#358 既存タスク完遂)
        │
        ├── Phase B1:  /api/voice / /api/reception/* proxy 廃止
        │              backend に CORS + auth 配線
        │
        ├── Phase B2:  admin/knowledge proxy 廃止
        │              admin auth migration が前提
        │
        └── Phase B3:  残る proxy 棚卸し → Vite 移行可否判断
                       - SEO 不要 + SSR 不要 = Vite 移行候補
                       - bundle 92KB → 42KB の現状計測スパイク
                       - kiosk + admin で異なる構成にする選択肢検討
```

### 7.3 並行実行依存図

```
[ADR-023] Routing + Critic ←──┐
   Phase 0: LangSmith trace   │ 共通 observability 基盤 (同 PR 推奨)
                              │
[ADR-024] Memory + Reception ←┘
   Phase A0: observability bridging
   Phase A1: agent_memory index
   Phase A2: hierarchical Store
   Phase A3: semantic extractor (← ADR-023 router cascade に統合)
   Phase A4: reception dead code 整理

[ADR-021 → ADR-025] FE proxy → Vite
   Phase B0-B3: Backend ownership が固まってから順次
```

→ **Phase 0 / A0 は同じ PR に同梱**するのが最も効率的（observability の二重 PR 化を避ける）。

---

## 8. 数値ターゲット（提案）

| 指標 | Before (現在) | After (Phase A 完了時) |
|---|---|---|
| `ltm_store_write="success"` rate (名前明示ターン) | 0% (常に skipped) | ≥ 95% |
| memory loader p95 latency (`_get_recent_messages`) | 未計測 (logging 無し) | ≤ 100ms |
| `memory_*` event 種別 (structured log) | 0 | ≥ 5 種類 |
| `route="unknown"` 出現率 | 2.4% (48/2000) | ≤ 0.5% |
| `route` field が class 名のままの率 | 39% (629+137+11+6/2000) | 0% |
| `/api/reception/respond` 呼び出し率 (start に対し) | 0% | (削除 or 100%) |
| `/api/reception/start` → reception 完了率 | 24% (38/158) | ≥ 60% |
| chat_response p95 latency | 7.35s | ≤ 6s (semantic router 効果) |
| frontend `/api/*/route.ts` 数 | 28 | 0 (Phase B 完了時) |

---

## 9. 残課題 / 次セッションへの引き継ぎ

### 9.1 まず決めること
1. **ADR-024 と ADR-025 を起票するか**: 本書を ADR 候補として提案するか、Epic GitHub Issue だけで進めるか
2. **Phase A0 を ADR-023 Phase 0 と同梱するか**: 推奨は同梱（observability の同期化）
3. **Phase A4 の reception dead code**: 削除 / 残す / 統合 のどれにするか
4. **public.users テーブル**: 作るか、visits ベース統一にするか

### 9.2 PR を起票する前に
1. PR #830 (ADR-023) のマージ確認
2. ADR-023 Epic + 6 sub-issues の起票 (Phase B)
3. 本書の内容を ADR 化する場合は ADR-024 / 025 番号で起票

### 9.3 Codex CLI 経路 C 委任候補（次セッション向け）
- Phase A0: 構造化ログ event 種別の追加（量産タスク） → Codex CLI 経路 C
- Phase A1: agent_memory query 書き換え + migration → backend-developer + tdd-guide (LSP 必須)
- Phase A2: hierarchical namespace migration → backend-developer + tdd-guide
- Phase A3: semantic extractor 統合 → backend-developer + ADR-023 担当者と協調
- Phase A4: 決定後の削除 / 統合 → backend-developer 単独

---

## 10. References

### 本リポジトリ内
- [ADR-006: LangGraph workflow redesign](../adr/006-langgraph-workflow-redesign.md)
- [ADR-011: LTM cross-session design](../adr/011-ltm-cross-session-design.md)
- [ADR-012: LTM connection pool migration](../adr/012-ltm-connection-pool-migration.md)
- [ADR-014: Observability phase 1a](../adr/014-observability-phase1.md)
- [ADR-017: Observability phase 1b](../adr/017-observability-phase1b.md)
- [ADR-019: Alpha live RAGAS case accounting](../adr/019-alpha-live-ragas-case-accounting.md)
- [ADR-021: Frontend/backend separation before React/Vite migration](../adr/021-frontend-backend-separation-before-react-vite.md)
- [ADR-023: Semantic Router + LangGraph runtime self-evaluation](../adr/023-semantic-router-and-runtime-self-evaluation.md)
- [docs/plans/semantic-router-self-eval-2026-05-17.md](semantic-router-self-eval-2026-05-17.md) — ADR-023 ハンドオフ計画
- `MEMORY.md` Phase 3.6 残課題 (B-1 〜 B-4) — 本書の発見と関連

### 外部 (2026/05 時点)
**Memory architecture:**
- [Mem0: State of AI Agent Memory 2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026)
- [Letta: Benchmarking AI Agent Memory](https://www.letta.com/blog/benchmarking-ai-agent-memory)
- [Analytics Vidhya: Architecture and Orchestration of Memory Systems in AI Agents (2026/04)](https://www.analyticsvidhya.com/blog/2026/04/memory-systems-in-ai-agents/)
- [arxiv 2510.27246: Benchmarking and Enhancing Long-Term Memory in LLMs](https://arxiv.org/pdf/2510.27246)
- [arxiv 2603.29194: Multi-Layered Memory Architectures for LLM Agents](https://arxiv.org/html/2603.29194)
- [GitHub: Agent_Memory_Techniques (NirDiamant)](https://github.com/NirDiamant/Agent_Memory_Techniques)

**LangGraph memory:**
- [LangChain: Long-term memory docs](https://docs.langchain.com/oss/python/langchain/long-term-memory)
- [Five Agent Memory Types in LangGraph (dev.to)](https://dev.to/sreeni5018/five-agent-memory-types-in-langgraph-a-deep-code-walkthrough-part-2-17kb)
- [LangMem Hot Path Quickstart](https://langchain-ai.github.io/langmem/hot_path_quickstart/)

**Evaluation:**
- [LangSmith Evaluation Platform](https://www.langchain.com/langsmith/evaluation)
- [Langfuse LLM-as-a-Judge](https://langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge)
- [RAGAS × LangSmith integration](https://docs.ragas.io/en/stable/howtos/integrations/langsmith/)
- [Agent Observability 2026 ガイド](https://www.digitalapplied.com/blog/agent-observability-2026-evals-traces-cost-guide)

**Voice receptionist 2026:**
- [Sigmamind: Create Voice AI Agent 2026 — Step-by-Step Architecture](https://www.sigmamind.ai/blog/create-voice-ai-agent-step-by-step-architecture-66b0b)
- [Hamming.ai Voice Agent Testing Guide 2026](https://hamming.ai/resources/voice-agent-testing-guide)

**Frontend migration:**
- [Designrevision: Vite vs Next.js Complete Comparison (2026)](https://designrevision.com/blog/vite-vs-nextjs)
- [TECHSY: Next.js vs React + Vite 2026](https://techsy.io/en/blog/nextjs-vs-react-vite)

---

## 11. 報告者ノート

本書は **ADR ではなく調査報告書** です。次セッションで本書の内容をベースに ADR-024 / ADR-025 を起票する際は、CLAUDE.md / .claude/rules/ 規約に従い:

1. develop ベースの feat ブランチ
2. code-reviewer + Codex CLI 経路 A 両 LGTM
3. PR 1 つ = 1 意図 (ADR-024 と ADR-025 は別 PR)
4. CI green (`cd backend && ruff check . && black --check . && pytest -m "not ragas and not slow"`)
5. MEMORY.md 更新

を厳守すること。ADR-023 と並走するため、依存タイミング (特に Phase 0 / A0 の同梱判断) を最初に確認してから着手するのが安全。
