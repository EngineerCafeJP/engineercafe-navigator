# ADR 009: Slow 403 responses during Cloud Run cold-start and model-load windows

Date: 2026-04-22 (Proposed) / 2026-04-23 (Accepted)

## Status

Accepted — #532 観測性 spec (docs/specs/rag-memory-observability.md) と連動して追跡する。
実装の残タスクは #488 のコメント欄のチェックリストで管理する。

## Context

Issue #488 tracks cases where `POST /api/character` returned `403` but the Cloud Run
request latency was 31-35 seconds. A `403` from API-key validation should normally be
near-immediate, so the initial concern was that auth checking might be performing slow
work or waiting on upstream dependencies.

This investigation was limited to logs and documentation. No backend runtime code was
changed because `backend/api/*` is being edited in another session and
`backend/utils/store.py` / `backend/workflows/main_workflow.py` are reserved for the
#487 track.

## Findings

### Current Cloud Run shape

The current service revision at investigation time was:

- Service: `engineer-cafe-backend`
- Region: `asia-northeast1`
- Revision: `engineer-cafe-backend-00087-sc5`
- Image: `.../engineer-cafe-backend:62fd572d0b1811fce256b7e950f53a843a63b074`
- Traffic: 100% to latest revision
- `autoscaling.knative.dev/minScale`: `1`
- `autoscaling.knative.dev/maxScale`: `3`
- `containerConcurrency`: `160`
- CPU / memory: `2 CPU`, `8Gi`
- Startup probe: TCP on port 8000, `timeoutSeconds=240`, `periodSeconds=240`

`minScale=1` reduces idle cold starts, but it does not eliminate slow windows during
deployment rollout, traffic shifting, or new instance initialization.

### Auth implementation is not doing slow work

`backend/main.py` loads the API secret once at module import:

```python
_raw_api_key = os.getenv("API_SECRET_KEY", "").strip()
_API_SECRET_KEY = _raw_api_key if _raw_api_key else None
```

`verify_api_key()` then reads `X-API-Key` or `Authorization: Bearer ...` and compares it
with `hmac.compare_digest`. It does not call Supabase, OpenRouter, model code, or Secret
Manager per request.

Protected endpoints, including `/api/character`, use `Depends(verify_api_key)`, so a bad
or missing key should be rejected before the route handler constructs
`CharacterControlAgent`.

### 2026-04-19 slow 403 pattern

The original incident window was confirmed in Cloud Run logs:

| Timestamp UTC | Revision | Status | Latency |
| --- | --- | ---: | ---: |
| 2026-04-19 07:49:37 | `00083-97t` | 403 | 34.969s |
| 2026-04-19 07:49:40 | `00083-97t` | 403 | 31.796s |
| 2026-04-19 07:49:40 | `00083-97t` | 403 | 31.473s |
| 2026-04-19 07:49:45 | `00083-97t` | 403 | 26.736s |
| 2026-04-19 07:49:49 | `00083-97t` | 403 | 23.259s |
| 2026-04-19 07:49:58 | `00083-97t` | 403 | 13.944s |
| 2026-04-19 07:50:03 | `00083-97t` | 403 | 8.810s |
| 2026-04-19 07:50:04 | `00083-97t` | 403 | 8.204s |
| 2026-04-19 07:50:09 | `00083-97t` | 403 | 3.421s |
| 2026-04-19 07:50:12 onward | `00083-97t` | 403 | ~3-4ms |

The latencies decay toward normal instead of remaining consistently high. That shape is
not consistent with an auth dependency that always performs slow work.

The same time window contained model-load related log lines:

- Vosk model loading between `07:49:16` and `07:49:21`
- Transformers warning at `07:49:30`
- a later `/api/chat` request around `07:50:13` taking `8.267s`

The most likely interpretation is that invalid `/api/character` requests were queued
behind CPU-bound or blocking model initialization/inference work in the same service
instance. They were eventually rejected quickly once the event loop could process the
auth dependency, but Cloud Run request latency includes the time spent waiting.

### 2026-04-22 reproduction during #480 rollout

During the #480 runtime update, revision `engineer-cafe-backend-00085-pk5` showed a
similar decay pattern after deployment rollout:

| Timestamp UTC | Revision | Status | Latency |
| --- | --- | ---: | ---: |
| 2026-04-22 12:22:32 | `00085-pk5` | 403 | 48.405s |
| 2026-04-22 12:22:35 | `00085-pk5` | 403 | 45.378s |
| 2026-04-22 12:22:35 | `00085-pk5` | 403 | 45.284s |
| 2026-04-22 12:22:40 | `00085-pk5` | 403 | 40.455s |
| 2026-04-22 12:22:44 | `00085-pk5` | 403 | 36.824s |
| 2026-04-22 12:22:52 | `00085-pk5` | 403 | 29.011s |
| 2026-04-22 12:22:59 | `00085-pk5` | 403 | 22.060s |
| 2026-04-22 12:23:03 | `00085-pk5` | 403 | 17.368s |
| 2026-04-22 12:23:13 | `00085-pk5` | 403 | 7.605s |
| 2026-04-22 12:23:21 | `00085-pk5` | 403 | 1.832s |
| 2026-04-22 12:23:26 onward | `00085-pk5` | 403 | ~4-11ms |

The same window included:

- `POST /api/voice` returning `200` after `63.737s`
- `/health` returning `200` after `33.629s`
- `POST /api/chat` returning `200` after `36.504s`
- Vosk model loading logs
- a Transformers `torch_dtype` warning

This broader evidence shows that the slow period affected multiple endpoints, not only
invalid `/api/character` requests. That makes an endpoint-specific auth bug unlikely.

## Decision

Treat #488 as a Cloud Run cold-start / rollout / lazy model-load queuing issue, not as a
slow API-key validation implementation.

Keep the application-level auth dependency unchanged for now. It is simple, fail-closed,
and does not perform remote I/O. The next work should focus on reducing or making visible
the pre-auth wait window caused by instance startup and model load.

## Consequences

### What this explains

- Why a logically trivial `403` can report 30-50s latency in Cloud Run.
- Why the slow responses appear in bursts and decay to millisecond latency.
- Why the same symptom reappeared during deployment rollout despite `minScale=1`.
- Why `/health`, `/api/voice`, and `/api/chat` were also slow in the same window.

### What this does not yet prove

- The exact component blocking the event loop in every case.
- Whether Qwen, Vosk, Piper, Supabase startup work, or a combination was the dominant
  blocker in each incident.
- Whether `containerConcurrency=160` amplified the queue under startup pressure.

## Recommended follow-up

### Short term

1. Keep `minScale=1`; it is necessary but not sufficient.
2. Add Cloud Run log-based metrics for:
   - `httpRequest.status=403 AND httpRequest.latency>1s`
   - `httpRequest.status=403 AND httpRequest.latency>10s`
   - all endpoints with `httpRequest.latency>30s` during revision rollout windows
3. During deploy validation, query logs for the first 5 minutes after a revision becomes
   ready and explicitly check whether 403 latency decays to <1s.
4. Keep `scripts/verify-deployment.sh` and frontend smoke checks in the release gate.

### Medium term

1. Add request lifecycle observability that can distinguish:
   - Cloud Run/platform queue time
   - ASGI middleware entry time
   - `verify_api_key()` duration
   - route handler duration
2. Consider lowering `containerConcurrency` if startup windows continue to queue many
   requests behind heavy model work.
3. Move heavyweight model warm-up behind an explicit readiness gate if accepting a longer
   rollout is preferable to serving traffic before models are warm.
4. Audit synchronous model initialization and inference paths. #478 removed the MP3
   encoding event-loop blocker, but STT/TTS/model loading can still block startup windows.

### Longer term

If immediate rejection of invalid requests is required even during backend startup,
application-level FastAPI auth is not enough. Put the first auth gate in front of the
container, for example at an edge/proxy layer or Cloud Armor/API Gateway equivalent.

## Validation plan

After the next backend deployment:

```bash
gcloud run services describe engineer-cafe-backend \
  --region=asia-northeast1 \
  --format='value(status.latestReadyRevisionName)'

gcloud logging read \
  'resource.type="cloud_run_revision"
   AND resource.labels.service_name="engineer-cafe-backend"
   AND httpRequest.status=403
   AND httpRequest.latency>"1s"
   AND timestamp>="YYYY-MM-DDTHH:MM:SSZ"' \
  --limit=50 \
  --format='value(timestamp,resource.labels.revision_name,httpRequest.requestUrl,httpRequest.status,httpRequest.latency)'
```

The deployment is healthy when invalid `/api/character` requests return to sub-second
latency after warm-up and there are no sustained `403` latencies above 1s outside rollout
or model-load windows.

## Related issues and PRs

- #488: `/api/character` 403 responses taking 31-35s
- #480: STT postprocess + Cloud Run min instances
- #478 / #498: MP3 encoding moved off the event loop
- #486 / #500: Supabase long-term memory reconnect and retry
