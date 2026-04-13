# Security Documentation

> Last updated: 2026-04-12. This document reflects the current production topology: Vercel frontend, Cloud Run backend, and Supabase database.

## Overview

Engineer Cafe Navigator is a multilingual voice AI agent system deployed as a Vercel-hosted Next.js frontend backed by a Cloud Run FastAPI/LangGraph service and a Supabase database. The threat surface spans:

- Unauthenticated access to admin, cron, and monitoring API routes
- Direct browser calls to backend services or the Supabase API
- Injection through voice/text input reaching LLM prompts or SQL
- Path traversal in resource identifiers (STT vocabulary, slide files)
- Timing-oracle attacks on token comparison
- Resource exhaustion through unbounded request rates

The sections below describe how each layer is protected as of 2026-03-15.

---

## Authentication Architecture

### Layer 1: Frontend Middleware (PR #233)

**File**: `frontend/src/middleware.ts`

All routes under `/api/admin/*`, `/api/cron/*`, and `/api/monitoring/*` are protected by a Next.js Edge Runtime middleware that runs before any route handler.

**How it works**:

1. The middleware reads the `ADMIN_API_SECRET` environment variable.
2. If the secret is absent in a `NODE_ENV=production` environment, the middleware returns `401 Unauthorized` immediately (fail-closed). In non-production environments without the secret, the request proceeds, allowing local development without a secret.
3. If the secret is present, the middleware extracts the `Authorization` header and compares it against `Bearer <ADMIN_API_SECRET>` using a SHA-256-based timing-safe comparison. Both strings are hashed before the byte-by-byte XOR comparison, which prevents timing oracles even on variable-length inputs in the Edge Runtime (where Node.js `crypto.timingSafeEqual` is unavailable).
4. Any mismatch returns `401 Unauthorized`.

**Protected route groups**:

| Pattern | Purpose |
|---|---|
| `/api/admin/:path*` | Knowledge base management, STT vocabulary, admin operations |
| `/api/cron/:path*` | Scheduled slide updates and other cron jobs |
| `/api/monitoring/:path*` | Internal health and metrics endpoints |

**Excluded route**: `/api/alerts/webhook` is not covered by this middleware. It implements its own independent `ALERT_WEBHOOK_SECRET` verification.

**Required environment variable**: `ADMIN_API_SECRET` — must be set in the Vercel project environment for production deployments.

### Layer 2: Backend API Key (PR #234)

**File**: `backend/main.py`

The FastAPI backend enforces an `API_SECRET_KEY` requirement at two points:

1. **Startup gate**: If `ENVIRONMENT=production` and `API_SECRET_KEY` is absent or empty, the process calls `sys.exit(1)` and refuses to start. This prevents a misconfigured deployment from silently exposing write-capable endpoints.

2. **Per-request dependency**: Protected endpoints declare `verify_api_key` as a FastAPI dependency. The function reads the `X-API-Key` request header and compares it against `_API_SECRET_KEY` using `hmac.compare_digest`, which provides constant-time comparison in CPython. If the key is missing or incorrect, the endpoint returns `403 Forbidden`. If a `production`, `staging`, or `preview` instance is running without a key (defence in depth), it returns `503 Service Unavailable` rather than permitting access.

**Required environment variable**: `API_SECRET_KEY` — must be set as a Cloud Run secret before deploying to production, and should also be set for any staging or preview environment that is expected to remain protected.

### Defense-in-Depth Summary

| Scenario | Frontend middleware | Backend dependency | Result |
|---|---|---|---|
| Valid Bearer token, valid X-API-Key | Pass | Pass | Request served |
| Valid Bearer token, missing X-API-Key | Pass | 403 | Blocked at backend |
| Invalid Bearer token | 401 | Not reached | Blocked at edge |
| `ADMIN_API_SECRET` not set (production) | 401 | Not reached | Blocked at edge |
| `API_SECRET_KEY` not set (production) | — | sys.exit(1) | Process never starts |

---

## STT Vocabulary Proxy (PR #235)

Before PR #235, some browser clients called the backend STT vocabulary API directly, which required `NEXT_PUBLIC_BACKEND_API_URL` to be exposed as a public environment variable and allowed path traversal through unvalidated vocabulary IDs.

After PR #235:

- All STT vocabulary operations are routed through `/api/admin/stt`, which is now protected by the frontend middleware described above.
- `NEXT_PUBLIC_BACKEND_API_URL` is no longer required by browser clients.
- The route handler validates vocabulary IDs against a strict format pattern before forwarding requests to the backend, blocking path traversal attempts.

---

## RAG Ingestion Proxy (PR #236)

Before PR #236, some frontend admin routes read from and wrote to the Supabase `knowledge_base` table directly using the service role key, bypassing the backend's input validation and embedding pipeline.

After PR #236:

- All admin knowledge operations are proxied through `backendFetch`, which calls the authenticated FastAPI backend.
- The backend performs input validation and uses OpenAI `text-embedding-3-small` (1536 dimensions) for all embeddings. There is no mixed-model path.
- No frontend route accesses the `knowledge_base` table directly for write operations.

---

## Database Security

All PostgreSQL tables managed through Supabase have Row Level Security (RLS) enabled. The service role key, which bypasses RLS, is used only in server-side contexts (Next.js route handlers and the FastAPI backend). It is never exposed to browser clients.

Key tables:

| Table | Access |
|---|---|
| `knowledge_base` | Server-side only via backend proxy after PR #236 |
| `conversation_sessions` | Server-side only |
| `conversation_history` | Server-side only |
| `agent_memory` | Server-side only; 3-minute TTL on entries |

---

## Rate Limiting

The FastAPI backend uses `slowapi` for rate limiting keyed by remote address. The import is no longer a soft no-op: if `slowapi` cannot be imported, `main.py` calls `sys.exit(1)` in production and raises `RuntimeError` in other environments. This ensures rate limiting is either active or the process does not start.

Infrastructure-level throttling (Cloud Run concurrency limits and Vercel/edge request limits) provides an additional layer.

---

## Input Validation

### Frontend

Route handlers validate request bodies with Zod schemas before forwarding to the backend. Key schemas cover voice processing (action enum, audio size cap, UUID session ID), slide control (action enum, slide number range, safe filename pattern), and character control (action enum, animation name allowlist pattern).

### Backend

The backend uses Pydantic model validation on all request bodies. The `utils/input_sanitizer.py` module applies additional sanitization for inputs that reach LLM prompts, preventing prompt injection through voice transcripts or free-text fields.

---

## XSS and Content Isolation

Marp slide HTML is sanitized before rendering. The `MarpViewer` component:

- Strips `<script>` tags and their content.
- Removes all `on*` event handler attributes from every element.
- Removes `javascript:`, `data:text/html`, and `vbscript:` URLs from `href`, `src`, `action`, `formaction`, and `data` attributes.
- Removes `<object>`, `<embed>`, `<applet>`, and dangerous `<meta>` and `<base>` tags.
- Renders sanitized HTML inside a sandboxed `<iframe>` with `allow-scripts allow-same-origin allow-popups allow-forms` and without `allow-top-navigation` or `allow-modals`.

Incoming `postMessage` events from the iframe are validated against an origin allowlist (`window.location.origin` and `"null"` for `srcDoc` content) before processing.

---

## Environment Variable Contracts

The following secrets must be configured before a production deployment is valid. Missing any secret in the column marked "Blocks startup" causes the process to refuse to start.

| Variable | Service | Blocks startup | Purpose |
|---|---|---|---|
| `ADMIN_API_SECRET` | Frontend (Vercel) | Yes (returns 401 in prod) | Protects `/api/admin/*`, `/api/cron/*`, `/api/monitoring/*` |
| `API_SECRET_KEY` | Backend (Cloud Run) | Yes (`sys.exit(1)`) | Authenticates frontend-to-backend requests |
| `ALERT_WEBHOOK_SECRET` | Frontend (Vercel) | No | Authenticates `/api/alerts/webhook` POST |
| `SUPABASE_SERVICE_ROLE_KEY` | Frontend + Backend | No (but functionally required) | Server-side Supabase access |
| `OPENAI_API_KEY` | Backend | No (but functionally required) | Text embeddings |

Do not use `--set-env-vars` on Cloud Run deployments — it overwrites all existing variables. Use `--update-env-vars` instead.

---

## Known Remaining Gaps

The following items were identified during the 2026-03-14 hardening audit and are tracked under Issue #232. They are not yet resolved.

**Reception session durability**: Active reception sessions are stored in a process-local `OrderedDict` in `backend/api/reception.py`. A Cloud Run restart or scale-out event will lose active sessions. The fix requires routing session storage through the Supabase-backed repository abstraction.

**Frontend env contract drift**: `frontend/src/lib/env.ts` still declares several variables as required that recent proxy cleanup has made optional. The validation helpers are not enforced at runtime. These need to be reconciled with the actual runtime contract.

**Browser and device validation**: Audio pipeline changes (WebM-to-WAV conversion, Web Audio API autoplay fixes) and VRM compatibility fixes from recent PRs have not been confirmed on all target kiosk browsers and tablet hardware. This is a deployment risk, not an authentication risk, but it belongs in a production sign-off checklist.

**Frontend E2E coverage is focused on kiosk core flows**: Playwright now gates smoke, reception, WebGL fallback, and live browser voice round-trip flows. Admin authentication and other backoffice paths are still not covered end-to-end.

---

## Security Testing

**Pre-merge checks run automatically via CI**:

- `ruff check .` and `black --check .` (backend) flag insecure patterns caught by the rule sets.
- `pnpm lint` and `pnpm typecheck` (frontend) catch type errors in auth logic.

**Manual checks required before each production deployment**:

- Confirm `ADMIN_API_SECRET` and `API_SECRET_KEY` are set in the target environment.
- Send a request to `/api/admin/knowledge` without an Authorization header and verify the response is `401`.
- Send a request to the backend health endpoint without `X-API-Key` and verify the response is `403`.
- Confirm the backend process refuses to start when `API_SECRET_KEY` is unset in a production-equivalent environment.

---

## Incident Response

| Severity | Description | Target response |
|---|---|---|
| Critical | Data exfiltration, authentication bypass, process compromise | 30 minutes |
| High | Exposed endpoint, secret rotation required, service disruption | 2 hours |
| Medium | Anomalous access pattern, rate limit breach, dependency CVE | 24 hours |
| Low | Lint-level finding, informational CVE with no exploit path | 1 week |

**Contact**: security@engineer-cafe.jp

**On credential exposure**: Rotate the affected secret immediately using Cloud Run `--update-env-vars` or the Vercel project environment settings. Do not reuse the exposed value. Audit access logs for the period between suspected exposure and rotation.

---

## References

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Web Crypto API — `SubtleCrypto.digest`](https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/digest)
- [Python `hmac.compare_digest`](https://docs.python.org/3/library/hmac.html#hmac.compare_digest)
- [Supabase Row Level Security](https://supabase.com/docs/guides/auth/row-level-security)
- [Vercel Environment Variables](https://vercel.com/docs/projects/environment-variables)
- [Cloud Run Secret Manager integration](https://cloud.google.com/run/docs/configuring/services/secrets)

---

[Home](../README.md) | [API Documentation](API.md) | [Deployment](DEPLOYMENT.md) | [Status](STATUS.md)
