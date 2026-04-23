# Engineer Cafe backend observability Terraform

Issue #513 Phase 1a では Cloud Logging の structured log から log-based metrics と
Cloud Monitoring alert policies を作成する。今回は `terraform plan` までを実施し、
`apply` は PR merge 後に terisuke の承認を受けて手動で行う。

## 前提

- Google Cloud project: `aipartner-426616`
- Terraform: `>= 1.6`
- gcloud CLI で対象 project に認証済みであること
- Terraform state 用 GCS bucket は Terraform 管理外で先に作成すること

```bash
gcloud auth login
gcloud config set project aipartner-426616
gsutil mb -p aipartner-426616 -l asia-northeast1 gs://aipartner-426616-tfstate
gsutil versioning set on gs://aipartner-426616-tfstate
```

bucket が既に存在する場合、`gsutil mb` は不要。state prefix は
`engineer-cafe-backend/observability` を使う。

## plan

```bash
cd infra/terraform
terraform init
terraform fmt -check -recursive
terraform validate
terraform plan \
  -var='project_id=aipartner-426616' \
  -var='region=asia-northeast1' \
  -var='cloud_run_service_name=engineer-cafe-backend'
```

`alert_email` の default は `terisuke1115@gmail.com`。prod 運用で別宛先にする場合は
`prod.tfvars` などで override する。

```hcl
alert_email = "alerts@example.com"
```

## apply

この PR では apply しない。merge 後、terisuke の承認を受けてから以下を手動実行する。

```bash
cd infra/terraform
terraform init
terraform plan -var-file=prod.tfvars -out=tfplan
terraform apply tfplan
```

GitHub Actions には `workflow_dispatch` の apply job も用意しているが、prod environment
approval を通した手動実行専用とする。

## 作成リソース

- log-based metrics
  - `rag_fallback_rate`
  - `ltm_store_success_rate`
  - `ltm_cross_session_recall_rate`
  - `event_agent_calendar_hit_rate`
  - `hallucination_flag_count`
- supporting distribution metric
  - `chat_response_latency_ms` (`/api/chat` p95 latency alert 用)
- alert policies
  - 5xx error rate > 5% / 5 min
  - `/api/chat` p95 latency > 10s / 10 min
  - LTM store success rate < 95% / 10 min
  - hallucination flag count > 5 / 10 min
- notification channel
  - email

