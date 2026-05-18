# ADR-027: Wave 3 — Observability & Refactor Foundation (Pre Phase 2)

## Status

Proposed (2026-05-18) — Wave 2 (ADR-026) 完了直後、Phase 2 (Semantic Router 三段カスケード) 着手前の foundation hardening として起草。

## Context

### 2026-05-18 監査で判明した運用面の課題

Wave 2 完了直後 (PR #852/#873/#874/#875/#876 merged) に独立検証を実施した結果、以下が明らかになった:

#### 1. Observability gap (運用上致命的)

| 項目 | 実測値 |
|------|--------|
| Cloud Monitoring alert policies | **0** |
| Cloud Monitoring notification channels | **0** |
| Cloud Logging log-based metrics | **0** |
| Dashboard | なし (raw log のみ) |

→ **「定期的にログを見るだけで会話が期待通りか、音声 I/O が期待速度か、正しい agent にルーティングしているか」が判断できない**。
→ 「一定の閾値を超えた agent の動きの問題」を **検知する仕組みが完全に欠落**。

#### 2. STT/TTS event call site 不完全

`backend/observability/structured_logger.py` には以下の event が定義されているが、live log で出現していないものがある:

| Event | 定義 | live 出現 |
|-------|------|---------|
| `chat_response` | ✅ | ✅ (22 件 / 24h) |
| `memory_store_message` | ✅ | ✅ (44 件) |
| `ltm_promote` | ✅ | ✅ (44 件) |
| `stt_qwen_complete` | ✅ | ❌ (0 件 — call site 不在 / レベル抑制) |
| `stt_winner` | ✅ | ❌ |
| `tts_cache` | ✅ | ❌ |
| `agent_routing` | ❌ **未定義** | ❌ |
| `voice_round_trip` | ❌ **未定義** | ❌ |

→ STT/TTS と agent routing の構造化ログが **設計はあるが運用に乗っていない**。

#### 3. Frontend audio telemetry 未連携

Wave 2 で FU-17 として追加された `useVoiceSessionController.ts:73` の `console.debug` は **ブラウザ console にしか出ない**:

```ts
console.debug(`[VoiceSessionController] ${message}`, details);
```

Datadog / Sentry / Backend telemetry endpoint への送信は未配線。
→ watchdog 発火率、fallback 発火率、user-interaction-gate timeout 率を **Backend からは見えない**。

#### 4. Backend / Frontend に大ファイルが多数残存

ルール: `ファイル 800 行未満` (`~/.claude/rules/coding-style.md`)

**Backend** (17 ファイル超過):
- 3,033 行: `backend/agents/stt_agent.py`
- 2,588 行: `backend/workflows/main_workflow.py`
- 2,071 行: `backend/agents/facility_agent.py`
- 1,984 行: `backend/main.py`
- 1,731 行: `backend/tools/enhanced_rag.py`
- 1,635 行: `backend/agents/business_info_agent.py`
- 1,610 行: `backend/agents/voice_agent.py`
- … 計 17 ファイル

**Frontend** (6 ファイル超過):
- 1,959 行: `frontend/src/app/components/VoiceInterface.tsx`
- 1,555 行: `frontend/src/app/components/CharacterAvatar.tsx`
- 1,304 行: `frontend/src/app/components/ReceptionPdfGuide.tsx`
- 962 行: `frontend/src/lib/vrm-utils.ts`
- 840 行: `frontend/src/app/page.tsx`
- 824 行: `frontend/src/lib/voice-recorder.ts`

#### 5. docs/plans に 21 件の plan が累積、archive ルール無し

ステータス (completed / superseded / active) の表示なし。古いものと新しいものの区別がつかず、新規メンバーが古い計画を SoT と誤認するリスク。

#### 6. ルートドキュメントが Wave 2 後の状態に追随していない

- `docs/STT-Implementation-Trace.md`: 2026-04-12 最終更新 (Wave 2 で日付処理周辺の prompt 変更があったが反映なし)
- `docs/observability-runbook.md`: Issue #513 ベース、Wave 2 の event 整備や次の Cloud Monitoring alert に未対応

## Decision

Wave 3 を **2 テーマ並列** で実施する:

### Theme A: Observability & Alerting (FU-21〜25)

定期的にログを見れば運用状態が分かり、閾値を超えれば自動で `company@cor-jp.com` に alert が飛ぶ体制を整備する。

#### D1: Backend 構造化ログの call site を完成させる
- `STT_LOGGER_NAME` で `stt_qwen_complete` / `stt_qwen_hedge_start` / `stt_vosk_complete` / `stt_winner` を **全 STT 呼び出しパス** で発火
- `TTS_LOGGER_NAME` で `tts_synthesis_start` / `tts_synthesis_complete` / `tts_cache_hit` / `tts_cache_miss` を発火
- 既存 `chat_response` event に `agent_route` / `intent` / `confidence` を必須 field として追加
- 新規 `agent_routing` event を OrchestratorAgent の全 routing 決定で発火 (routed_to, reason, confidence)
- 新規 `voice_round_trip` event を `/api/voice` のフル round-trip で発火 (stt_ms, chat_ms, tts_ms, total_ms)

#### D2: Frontend telemetry を Backend に送信
- `useVoiceSessionController.ts:73` の `console.debug` を **並列で** `/api/telemetry/voice` に POST
- 送信 event: `voice_state_transition`, `thinking_watchdog_expire`, `fallback_tts_triggered`, `user_interaction_gate_timeout`, `audio_playback_failed`
- Backend が受信 → 既存 `structured_logger` 経由で Cloud Logging に書き出し → Cloud Logging metric にも乗る

#### D3: Cloud Logging log-based metrics
以下を Cloud Logging のカスタムメトリクスとして登録 (gcloud / Terraform):

| Metric 名 | 説明 | type |
|----------|------|------|
| `voice_round_trip_latency_ms` | `/api/voice` round-trip 全 quantile | distribution |
| `chat_response_latency_ms` | chat_response.latency_ms quantile | distribution |
| `stt_latency_ms` | stt_qwen_complete.latency_ms quantile | distribution |
| `tts_latency_ms` | tts_synthesis_complete.latency_ms quantile | distribution |
| `agent_route_distribution` | agent_routing.routed_to value count | counter |
| `stt_winner_ratio` | stt_winner.provider value count (qwen vs vosk) | counter |
| `error_rate_5m` | severity>=ERROR 件数 / 5min | counter |
| `frontend_audio_watchdog_rate` | thinking_watchdog_expire 件数 | counter |
| `frontend_fallback_rate` | fallback_tts_triggered 件数 | counter |

#### D4: Cloud Monitoring alert policies + 通知
- Notification channel: **`company@cor-jp.com` (Email)** を新規作成
- Alert policy (初期は **WARN しきい値**で過剰アラートを避ける):

| Alert 名 | 条件 | しきい値 | severity |
|---------|------|---------|---------|
| `voice-round-trip-p95-slow` | voice_round_trip_latency_ms p95 > 8s for 10 min | warn | P2 |
| `chat-response-p95-slow` | chat_response_latency_ms p95 > 6s for 10 min | warn | P2 |
| `stt-latency-degradation` | stt_latency_ms p95 > 5s for 15 min | warn | P2 |
| `backend-error-burst` | error_rate_5m > 20 (件 / 5min) for 10 min | error | P1 |
| `agent-routing-skew` | agent_route_distribution `fallback_general` ratio > 30% for 30 min | warn | P3 |
| `frontend-audio-watchdog-spike` | frontend_audio_watchdog_rate > 10 (件 / 15min) | warn | P2 |
| `cloud-run-traffic-zero` | Cloud Run request count = 0 for 30 min (営業時間 12-20 JST) | info | P3 |

→ alert は `company@cor-jp.com` に email、subject prefix `[Engineer Cafe Navigator]`、本文に Cloud Logging 直リンク。

#### D5: Cloud Monitoring dashboard
- 単一 dashboard `Engineer Cafe Navigator — Production` を新設
- パネル: latency p50/p95 (voice/chat/stt/tts), error rate, agent route distribution, traffic count
- terraform/cloud-monitoring/ 配下に IaC 化 (review/plan/apply 手動)

### Theme B: Refactoring & Documentation (FU-26〜30)

Wave 2 で大量追加したコード・ドキュメントを Phase 2 着手前に整理する。

#### D6: Dead code 削除
- Frontend: `npx knip` + `npx ts-prune` 実行 → unused export を削除
- Backend: `ruff check --select F401,F811` + `vulture backend/ --min-confidence=80` → unused import / dead function 削除
- 検出 → 削除 → unit test 全 PASS が条件

#### D7: Backend 大ファイル分割 (最優先 top 6)

| 対象 | 現行行数 | 分割方針 |
|------|---------|---------|
| `backend/agents/stt_agent.py` | 3,033 | Qwen / Vosk / hedge / postprocess を別 module に分離 |
| `backend/workflows/main_workflow.py` | 2,588 | subgraph 別 + helper 関数を分離 |
| `backend/agents/facility_agent.py` | 2,071 | facility category 別 (hall / reception / wifi / amenity) に分離 |
| `backend/main.py` | 1,984 | route 別 module (api/voice / api/chat / api/calendar / api/admin) に分離 |
| `backend/tools/enhanced_rag.py` | 1,731 | RAG pipeline stage (retrieve / rerank / filter / format) ごとに分離 |
| `backend/agents/business_info_agent.py` | 1,635 | category 別 (saino_cafe / hours / pricing) に分離 |

各分割: 既存テスト全 PASS + behaviorally equivalent (= 出力 1:1 一致) が必須。

#### D8: Frontend 大ファイル分割

| 対象 | 現行行数 | 分割方針 |
|------|---------|---------|
| `frontend/src/app/components/VoiceInterface.tsx` | 1,959 | hooks 抽出 (use*) + sub-component (PlaybackController, FallbackUI 等) に分離 |
| `frontend/src/app/components/CharacterAvatar.tsx` | 1,555 | VRM lifecycle / 表情 / lipsync を hooks に分離 |
| `frontend/src/app/components/ReceptionPdfGuide.tsx` | 1,304 | PDF render / navigation / UI を分離 |

#### D9: docs/plans archive 整理 + ルートドキュメント更新
- `docs/plans/archive/` を新設、completed / superseded plan を移動
- 各 plan に冒頭 `> Status: completed (YYYY-MM-DD) / superseded by ...` を明記
- `docs/STT-Implementation-Trace.md` を Wave 2 後の状態に最新化 (TZ=Asia/Tokyo + date-only fast path 追記)
- `docs/observability-runbook.md` に Wave 3 で追加した metric / alert を追記
- `docs/CODEMAPS/` を新設、`/update-codemaps` skill で `backend.md`, `frontend.md`, `architecture.md` を自動生成

#### D10: 4-point data flow audit
CLAUDE.md ルール「endpoint 修正時、client → API route → backend → response の 4 点一致を確認」を Wave 2 で変更された全エンドポイントに対して実施:

- `/api/voice/*` (frontend → /api/voice → backend → response)
- `/api/chat` (同上)
- `/api/calendar` (同上)
- `/api/reception/*` (Wave 7 で導入の subgraph)
- (NEW) GAS Web App → `EVENT_SHEET_GAS_URL` → `SheetsEventSource` → KB

各 endpoint について audit report markdown (1 ページ / endpoint) を `docs/data-flow/` 配下に保存。

## Consequences

### Positive
- 運用が「raw log 目視」から「dashboard + alert」に進化
- Wave 2 で導入した audio reliability が **数値で計測可能**になる
- 大ファイルが分割され Phase 2 (Semantic Router) の差分が読みやすくなる
- 古い plan が archive されることで新規メンバーの混乱が減る

### Negative
- alert policy が過敏すぎると alert fatigue → 初期は warn しきい値、運用 1 ヶ月で再調整
- 大ファイル分割は import path 変更が広範に発生 → CI で全 unit/integration test 必須
- terraform/cloud-monitoring/ を導入する場合、Cloud Build 経由の plan/apply フローを整備する必要

### Out of Scope (Wave 3 では実装しない)
- Phase 2 Semantic Router cascade (ADR-023)
- Memory hierarchy 再設計 (ADR-024)
- 新規エージェント追加
- VRM / animation の本格リファクタ (D8 の component 分割のみ)

## Follow-up

- **Wave 3 完了後**: 1 週間運用ログ蓄積 → alert しきい値再調整 → Wave 4 (Phase 2 着手判断)
- iPad kiosk 実機での audio reliability proof (ADR-026 Follow-up 継続)
- BigQuery export sink を Wave 4 で検討 (ad-hoc 分析用)

## Approvals

- Proposed: Claude (2026-05-18) — Wave 2 後の独立検証を踏まえた Wave 3 設計
- 承認待ち: Terada Kousuke (terisuke)

## References

- [ADR-026 Wave 2 Kiosk UX Reliability Baseline](./026-wave2-kiosk-ux-reliability-baseline.md)
- [ADR-024 Memory & Reception Modernization](./024-memory-and-reception-modernization.md)
- [ADR-023 Routing Modernization (Semantic Router)](./023-routing-modernization.md)
- `backend/observability/structured_logger.py` (既存 logger 基盤)
- `docs/observability-runbook.md` (Issue #513 ベース、Wave 3 で拡張)
- [Wave 3 Handoff Doc](../plans/wave3-observability-refactor-handoff-2026-05-18.md)
