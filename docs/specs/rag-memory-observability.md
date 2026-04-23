# RAG + Memory Observability Spec (draft)

**Issue**: #513 E-6 — RAG/メモリ観測性強化
**Status**: Draft
**Date**: 2026-04-23
**Author**: Claude Code（統括）
**Related**: ADR 008 (operational guardrails), ADR 011 (LTM cross-session), ADR 012 (LTM connection pool, 予定), #532 (LTM regression incident), #508

---

## 背景

2026-04-22 夜〜04-23 朝にかけて、LTM 跨セッション recall regression (#532) が発生した。
Codex の live verify が**デプロイ直後の warm window で false positive**となり、本番で連続失敗していることが翌朝の smoke で初めて判明した。

原因の核は「**本番で壊れていることを自動検知する仕組みがない**」こと。観測性の欠如が alpha 直前 blocker の遅れにつながった。

本 spec は以下を同じパイプラインで仕組み化する:

- RAG fallback の増減（言語別）
- LTM 書込み/読出しの success rate
- Supabase connection 健全性
- Agent 応答 latency p50/p95/p99
- Hallucination 検知（EventAgent の suspicious token）

---

## 目的

1. 本番 regression を **自動で即検知**（deploy 後 10分以内、idle 15分以内）
2. 監査で**言語別 RAG 品質**を継続計測（Epic E-4 #511 RAGAS と並行）
3. Cloud Monitoring で**単一ダッシュボード**に集約
4. アラートは**PagerDuty or email**で oncall に飛ぶ

## 非目的

- 外形 E2E 監視（別枠: `.github/workflows/voice-e2e-nightly.yml` で継続）
- frontend 側 observability（Vercel Analytics で継続）
- 課金系メトリクス（将来）

---

## SLI（Service Level Indicators）

### 1. LTM Recall Success Rate

> 同一 `visitor_id` で前セッションの明示記憶が次セッションで recall できる率

- 測定: smoke script (`scripts/alpha-smoke.sh`) を 15分間隔で Cloud Scheduler から実行
- 成功条件: `answer` に記憶対象の名前トークンが含まれる
- 公開: `custom.googleapis.com/ecn/ltm_recall_success`

### 2. LTM Store/Load Success Rate

> アプリケーションからの Store/Load 呼び出しで、connection error なしに完了した率

- 測定: log-based metric（後述）
- 失敗シグナル: `the connection is closed`, `pool is closed`, `broken pipe`
- 公開: `custom.googleapis.com/ecn/ltm_store_errors`, `ecn/ltm_load_errors`

### 3. RAG Non-Fallback Rate（言語別）

> 全 `/api/chat` request のうち `sources != ['fallback']` を返した率（言語別に分離）

- 測定: `/api/chat` レスポンスで `metadata.sources` を構造化ログに記録
- 公開: `custom.googleapis.com/ecn/rag_hit_rate{lang=ja|en|zh|ko}`

### 4. Agent Response Latency（p50 / p95 / p99）

> `/api/chat`, `/api/voice` の response time 分布

- 測定: Cloud Run の request log は既に取得済 → Distribution metric 化
- 公開: 既存 `run.googleapis.com/request_latencies` の分位数抽出

### 5. EventAgent Hallucination Rate

> EventAgent 応答のうち、suspicious token（`ビジー`, `ランチ交流会` 等）を含む率

- 測定: 応答をログに記録 → keyword match で log-based metric 化
- 公開: `custom.googleapis.com/ecn/event_hallucination_rate`

---

## SLO（Service Level Objectives）

| SLI | 目標 | 測定期間 | アラート閾値 |
|---|---|---|---|
| LTM recall success | 95% | 24h rolling | 連続 3 回失敗で WARN、6 回で CRIT |
| LTM store error rate | < 1% | 15min rolling | 5% 超で WARN、10% 超で CRIT |
| LTM load error rate | < 1% | 15min rolling | 5% 超で WARN、10% 超で CRIT |
| RAG non-fallback (ja) | ≥ 85% | 24h rolling | 80% 下回りで WARN |
| RAG non-fallback (en) | ≥ 70% | 24h rolling | 60% 下回りで WARN |
| RAG non-fallback (zh/ko) | ≥ 60% | 24h rolling | 50% 下回りで WARN |
| Agent p95 latency | < 5s | 15min rolling | 7s 超で WARN |
| Agent p99 latency | < 10s | 15min rolling | 15s 超で CRIT |
| EventAgent hallucination | < 0.5% | 24h rolling | 1% 超で WARN |

---

## 実装プラン（段階導入）

### Phase 1 — Foundation（今日〜2日）

#### 1.1 構造化ログの正規化（backend/utils/logging_config.py 想定）
- 既存 `jsonPayload` 形式は維持
- 以下のフィールドを request 単位で必ず出力:
  ```json
  {
    "request_id": "...",
    "endpoint": "/api/chat",
    "language": "ja|en|zh|ko",
    "agent": "business_info|event|general_knowledge|...",
    "sources": ["enhanced_rag|fallback|web_search"],
    "latency_ms": 2841,
    "visitor_id_hash": "sha1(vid)[:10]"
  }
  ```
- 個人情報（visitor_id 生値）は出さず、ハッシュのみ。

#### 1.2 Log-Based Metrics 定義（gcloud 経由）
- `ecn_ltm_store_errors` = count of `jsonPayload.message =~ "long-term memory store failed"`
- `ecn_ltm_load_errors` = count of `jsonPayload.message =~ "Long-term memory load failed"`
- `ecn_rag_fallback` = count of `jsonPayload.sources[0] = "fallback"` labeled by `language`
- `ecn_event_halluc` = count of suspicious tokens in EventAgent responses
- `ecn_403_slow_count` = count of `httpRequest.status=403 AND httpRequest.latency>"1s"` （#488 連動）
- `ecn_403_very_slow_count` = count of `httpRequest.status=403 AND httpRequest.latency>"10s"` （#488 連動）

定義ファイル: `infra/monitoring/log-based-metrics.yaml` （新規）

#### 1.3 Alerts（Cloud Monitoring Policy）
- 各 metric に対して上記 SLO 閾値のアラートポリシーを Terraform で定義
- 通知チャネル: email + Slack（既存 channel 流用）

### Phase 2 — Dashboard（3日）

#### 2.1 Cloud Monitoring Dashboard（JSON）
- Panel 構成:
  1. LTM Health（recall success, store/load error rate, connection closed count）
  2. RAG by Language（hit rate ja/en/zh/ko の 4 グラフ重ね）
  3. Agent Latency（p50/p95/p99 by endpoint）
  4. Error Budget Remaining（SLO burn rate）
- 配置: `infra/monitoring/dashboards/rag-memory.json`

### Phase 3 — Active Probing（1週）

#### 3.1 Cloud Scheduler で alpha-smoke を定期実行
- 間隔: 15分
- 環境: API_KEY は Secret Manager から引く
- 失敗時: log-based metric `ecn_smoke_failures` を発火、アラート連動

### Phase 4 — Audit ダッシュボード（2週）

#### 4.1 週次 audit pipeline
- RAGAS スコア（Epic E-4 #511 実装後に統合）
- LTM promotion 統計（promoted candidates / day）
- hallucination 検知内訳
- Audit レポートは `docs/audit/YYYY-MM-DD-weekly.md` に書き出し

---

## Terraform / Infra 変更

現状の `infra/` 配下を再利用:

```
infra/
  monitoring/
    log-based-metrics.tf    # Phase 1.2
    alert-policies.tf        # Phase 1.3
    dashboards/
      rag-memory.json        # Phase 2.1
  scheduler/
    alpha-smoke-cron.tf      # Phase 3.1
```

権限:
- Cloud Monitoring Admin to terraform service account
- Cloud Scheduler にも既存 service account で invoke 可能にする

---

## 成功基準（Exit criteria）

| 項目 | 達成基準 |
|---|---|
| Phase 1 | `ecn_ltm_store_errors` が Cloud Monitoring で見える / alert が test fire する |
| Phase 2 | ダッシュボードで JA/EN の RAG hit rate が 1h 粒度で見える |
| Phase 3 | 15分 cron 実行で failure が log-based metric に反映される |
| Phase 4 | 週次 audit レポートが自動生成される |

---

## Open Questions

1. **alpha-smoke を Cloud Scheduler から呼ぶか、Cloud Run Job にするか**
   - Scheduler + HTTP invoke が一番軽い。Job 化は Phase 4 以降でも可。
2. **log-based metric のカーディナリティ上限**
   - `language` ラベルだけなら 4 値で問題なし。visitor_id_hash は metric label にしない（cardinality 爆発防止）。
3. **既存 `/api/monitoring/dashboard` endpoint との棲み分け**
   - 既存は backend 内部の debug 用。本 spec は GCP 外形観測。用途重複なし、両立可能。
4. **Epic E-4 #511 RAGAS との統合タイミング**
   - Phase 4 で統合。RAGAS は 127 件 batch 評価 → metric 化、本 spec は live probe 系。

---

## References

- Issue #513（E-6 観測性 Epic）
- Issue #532（LTM regression RCA）
- Issue #488（`/api/character` 403 cold start、類似 observability ギャップ）
- ADR 008 Operational Guardrails
- ADR 011 LTM Cross-Session Design
- `scripts/alpha-smoke.sh`（本日 Claude が追加）
- Google SRE Book: "Service Level Objectives" 章

---

## Changelog

- 2026-04-23: initial draft (Claude Code 統括), Phase 1–4 スケルトン、#513 spec draft 完了
