# ADR 014: RAG/Memory Observability — Phase 1a: Structured Logging

## ステータス

採用

## 日付

2026-04-24

## 背景

Engineer Cafe Navigator backend は Cloud Run 上で alpha 運用に入っているが、RAG、
長期記憶、EventAgent、hallucination flag が本番で期待通り機能しているかを定量的に
確認する仕組みが不足していた。

既存の health check や 5xx 監視だけでは、サービスが応答していても回答品質が落ちている
状態を検知できない。alpha では、RAG fallback の増加、LTM 書き込み失敗、cross-session
recall の低下、EventAgent の calendar hit 低下、hallucination flag の急増を早く見つける
必要がある。

## 決定

Phase 1a では `/api/chat` の成功レスポンスで以下の structured JSON log を stdout に
出力する。Cloud Logging では `jsonPayload.event="chat_response"` で絞り込み、log-based
metric と alert policy は GCP Console 上で必要なものから順に手動定義する。

```json
{
  "event": "chat_response",
  "request_id": "req-...",
  "language": "ja",
  "route": "business_info",
  "sources": ["enhanced_rag"],
  "rag_fallback": false,
  "hallucination_flag": false,
  "ltm_store_write": "skipped",
  "latency_ms": 1234
}
```

ヘルパーは `backend/observability/structured_logger.py` に集約し、フィールド追加は
同ファイルを経由する。`/api/chat` の既存挙動 (response schema、latency、error handling)
は変更しない。

## 採用理由

structured log は Cloud Run の既存 stdout/stderr ログから拾えるため、backend の runtime
や deployment manifest に追加の環境変数を要求しない。Phase 1a の目的は「alpha 運用に
必要な最低限の観測性を短く入れる」ことであり、log schema を先に固定すれば、log-based
metric や alert policy は後から追加しても schema を再設計しなくて済む。

log-based metric・alert policy・dashboard の IaC 化 (Terraform など) は Phase 1b に
分離する。現時点では Dev と Proto で GCP organization が異なり、特定 organization 前提
で WIF / state bucket / project ID をコード化しても、organization 統合時に書き直しが
発生するためである。Phase 1a で log schema だけ先に本番投入し、metric/alert は Console
上で必要最小限を先行整備する方が、手戻りが小さい。

## 代替案

### 代替案 A: OpenTelemetry を導入する

trace、metric、log を統合でき、将来的な分散トレーシングには有利である。一方で collector、
exporter、sampling、resource attribute 設計が必要になり、Phase 1a の「今日 alpha で見る」
目的に対して導入面積が大きい。今回は不採用とし、Phase 2 以降の候補に残す。

### 代替案 B: Terraform で metric/alert を今回同時に IaC 化する

Review 可能なコードに固定できる利点があるが、Dev/Proto の GCP organization が別で、
WIF と state bucket の置き場所が将来変わる可能性がある。今 IaC 化しても organization
統合時に書き直しが必要になるため、Phase 1b に送る。

### 代替案 C: Dashboard まで同じ PR で作る

可視化まで一気通貫になるが、metric/log schema と alert の妥当性が固まる前に dashboard JSON を
固定することになる。Phase 1a では structured log のみに絞り、dashboard は Phase 1b に
分割する。

## Phase 1a / 1b 分割

**Phase 1a (本 PR のスコープ)**

- `backend/observability/structured_logger.py` ヘルパー
- `/api/chat` で `chat_response` structured log を emit
- log schema に対する unit/API テスト
- 本 ADR

**Phase 1b (別 PR / 別 Issue)**

- log-based metrics の IaC (Terraform か gcloud CLI、organization 方針確定後)
- alert policy (5xx rate、p95 latency、`ltm_store_write="success"` 割合、
  `hallucination_flag=true` の count、`rag_fallback=true` の count)
- notification channel
- Grafana または Looker Studio dashboard
- SLO burn-rate alert

Phase 1a の log が本番で安定してフィールドを出していることを確認してから、
Phase 1b で metric と alert を組む方が schema の後戻りが少ない。

## 互換性

- Cloud Run service に新しい環境変数は不要。
- `/api/chat` response schema は変更しない。
- structured log は stdout の追加ログであり、既存 API 挙動には影響しない。
- Cloud Logging の query (`jsonPayload.event="chat_response"`) は schema が固定されれば
  そのまま Phase 1b の metric 定義にも使える。

## ロールバック

問題が出た場合は、`/api/chat` の structured log 呼び出し (backend/main.py) を revert すれば
アプリ挙動は元に戻る。log helper 単体 (`backend/observability/structured_logger.py`) は
import されない限り副作用がない。

## 検証方針

- Unit/API: `/api/chat` が `chat_response` structured log を出し、必要フィールド
  (`event`, `request_id`, `language`, `route`, `sources`, `rag_fallback`,
  `hallucination_flag`, `ltm_store_write`, `latency_ms`) が揃うこと。
- Local: `ruff check .`、`black --check .`、`pytest -m "not ragas and not slow" -q`。
- Production: merge 後、Cloud Logging で
  `resource.type="cloud_run_revision" AND jsonPayload.event="chat_response"`
  が期待通り流れてくることを確認し、Phase 1b で log-based metric を定義する前提を整える。
