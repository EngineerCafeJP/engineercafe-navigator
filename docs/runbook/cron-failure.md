# Cron Failure Runbook

Audience: alpha operators and release owners.

## How alerts are detected

The Vercel cron route `/api/cron/update-knowledge-base` runs daily at 02:00 UTC / 11:00 JST. When the update throws, the route records failure metrics and calls `dispatchCronAlert()`.

If `CRON_SLACK_WEBHOOK_URL` is set in Vercel, Slack receives a message like:

```text
Cron failure: /api/cron/update-knowledge-base (Supabase request timed out)
Cron: /api/cron/update-knowledge-base
Duration: 1234ms
Metrics tracked: yes
Deployment: https://<vercel-deployment>
```

If the webhook is unset or Slack delivery fails, Vercel runtime logs still contain `[CRON_ALERT]`. During alpha, check the Slack alert channel or Vercel cron runtime logs every business day so failures are detected within 24 hours.

## First response

1. Open the Vercel project logs for the latest `/api/cron/update-knowledge-base` invocation.
2. Confirm whether the failure happened before or after `ragMetrics.trackKnowledgeBaseOperation()`.
3. Check Supabase project health and recent deployment changes.
4. Post the failure summary, timestamp, and suspected owner in the alpha operations channel.

## Manual rerun

Use the production cron secret and call the route directly:

```bash
curl -i \
  -H "Authorization: Bearer ${CRON_SECRET}" \
  "https://<vercel-domain>/api/cron/update-knowledge-base"
```

Expected success response:

```json
{
  "success": true,
  "message": "Knowledge base update completed"
}
```

## Recurrence prevention

Keep `CRON_SLACK_WEBHOOK_URL` set for production and preview environments used in alpha. After any cron failure, add the root cause and fix link to the alpha verification notes. If the same failure repeats twice in 7 days, open a P1 issue and assign an owner before the next onsite verification window.

## Escalation

Escalate immediately when the cron has failed for 24 hours, the knowledge base import is stale before onsite verification, or the alert path itself stops posting to Slack. The release owner decides whether to pause alpha validation until a manual rerun succeeds.
