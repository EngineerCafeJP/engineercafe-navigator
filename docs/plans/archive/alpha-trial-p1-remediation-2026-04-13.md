> Status: completed (2026-05-18); archived by FU-29 and superseded by `docs/plans/wave3-engineer-handoff-master-2026-05-18.md`.

# Alpha Trial Start And P1 Remediation Plan

Date: 2026-04-13
Scope: Start alpha user testing for the kiosk core flow while tracking the remaining P1 quality and implementation risks in a fixed execution order.
Tracking issue: #460

> 履歴注記: この文書は 2026-04-13 時点の alpha 開始判断を記録したものです。
> 現在の follow-up plan は [production-readiness-followup-2026-04-19.md](production-readiness-followup-2026-04-19.md) を参照してください。

## Objective Status

The current build is suitable for a controlled alpha trial of the kiosk core flow.

That statement is intentionally narrower than "all risks are closed" or "no production errors exist."

As of 2026-04-13:

- Browser-level kiosk core flows are merge-gated in CI:
  - `smoke.spec.ts`
  - `reception-flow.spec.ts`
  - `webgl-fallback.spec.ts`
  - `voice-live.spec.ts`
- Live backend scenario and voice round-trip tests exist on the backend side.
- Cloud Run and Vercel are deployed and the core text and voice paths have been exercised.

However, the following remain true:

- Cloud Run logs still show at least one recent `POST /api/voice` `500` caused by STT failure fallback exhaustion.
- VRM expression fidelity, VRMA animation behavior, lipsync quality, and target-device verification remain open.
- Multilingual quality is improved but not yet closed to the target bar.
- Load and performance baselines are not yet established.
- The full autonomous reception flow is not yet integrated end-to-end.

## Alpha Trial Decision

### Allowed now

- Controlled alpha testing with real users on the kiosk UI
- Text query flow validation
- Browser voice flow validation
- Operator-observed reception workflow validation
- Live deploy validation against the current Vercel + Cloud Run stack

### Not yet claimable

- Zero-error production operation
- Full device/browser coverage for kiosk hardware
- Fully closed multilingual quality work
- Full autonomous new/repeat visitor reception integration
- Performance guarantees under concurrent load

## Active Risk Register

| Priority | Issue | Why it still matters during alpha |
|---|---|---|
| P1 | #458 | Emotion tags, VRM expressions, and animation mapping are still inconsistent and can degrade perceived assistant quality |
| P1 | #190 | Character-specific validation on real devices and browsers is still incomplete |
| P1 | #138 | English and multilingual quality still has known gaps, especially evaluation targets and some English retrieval cases |
| P1 | #140 | No load/performance baseline exists yet, so concurrency risk remains unknown |
| P1 | #117 | Full autonomous reception flow is not integrated end-to-end yet |

## Execution Order

### Step 1: Fix expression and animation correctness (#458)

Owner intent:
- Normalize backend emotion tags
- Make expression mapping deterministic
- Remove partial-intensity behavior unless explicitly desired
- Align animation selection with the same emotion contract

Exit criteria:
- Character control payload uses a stable emotion vocabulary
- Happy/sad/neutral cases map correctly in UI verification
- No obvious "neutral fallback when emotion exists" behavior remains

### Step 2: Re-run character validation against the live UI (#190)

Owner intent:
- Verify VRM expression fidelity
- Verify VRMA animation behavior
- Verify lipsync timing and visual coherence
- Verify at least one target tablet/browser environment

Exit criteria:
- Character team validation checklist is filled with PASS/FAIL evidence
- Any remaining defects are split into concrete follow-up issues

### Step 3: Close remaining multilingual quality gaps (#138)

Owner intent:
- Improve English retrieval misses
- Raise multilingual answer consistency
- Add or strengthen evaluation and E2E assertions where useful

Exit criteria:
- English retrieval gap cases are explicitly fixed or documented
- zh/ko happy-path answers remain stable
- Target metrics or a justified revised target are recorded

### Step 4: Establish load and latency baseline (#140)

Owner intent:
- Measure p50/p95/p99 for text, STT, and TTS paths
- Check concurrent session behavior
- Produce a reproducible baseline

Exit criteria:
- Load script exists
- Baseline report exists
- Known bottlenecks and practical alpha limits are documented

### Step 5: Continue autonomous reception integration (#117)

Owner intent:
- Move from operator-observed kiosk trial to fuller autonomous reception behavior
- Integrate repeat/new visitor branching and slide handoff as originally planned

Exit criteria:
- End-to-end reception stages are implemented coherently
- The integrated flow has its own validation path

## Operating Rule During Alpha

- Alpha trial proceeds now for kiosk core usage.
- Any new issue that breaks text chat, browser voice round-trip, kiosk shell startup, or live deploy health is treated as an immediate blocker.
- P1 issues above are worked in order while the alpha trial is running.

## References

- `docs/adr/006-langgraph-workflow-redesign.md`
- `docs/adr/007-stt-parallel-architecture.md`
- `docs/plans/alpha-ui-e2e-hardening-2026-04-12.md`
