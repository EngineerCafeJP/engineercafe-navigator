# ADR 017: Observability Phase 1b — Terraform Metrics, Dashboard, and Alerts

## ステータス

採用

## 日付

2026-04-25

## 背景

ADR 014 で `/api/chat` の `chat_response` structured log を追加し、ADR 016 で
`stt_*` structured log を追加した。Phase 1b では、この runtime log schema を Cloud
Monitoring の log-based metric、dashboard、alert policy に固定する。

Issue #513 の目的は、alpha 運用中に STT latency、chat response latency、RAG fallback、
memory helper error を早く検知できる状態にすることである。backend behavior の追加変更は
Phase 1b の対象外とし、既存ログから観測できる範囲を Terraform 管理する。

## 決定

Phase 1b の observability resource は Terraform で管理する。

- Log-based metrics: `chat_response`, `stt_*`, memory helper error, fallback count/rate
- Dashboard: STT latency、chat response latency、memory errors、fallback rate を 1 画面で確認
- Alert policies: latency threshold、memory error count、fallback rate、SLO burn-rate

Terraform は review 可能な IaC として repository に入れるが、`terraform apply` は merge 後に
operator が手動実行する。PR merge と同時に本番 Monitoring resource を変更しないことで、
notification channel、project ID、state、IAM の誤設定を人間が最終確認できるようにする。

## 現在のログ前提

Phase 1b は次の既存ログだけを信頼する。

- STT: `jsonPayload.event` が `stt_*` の structured log
- Chat: `jsonPayload.event="chat_response"` の structured log
- Memory: 現時点で `memory_*` structured event は存在しない

`backend/**` は本 issue の範囲外であるため、memory 専用 event は追加しない。memory helper の
error は、既存の root structured log から `logger="backend.utils.memory_helper"` かつ
`level="ERROR"` で監視する。

## Alert Thresholds

Latency alert は user-facing degradation を早く拾うが、一時的な cold start や少数 request で
noise になりやすい。このため、単発 request ではなく rolling window の p95 / rate で判定する。

| Signal | Warning | Critical | 理由 |
| --- | ---: | ---: | --- |
| STT p95 latency | dashboard watch | > 6s over 15m | ADR 016 の Phase B-1 期待値は約 3.1s。6s は baseline の約 2 倍で、Qwen timeout / Vosk fallback / cold path を疑う。 |
| Chat p95 latency | dashboard watch | > 10s over 15m | alpha kiosk で対話が途切れる上限として 10s を採用し、short spike は 15m 継続で抑制する。 |
| Memory helper errors | dashboard watch | > 0 over 15m | memory write/load は volume が低くても recall regression に直結するため、絶対数で検知する。 |
| Fallback burn rate | 1h > 14.4x only | 1h > 14.4x and 6h > 6x | 98% SLO の 2% error budget に対して 28.8% / 12% bad-event ratio。急激な悪化と sustained degradation を分ける。 |
| STT failure burn rate | 1h > 14.4x only | 1h > 14.4x and 6h > 6x | `stt_winner="none"` を bad event とし、98% STT availability SLO の error budget 消費として扱う。 |

SLO burn-rate alert は multi-window で定義する。1h window は急激な regression を早く検知し、
6h window は短い spike や deploy 直後の warm-up noise を抑制する。両方の window が同時に
閾値を超えた場合に page / high severity とし、1h のみ超過は warning とする。

推奨する初期値:

- Chat quality SLO: chat requests の 98% が non-fallback
- STT availability SLO: STT winner events の 98% が `none` 以外
- Latency guardrail: STT p95 6s、chat p95 10s
- Memory guardrail: memory helper ERROR log が 15m で 0 件
- Burn-rate: 1h が 14.4x 以上、かつ 6h が 6x 以上で critical

## 採用理由

Terraform 管理により、Console で手作業作成した metric や alert が drift することを避けられる。
dashboard と alert policy を同じ review 単位にすることで、operator は「どの metric がどの
panel と alert に使われるか」を PR 上で確認できる。

一方で apply は manual after merge とする。Monitoring resource は即時に通知や incident を
発生させるため、merge gate だけで本番へ反映するより、merge 後に `terraform plan` を確認して
から operator が apply する方が alpha 運用では安全である。

## 代替案

### Console で手動管理する

早いが、query、threshold、notification channel が属人化し、Phase 1a の後続として残すには
drift risk が高い。Issue #513 では不採用。

### Backend に memory structured event を追加する

`memory_store_failed` などの event があれば metric は作りやすい。ただし Phase 1b の ownership
は observability IaC と docs であり、`backend/**` は out of scope。今回は既存 root structured
log の `logger=backend.utils.memory_helper` と `level=ERROR` を使う。

### SLO burn-rate を 1 window のみにする

実装は単純だが、short spike で false positive になりやすい。1h + 6h の multi-window により、
早い検知と noise 抑制を両立する。

## 互換性

- Backend API schema と runtime behavior は変更しない。
- 既存 structured log schema を前提にする。
- Terraform apply までは GCP Monitoring resource は変更されない。

## Phase 1b pre-apply fix (#564)

Terraform apply 前の安全対策として、memory helper error metric の `message` label は採用しない。
`backend.utils.memory_helper` の ERROR log は `"Error storing message: %s"` など例外内容を含む
free-form message であり、Supabase/PostgREST の response、session/key、接続エラー詳細などが
混入すると log-based metric label の cardinality が無制限に増える。alert と dashboard では
message 別内訳よりも 15m error count の検知を優先する。

また、alert policy と dashboard の Monitoring filter は
`google_logging_metric.*.name` から組み立てた metric type を使う。これにより初回 apply 時に
log-based metric descriptor が alert/dashboard より先に作成される Terraform graph になるため、
静的文字列だけで参照した場合の descriptor 作成順序リスクを避ける。

## ロールバック

問題が出た場合は、該当 alert policy の notification を停止するか、Terraform で対象 resource
を戻して手動 apply する。backend deploy の rollback は不要。

## 検証方針

- `terraform fmt -check`
- `terraform validate`
- `terraform plan` で log metric、dashboard、alert policy の差分を確認
- Merge 後、operator が手動で `terraform apply` を実行
- Apply 後、Cloud Logging query と Cloud Monitoring dashboard で metric ingestion を確認
