# ADR 014: Observability Phase 1a

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

Phase 1a では `/api/chat` の成功レスポンスで以下の structured log を出力し、Cloud
Logging の log-based metrics と Cloud Monitoring alert policies を Terraform で管理する。

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

Terraform state は GCS backend
`gs://aipartner-426616-tfstate/engineer-cafe-backend/observability` を使う。bucket 自体は
bootstrap 手順として手動作成し、今回の Terraform 管理対象には含めない。

## 採用理由

log-based metrics は既存の Cloud Run stdout/stderr ログから作成できるため、backend の
runtime や deployment manifest に追加の環境変数を要求しない。Phase 1a の目的は「alpha
運用に必要な最低限の観測性を短く入れる」ことであり、構造化ログと Terraform 管理の alert
policy が最も小さい変更で要件を満たす。

Terraform を今回から導入することで、metric と alert の設定を PR review 可能なコードに
固定できる。console 手作業だけで作ると、後続の dashboard/SLO 設計で差分追跡が難しくなる。

## 代替案

### 代替案 A: OpenTelemetry を導入する

trace、metric、log を統合でき、将来的な分散トレーシングには有利である。一方で collector、
exporter、sampling、resource attribute 設計が必要になり、Phase 1a の「今日 alpha で見る」
目的に対して導入面積が大きい。今回は不採用とし、Phase 2 以降の候補に残す。

### 代替案 B: Cloud Monitoring console で手動作成する

最速で作れるが、review できず、環境再作成や rollback が難しい。今回から Terraform で管理する
ため不採用。

### 代替案 C: Dashboard まで同じ PR で作る

可視化まで一気通貫になるが、metric/log schema と alert の妥当性が固まる前に dashboard JSON を
固定することになる。Phase 1a では structured log、metrics、alerts に絞り、dashboard は
Phase 1b に分割する。

## Phase 1a / 1b 分割

Phase 1a は本番事故や品質劣化を検知する最低限の signal を作る。具体的には log schema、
log-based metrics、alert policies、notification channel、Terraform CI までを含める。

Phase 1b は dashboard、SLO 表示、運用レビュー用の可視化を扱う。Phase 1a の metric 名と
label が本番ログで安定することを確認してから dashboard を作る方が、後戻りが少ない。

## 互換性

- Cloud Run service に新しい環境変数は不要。
- `/api/chat` response schema は変更しない。
- structured log は stdout の追加ログであり、既存 API 挙動には影響しない。
- Terraform apply はこの PR では実施せず、承認後に手動で行う。

## ロールバック

問題が出た場合は、backend 側の structured log 呼び出しを revert すればアプリ挙動は元に戻る。
Terraform resources は `terraform destroy` ではなく、必要な metric/policy を個別に無効化または
削除する。alert の誤検知だけであれば `enabled = false` への変更 PR で止められる。

## 検証方針

- Unit/API: `/api/chat` が `chat_response` structured log を出すこと。
- Local: `ruff check .`、`black --check .`、`pytest -m "not ragas and not slow" -q`。
- Terraform: `terraform init`、`terraform validate`、`terraform plan`。
- Production: merge 後、terisuke 承認のうえ手動 apply し、Cloud Logging に sample log が
  到達して metric が増えることを確認する。

