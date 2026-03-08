# Production Diagnostic Report

> Date: 2026-03-07 (Updated: 2026-03-08)
> Environment: Cloud Run (asia-northeast1) + Cloudflare Workers
> Status: ALL CRITICAL ISSUES FIXED (PR #188, deployed 2026-03-08)

## Executive Summary

~~Frontend (Cloudflare Workers) is deployed and serving the UI. Backend (Cloud Run) is running (Uvicorn up, `/api/character` returns 200). However, **3 critical issues** prevent core functionality from working.~~

**2026-03-08 UPDATE**: All 3 critical issues have been fixed and deployed via PR #188. curl verification confirmed all endpoints return 200 OK. Details of original issues preserved below for reference.

---

## Critical Issues

### 1. VoiceVox TTS: Connection Failure (Voice completely broken) — FIXED

**Status**: FIXED (PR #188, 2026-03-08)

**Fix applied**: VoiceVox is now deployed as a separate Cloud Run service (`voicevox-proto`). CI/CD updated from `--set-env-vars` to `--update-env-vars` with explicit `TTS_PROVIDER=voicevox` and `VOICEVOX_API_URL=https://voicevox-proto-639959525777.asia-northeast2.run.app`. Verified: TTS returns 200 OK with 207KB WAV audio.

<details><summary>Original diagnosis (resolved)</summary>

**Symptom**: `httpx.ConnectError: All connection attempts failed` at `voice_agent.py:484`

**Root Cause**: VoiceAgent defaults to `tts_provider="voicevox"` (`backend/main.py:502`). VoiceVox requires a local Docker container (`http://localhost:50021`), which is NOT available in the Cloud Run environment. Similarly, Kokoro TTS (`http://localhost:8880`) is also unavailable.

**Code path**:
- `backend/main.py:502`: `tts_provider = os.getenv("TTS_PROVIDER", "voicevox")`
- `backend/agents/voice_agent.py:584-586`: Creates `VoiceVoxClient(api_url="http://localhost:50021")`
- `backend/agents/voice_agent.py:712-714`: Japanese TTS calls VoiceVox, fails
- `backend/agents/voice_agent.py:733-743`: Fallback also tries VoiceVox again (same provider), fails
</details>

### 2. LangGraph Checkpointer: AsyncPostgresSaver API Incompatibility — FIXED

**Status**: FIXED (PR #188, 2026-03-08)

**Fix applied**: `checkpointer.py` rewritten to use context manager pattern (`__aenter__`/`__aexit__`) matching `store.py`. Added singleton with `asyncio.Lock`, `get_checkpointer_context()` for safe usage, and 13 unit tests passing.

<details><summary>Original diagnosis (resolved)</summary>

**Symptom**: `TypeError: object _AsyncGeneratorContextManager can't be used in 'await' expression` at `checkpointer.py:78`

**Root Cause**: `AsyncPostgresSaver.from_conn_string()` in langgraph-checkpoint-postgres >= 2.0.0 returns an `@asynccontextmanager` (not a coroutine). The code uses `await` on it, which fails.

**Code**:
```python
# checkpointer.py:78 - BROKEN
checkpointer = await AsyncPostgresSaver.from_conn_string(db_uri)

# store.py:57 - CORRECT (same library, different module)
_store_cm = AsyncPostgresStore.from_conn_string(db_uri)
store = await _store_cm.__aenter__()
```
</details>

### 3. Marp API: Hardcoded 503 — FIXED

**Status**: FIXED (PR #188, 2026-03-08)

**Fix applied**: `frontend/src/app/api/marp/route.ts` rewritten to proxy POST requests to `${getBackendApiUrl()}/api/slides`. Backend `/api/slides` endpoint returns narration, slide data, and VRM control. Verified: returns 200 OK with slide content.

<details><summary>Original diagnosis (resolved)</summary>

**Symptom**: `/api/marp` returns 503 with "Marp API temporarily disabled during backend migration"

**Root Cause**: `frontend/src/app/api/marp/route.ts:9-13` was hardcoded to return a 503 error. This was intentionally disabled during the backend migration but never re-enabled.
</details>

---

## Non-Critical Issues

### 4. VRM 0.0 Warnings (Cosmetic)

**Symptom**:
- `Curves of LookAtDegreeMap defined in VRM 0.0 are not supported`
- `createVRMAnimationClip: VRMLookAtQuaternionProxy is not found`

**Root Cause**: The VRM model file uses VRM 0.0 format features that are deprecated in @pixiv/three-vrm 3.4.1. These are non-fatal warnings.

**Impact**: No functional impact. Character renders correctly.

**Fix**: Low priority. Could update VRM model to 1.0 format, or suppress warnings.

---

## Architecture: Production vs Local

| Component | Local Dev | Production (Cloud Run) | Status |
|-----------|-----------|----------------------|--------|
| TTS (JA) | VoiceVox Docker (localhost:50021) | VoiceVox Cloud Run (asia-northeast2) | FIXED |
| TTS (EN) | Kokoro Docker (localhost:8880) | Google Cloud TTS fallback | OK |
| STT | Vosk local / Google Cloud | Google Cloud only | OK |
| LLM | OpenRouter API | OpenRouter API | OK |
| Database | Supabase (remote) | Supabase (remote) | OK |
| Checkpointer | AsyncPostgresSaver | AsyncPostgresSaver (context manager) | FIXED |
| Marp/Slides | Backend proxy | Backend proxy (`/api/slides`) | FIXED |

---

## Fix History

All fixes applied in PR #188 (merged 2026-03-08, auto-deployed to Cloud Run):

1. **[P0] Checkpointer** — Context manager pattern applied. 13 unit tests passing.
2. **[P0] TTS** — VoiceVox deployed as separate Cloud Run service. CI/CD uses `--update-env-vars` to preserve config.
3. **[P1] Marp API** — Frontend proxies to backend `/api/slides`. Returns 200 OK.
4. **[P1] CI/CD** — `--set-env-vars` → `--update-env-vars` to prevent env var overwrites on deploy.
