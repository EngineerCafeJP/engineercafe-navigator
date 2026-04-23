# ADR 013: VRM Generation Fire-and-Forget (Parallel Endpoint)

**Status**: Accepted
**Date**: 2026-04-24
**Context**: Issue #479

## Context

The `/api/voice` endpoint's `synthesize_lab_tts` path blocks on VRM generation (`CharacterControlAgent.process`) for 100-500ms, delaying the audio response to the user.

Three approaches were considered:

1. **Fire-and-forget + WebSocket push**: Return audio immediately, push VRM data via WebSocket
2. **Parallel endpoint**: New `/api/character/auto` endpoint; frontend calls both in parallel
3. **Inline deprecation only**: Just add deprecation warning, defer to Epic D

## Decision

We chose **Approach 2 (Parallel endpoint)** for Alpha.

### Rationale

- Zero frontend state management complexity (no WebSocket lifecycle, no reconnection)
- Frontend uses `Promise.all([fetch('/api/voice'), fetch('/api/character/auto')])` - one round-trip
- p50 improvement achievable by parallelization alone
- WebSocket approach requires Epic D design (connection mgmt, reconnection, backpressure)
- Deprecation path is clean: `includeVrmControl` flag remains for backward compatibility

## Consequences

### Positive

- `/api/voice` latency reduced by 100-500ms (VRM generation no longer blocks)
- Frontend controls parallelism explicitly
- Clean backward compatibility via `includeVrmControl` deprecation

### Negative

- Two HTTP requests instead of one (mitigated by HTTP/2 multiplexing)
- Frontend must handle partial failure (voice succeeds, VRM fails -> neutral expression)

### Migration Path

1. **Phase 1 (this PR)**: Backend adds `/api/character/auto`, deprecates `includeVrmControl`
2. **Phase 2 (frontend PR)**: Frontend switches to parallel fetch pattern
3. **Phase 3 (post-Alpha)**: Remove `includeVrmControl` from `/api/voice` entirely
