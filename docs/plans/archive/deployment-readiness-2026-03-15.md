> Status: completed (2026-05-18); archived by FU-29 and superseded by `docs/plans/wave3-engineer-handoff-master-2026-05-18.md`.

# Deployment Readiness Plan

Last updated: 2026-03-16

## Context

Pre-deployment audit on develop branch found CRITICAL/HIGH issues that must be resolved before Dev environment deployment. This plan covers Waves 4-6 of the production hardening effort.

### Completed (2026-03-15 ~ 2026-03-16 session)
- Wave P0: Auth middleware + backend fail-closed (PRs #233, #234)
- Wave P1: STT proxy + RAG ingestion + chunking (PRs #235, #236)
- Wave 2: slowapi + reception persistence + docs + categories (PRs #237-240)
- Wave 3: Frontend cleanup + monitoring/alerts proxy (PRs #241, #242)
- Wave 4: Security audit fixes (PRs #246-248)
- Wave 5: OCR + agent cleanup + CSP + @mastra removal (PRs #249-252)
- Wave 6: PR #215 merge + VRM fix + Cloudflare→Vercel migration + heavy deps cleanup (PRs #254-256)
- **Total: 20 PRs merged, 6 Issues closed**
- RAG knowledge base: 80 entries seeded with OpenAI 1536-dim embeddings
- Supabase migrations: all applied (including reception_sessions)
- Frontend: Vercel auto-deploy verified (develop → Preview)
- Backend: Docker image built + pushed to Artifact Registry
- Cloud Run: API_SECRET_KEY + ENVIRONMENT=development set

### Remaining (Next Session)

#### Issue #257: Backend Cloud Run Deploy (HIGH)
- Docker image ready at `asia-northeast1-docker.pkg.dev/aipartner-426616/cloud-run-source-deploy/engineer-cafe-backend:latest`
- Command: `gcloud config set project aipartner-426616 && gcloud run deploy engineer-cafe-backend --image <above> --region asia-northeast1`
- Post-deploy: run `scripts/verify-deployment.sh <API_SECRET_KEY>`
- Prerequisite: GCP project must be set to `aipartner-426616`

#### Issue #258: .env File Consolidation (MEDIUM)
- Not a security issue (keys never committed to git history — confirmed)
- Delete redundant root .env files, consolidate frontend templates
- Create docs/ENV_SETUP.md
- Delegate to Codex CLI

### Previously completed (2026-03-15 session)
- Wave P0: Auth middleware + backend fail-closed (PRs #233, #234)
- Wave P1: STT proxy + RAG ingestion + chunking (PRs #235, #236)
- Wave 2: slowapi fix + reception persistence + docs refresh + categories proxy (PRs #237-240)
- Wave 3: Frontend cleanup + monitoring/alerts proxy (PRs #241, #242)
- Issue #232 closed, Issue #224 closed

### Audit Results Summary
- Backend: 2707 tests passed, 0 failed
- Frontend: lint/typecheck/build all pass
- Security: 3 CRITICAL, 5 HIGH, 4 MEDIUM
- Agent connectivity: 9/13 agents READY, 1 BLOCKED, 1 DISCONNECTED, 2 ORPHANED

## Tracking Issues

| Issue | Scope | Wave |
|-------|-------|------|
| [#243](https://github.com/EngineerCafeJP/engineercafe-navigator/issues/243) | Security: auth + CORS + fail-open | Wave 4 |
| [#244](https://github.com/EngineerCafeJP/engineercafe-navigator/issues/244) | Agent connectivity: OCR + cleanup | Wave 5 |
| [#245](https://github.com/EngineerCafeJP/engineercafe-navigator/issues/245) | npm audit + security headers | Wave 4-5 |

---

## Wave 4: Security Hardening (Day 1)

**Goal:** Fix all CRITICAL + HIGH security issues. Deploy-blocking.

### Execution Plan (3 parallel tracks)

```
Track A (Codex CLI): Backend auth fixes
  Branch: fix/security-audit-backend
  - C1: Add verify_api_key to reception_router (main.py:843)
  - C2: Add verify_api_key to /api/slides/content (main.py:680)
  - C3: Add GET /api/voice handler for supported_languages
  - H4: Extend verify_api_key to check staging/preview
  - H5: Make reception status session_id required
  - Tests for all changes

Track B (Codex CLI): Frontend security fixes
  Branch: fix/security-audit-frontend
  - H1: Remove Access-Control-Allow-Origin: * from 5 OPTIONS handlers
  - H3: Restrict next.config.js allowedOrigins to specific subdomain
  - M2: Fix innerHTML in audio-interaction-manager.ts

Track C (Sub-agent): npm dependency audit
  Branch: chore/npm-audit-fix
  - H2: pnpm audit fix
  - Manual updates for hono, undici, fast-xml-parser
  - Verify build passes after updates
```

### Acceptance Checks (Issue #243)
- [ ] All reception endpoints require API key
- [ ] /api/slides/content requires API key
- [ ] GET /api/voice returns supported languages
- [ ] CORS restricted to specific origin
- [ ] allowedOrigins restricted to production domain
- [ ] verify_api_key checks staging/preview
- [ ] session_id required on reception status
- [ ] npm audit: 0 CRITICAL, 0 HIGH

### Merge Order
1. Track A (backend) → develop
2. Track B (frontend) → develop
3. Track C (npm) → develop (may conflict with Track B, merge last)

---

## Wave 5: Agent Connectivity + Security Headers (Days 2-3)

**Goal:** Connect OCR agent, clean up orphaned agents, add security headers.

### Execution Plan (3 parallel tracks)

```
Track A (Codex CLI): OCR frontend connectivity
  Branch: feat/ocr-frontend-integration
  - Add image_data field to ChatRequest model
  - Create /api/ocr backend endpoint or extend /api/chat
  - Create frontend image capture UI component
  - Wire frontend upload → backend → VisionAgent
  - Tests

Track B (Codex CLI): Agent skeleton cleanup
  Branch: refactor/agent-cleanup
  - Delete ClarificationAgent (skeleton, never used)
  - Delete MemoryAgent (replaced by SimplifiedMemoryHelper)
  - Decision on CharacterControlAgent (integrate or remove)
  - Remove outdated comments (knowledge.py auth comment)
  - Tests

Track C (Sub-agent): Security headers
  Branch: fix/security-headers
  - Add Content-Security-Policy to backend and frontend
  - Replace X-XSS-Protection with CSP
  - Verify headers in dev deployment
```

### Acceptance Checks (Issues #244, #245)
- [ ] Frontend can send images → OCR agent processes them
- [ ] ClarificationAgent and MemoryAgent skeletons removed
- [ ] CharacterControlAgent decision implemented
- [ ] CSP header configured
- [ ] Security headers audit passes

---

## Wave 6: Frontend UI + Dev Deployment (Days 4-5)

**Goal:** PR #215 merge, UI integration, Dev environment deployment verification.

### Execution Plan

```
Track A: PR #215 rebase + conflict resolution
  - Rebase feat/new-knowledge-ui onto develop
  - Apply conflict resolution guide (posted as PR comment)
  - Verify: categories/metadata-templates routes kept
  - Verify: embedding model changed to OpenAI
  - Verify: chunking integrated
  - CI green + code review

Track B: Dev environment deployment
  - Docker build with all fixes (slowapi, langchain-text-splitters)
  - Cloud Run deploy (ENVIRONMENT=development)
  - Set API_SECRET_KEY and ADMIN_API_SECRET in Secret Manager
  - Smoke test: all endpoints respond correctly
  - Verify: auth middleware blocks unauthorized requests
  - Verify: OCR agent accessible (if Wave 5 complete)

Track C: Integration testing
  - curl tests for each endpoint (auth required/denied)
  - RAG ingestion test (upload PDF → chunks created)
  - Reception flow test (start → respond → complete)
  - Monitoring dashboard test
```

### Acceptance Checks
- [ ] PR #215 merged without regressions
- [ ] Dev Cloud Run deployment succeeds
- [ ] All endpoints respond (200 or expected auth errors)
- [ ] End-to-end flows work: chat, voice, slides, reception, knowledge admin

---

## Parallel Execution Strategy

### Resource Allocation
- **Codex CLI**: 2-3 worktrees simultaneous (backend + frontend + npm)
- **Sub-agents**: Code review, security review, test validation
- **Claude Code main**: Coordination, PR management, deployment

### Risk Mitigation
- Each wave has independent branches — no cross-wave dependencies
- CI must pass before any merge
- Code review on all PRs (sub-agent + human)
- Merge order within waves: backend → frontend → dependencies

### Rollback Plan
- Each wave is a separate set of PRs
- If Wave 4 breaks something, revert individual PRs
- Dev deployment uses `ENVIRONMENT=development` — auth bypass available
- Cloud Run revision rollback: `gcloud run services update-traffic --to-revisions=REVISION=100`
