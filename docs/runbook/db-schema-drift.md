# DB Schema Drift Runbook

Audience: backend developers and release owners.

## What the check does

The `DB Schema Drift Check` workflow runs daily at 12:00 UTC / 21:00 JST and on pull requests that change `backend/supabase/migrations/**`. It installs the Supabase CLI, links the project with GitHub Actions secrets, and runs:

```bash
./scripts/check-db-schema-drift.sh
```

The script compares local migrations with the linked Supabase project using `supabase db diff --linked --schema public`. It prints the diff and exits 1 when drift is found. It exits 2 when required secrets or tooling are missing.

## Drift response

1. Read the workflow log and identify the table, column, policy, index, or function that differs.
2. Decide whether production is ahead of migrations or the migration history is missing a reviewed change.
3. Add a reviewed migration file under `backend/supabase/migrations/`, test it against a safe environment, and rerun the workflow.

Do not resolve drift by changing production directly during alpha unless the release owner approves an incident workaround.

## Creating a manual migration

Create a migration file with a UTC timestamp and descriptive name:

```bash
timestamp="$(date -u +%Y%m%d%H%M%S)"
migration="backend/supabase/migrations/${timestamp}_describe_change.sql"
: > "${migration}"
${EDITOR:-vi} "${migration}"
```

Edit the SQL so it is idempotent where practical, includes any needed indexes or RLS policy changes, and can be reviewed without relying on dashboard context.

## Production synchronization

After the migration is reviewed and merged, apply it through the normal release process for the Supabase project. Then rerun `DB Schema Drift Check` with `workflow_dispatch`. The workflow must show no schema changes before a Cloud Run or Vercel deploy that depends on the schema.

## Emergency dashboard change template

Use this commit message body when a dashboard change was unavoidable and needs to be captured afterward:

```text
Capture emergency Supabase schema change

Reason:
Production timestamp:
Operator:
Affected objects:
Verification:
Follow-up issue:
```

Open the follow-up PR before the next alpha verification window and include the workflow log proving drift is resolved.
