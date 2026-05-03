# Alpha Reset Handoff 2026-05-03

Use this handoff when resuming implementation after the docs reset PR.

## Stop Rule

Implementation and merge monitoring stopped at the user's request. Do not continue the previous
full-suite watch loop or opportunistically merge open PRs before re-reading the reset status.

Primary references:

- [Alpha Live Verification Status 2026-05-03](../testing/alpha-live-verification-status-2026-05-03.md)
- [Alpha Reset Plan 2026-05-03](../plans/alpha-reset-plan-2026-05-03.md)
- [ADR 008](../adr/008-operational-verification-and-deployment-guardrails.md)
- [ADR 019](../adr/019-alpha-live-ragas-case-accounting.md)

## Known Open PRs

- #736: frontend node test discovery. CI was green when checked, but it was intentionally left
  unmerged for the reset.
- #716: memory warning tightening. Draft/conflicting; rebase before any merge decision.
- #706: M5Stack hardware integration. Keep open until firmware/security/hardware proof is ready.

## Known Closed/Resolved Issues From Sweep

- #653: Q quality, after run `25274709049` reported `25 PASS / 0 WARN / 0 FAIL`.
- #721: null-byte / persistence issue, after D/M run `25275030436` had zero Cloud Logging errors.
- #729: backend pytest timeout dependency, via #734.
- #732: unbounded alpha workflow step timeout, via #735.

## Resume Order

1. Read the current GitHub issue/PR state. Develop may have moved since this handoff.
2. If #736 is still open, treat it as a separate hygiene PR. Do not mix it with P0 fixes.
3. Start with #658 STT latency. Use targeted STT runs.
4. Then fix #583/#672 C answer/source quality using run `25274709049` artifacts.
5. Only after targeted STT and C are green, consider another full `suites=all` dispatch.
