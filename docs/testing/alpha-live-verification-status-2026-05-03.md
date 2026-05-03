# Alpha Live Verification Status 2026-05-03

This is the stop-point status after the 2026-05-03 merge and verification sweep. It supersedes
the "watch in progress" parts of
[Alpha Live Verification Status 2026-05-02](alpha-live-verification-status-2026-05-02.md)
for next implementation planning.

## Conclusion

**NO-GO**.

The alpha gate is now failing on runtime proof, not on missing workflow plumbing:

- Direct OpenAI RAGAS is confirmed.
- C-127 manifest accounting is fixed: the gate can prove `requested=127`.
- Q quality is currently green on the latest valid run.
- D/log hygiene is green for the latest D/M run window.
- STT current-revision latency is red again.
- C-127 answer/source quality is still red after complete collection.
- Mobile/iOS/Android and onsite kiosk proof remain open until target-device evidence is attached.

Do not dispatch another full `suites=all` run until the targeted STT and C/RAGAS blockers below are
fixed or explicitly waived. Full-suite runs are now expensive confirmation, not the fastest debugger.

## Develop / PR State

- Current documented base: `develop` at `3b3b370265834d8db032917d4452e9a488d055ca`
  (`Merge pull request #735 from EngineerCafeJP/codex/alpha-verification-bounds`).
- Merged in the sweep:
  - #727: cron alert and DB drift mechanism; #717/#719 intentionally remain open for env/workflow proof.
  - #731: M5Stack reception simulation E2E; #585 remains open for real device and 2h onsite proof.
  - #730: iOS tap-to-enable UI; #697/#634/#635/#471 intentionally remain open for iPhone/iPad proof.
  - #734: backend `pytest-timeout`; #729 closed.
  - #735: alpha verification bounds/telemetry; #732 closed, #670 remains open for live C/Q proof.
- Open at the stop point:
  - #736: frontend `node:test` discovery. CI was green when checked, but it is intentionally not merged in this docs reset.
  - #716: memory warning tightening, draft and conflicting/outdated.
  - #706: M5Stack hardware integration, open for hardware readiness; simulation coverage from #731 does not replace it.

## Verification Runs

### C/Q: run `25274709049`

- URL: <https://github.com/EngineerCafeJP/engineercafe-navigator/actions/runs/25274709049>
- Backend SHA: `1110089ab0c85bf267b2e78f19d16ab4b412a5f5`
- Provider: direct OpenAI
- Model: `gpt-5.2-2025-12-11`
- C alpha-127 result: failure
  - requested: `127`
  - collected: `127`
  - evaluated: `127`
  - collection errors: `0`
  - RAGAS errors: `0`
  - JA answer correctness: `0.5671` below target `0.85`
  - EN answer correctness: `0.6914` below target `0.75`
  - ZH answer correctness: pass
  - KO answer correctness: pass
  - KO source gate failed for `gt-113`: actual sources were `[fallback]` instead of a knowledge source.
- Q result: pass
  - `25 PASS / 0 WARN / 0 FAIL`
  - This is sufficient to close #653, which has been closed.

Interpretation: ADR 019 / PR #692 fixed the accounting problem, and PR #695/#701 fixed the earlier
429 collection failure enough to evaluate all 127 cases. The remaining C blocker is product quality
and source grounding, tracked by #583/#672.

### STT/D/M: run `25275030436`

- URL: <https://github.com/EngineerCafeJP/engineercafe-navigator/actions/runs/25275030436>
- Backend SHA: `1110089ab0c85bf267b2e78f19d16ab4b412a5f5`
- STT result: failure
  - samples: `29`
  - p95: `15624ms`
  - max: `15976ms`
  - over 10s: `14/29` (`48.3%`)
  - qwen-primary samples: `24`
  - vosk-fallback samples: `5`
  - no `TimeoutError`
- D result: pass with warnings
  - `45 passed, 10 warned, 0 failed`
  - warnings are `ltm_recall_s2: parallel_ltm`
  - Cloud Logging gate passed for the run window: `/api/chat` 5xx `0`, `ltm_store_write=failed` `0`,
    `memory_helper` errors `0`, invalid UUID / null-byte persistence signatures `0`.
- M result: pass with warning
  - `4 PASS / 1 WARN / 0 FAIL`
  - remaining warning: `M-LTM-001` cross-session recall empty.

Interpretation: #721 is closed because the null-byte/persistence class is proven fixed. #658 is
reopened because STT latency is again a current-revision alpha blocker. #655/#716 remain the memory
warning track, but they are not the current primary NO-GO reason.

## Issue State To Carry Forward

Primary alpha blockers:

- #643: umbrella alpha gate remains open.
- #658: STT current-revision latency failure.
- #583 / #672: C alpha-127 still misses JA/EN answer correctness and KO source grounding.
- #697 / #698 / #585: target-device and onsite proof.

Important but not first debugger:

- #670: C/RAGAS telemetry/bounds are implemented, but close only after a live C/Q run proves the
  artifact trail is operationally sufficient.
- #655 / #716: memory warning semantics remain open; #716 needs rebase/conflict resolution before merge.
- #717 / #719: infra mechanisms are merged, but env/secret/workflow proof is still required before closure.
- #706: hardware integration is not replaced by #731's simulation test.

Closed from this sweep:

- #653: Q quality gate passed 25/25.
- #721: null-byte / persistence live failure class did not recur in D/M proof.
- #729: backend pytest timeout dependency.
- #732: unbounded alpha workflow step timeout.

## Next Efficient Order

1. Merge this docs reset PR, then avoid broad implementation until the issue map is stable.
2. Fix #658 with a targeted STT latency investigation. Re-run only `suites=stt` or `suites=stt,v`.
3. Fix #672 by inspecting the 127 evaluated C artifacts. Separate response-generation defects,
   source-retrieval defects, and invalid ground-truth expectations.
4. Re-run only `suites=c-127` after the #672 fix. Require `requested=127`, `collected=127`,
   `evaluated=127`, `collection_errors=0`, and source/quality thresholds passing.
5. Handle #697/#698 with real target-device evidence. Close #634/#635/#471 only as duplicates after
   #697 remains the canonical proof issue or passes.
6. Rebase #716 only after the M warning policy is agreed. Run targeted `suites=m` after merge.
7. Prove #717/#719 with workflow/env evidence, then close them.
8. Run `suites=all` only after targeted STT and C are green.

## Useful Targeted Commands

```bash
gh workflow run alpha-live-verification.yml \
  --ref develop \
  -f suites=stt,v \
  -f require_deployed_sha_match=true \
  -f expected_backend_sha=<deployed-backend-sha>

gh workflow run alpha-live-verification.yml \
  --ref develop \
  -f suites=c-127 \
  -f require_deployed_sha_match=true \
  -f expected_backend_sha=<deployed-backend-sha>

gh workflow run alpha-live-verification.yml \
  --ref develop \
  -f suites=m \
  -f require_deployed_sha_match=true \
  -f expected_backend_sha=<deployed-backend-sha>
```
