# Alpha Reset Plan 2026-05-03

This plan is the next-session entry point after the long-running 2026-05-03 implementation and
merge sweep. It replaces the "watch the full run" posture from
[Alpha Remediation Plan 2026-05-02](alpha-remediation-plan-2026-05-02.md).

## Reset Decision

Stop implementation churn, merge a docs-only reset, then resume with targeted fixes. The repository
has enough workflow coverage now; repeated full-suite runs before fixing known blockers waste time
and make issue state harder to trust.

Current alpha status: **NO-GO**.

## Ground Truth At Reset

- `develop`: `3b3b370265834d8db032917d4452e9a488d055ca`
- Latest valid C/Q proof: run `25274709049`
- Latest valid STT/D/M proof: run `25275030436`
- C/Q conclusion:
  - C alpha-127 accounted and evaluated all 127 cases with direct OpenAI.
  - Q passed 25/25.
  - C failed JA/EN answer correctness and KO source grounding.
- STT/D/M conclusion:
  - STT failed current-revision latency.
  - D/log hygiene passed with memory warnings.
  - M passed with one cross-session recall warning.

## P0 / P1 Work Queue

### P0-A: #658 STT latency

Goal: make current deployed STT pass the alpha gate without hiding real latency.

Evidence:

- Run `25275030436`
- p95 `15624ms`
- max `15976ms`
- over 10s `14/29` (`48.3%`)
- no timeout errors

Next steps:

- Inspect per-sample STT artifacts and provider path split.
- Determine whether latency is model warmup, Qwen primary, Vosk fallback, Cloud Run resource, or
  test pacing.
- Fix product/runtime first. Adjust the gate only if the current threshold is demonstrably invalid.
- Re-run `suites=stt,v`, then comment #658 with exact counters.

### P0-B: #583 / #672 C alpha-127 quality and sources

Goal: make the complete 127-case C gate pass with direct OpenAI.

Evidence:

- Run `25274709049`
- requested/collected/evaluated `127/127/127`
- collection errors `0`
- JA answer correctness `0.5671 < 0.85`
- EN answer correctness `0.6914 < 0.75`
- KO source failure: `gt-113` returned `[fallback]`

Next steps:

- Pull and inspect C artifacts before changing code.
- Classify failures into answer generation, retrieval/source, fixture expectation, or threshold.
- Prefer product-side fixes for routing, source selection, and answer content.
- Re-run `suites=c-127`; do not use partial C metrics as release proof.

### P0-C: #697 / #698 / #585 device and onsite proof

Goal: prove merged audio and M5Stack changes on real target devices.

Evidence:

- PR #730 implemented iOS tap-to-enable UI, but #697/#634/#635/#471 remain proof-gated.
- PR #731 implemented M5Stack simulation E2E, but #585 requires real M5Stack + kiosk proof.

Next steps:

- Capture iPhone/iPad Safari delayed TTS proof for #697.
- Capture Android large-audio proof for #698 or explicitly demote it with rationale.
- Keep #706 open until hardware firmware/security/readiness proof is present.
- Keep #585 open until real device and 2h onsite round-trip proof is attached.

### P1-A: #655 / #716 memory warning semantics

Goal: decide whether M-LTM warnings are alpha blockers or post-alpha hardening.

Evidence:

- Run `25275030436`
- M: `4 PASS / 1 WARN / 0 FAIL`
- warning: `M-LTM-001` cross-session recall empty
- #716 is draft/conflicting and should not merge before rebase.

Next steps:

- Rebase #716 only after STT and C are no longer blocking.
- Keep M warning semantics explicit: do not silently turn warnings into passes.
- Re-run `suites=m` after #716 or an alternative memory fix.

### P1-B: #717 / #719 operational proof

Goal: close infra issues only after env and workflow proof.

Evidence:

- PR #727 merged implementation and runbooks.
- #717/#719 were intentionally reopened because implementation-only closure is insufficient.

Next steps:

- Configure required secrets/env.
- Run the DB drift workflow and cron alert path once.
- Attach proof windows/artifacts, then close.

### Hygiene / Sequencing

- #736 is ready-looking but was intentionally left open at reset. Merge it separately only after
  this docs PR is merged and current branch protection state is clear.
- #670 should close only after the next C/Q proof demonstrates useful logs and compact artifacts.
- Avoid closing #634/#635/#471 independently unless #697 remains the canonical proof tracker or
  the device proof passes.

## Definition Of Alpha GO

Alpha GO requires all of the following:

- C alpha-127 complete and green: `127/127/127`, zero collection/RAGAS errors, thresholds pass.
- Q green: no failures.
- STT current-revision gate green.
- D/log hygiene has no live error signatures in the run window.
- M warnings are either fixed or explicitly accepted as non-blocking.
- iOS/Android/onsite proof issues are closed or explicitly waived with dated rationale.
- #643 umbrella has linked run URLs and artifact evidence for each accepted gate.
