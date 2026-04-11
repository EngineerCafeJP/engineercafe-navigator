# Qwen3-ASR 0.6B CPU on Cloud Run: Validation Report

Date: 2026-04-11
Scope: Validate whether Qwen3-ASR 0.6B CPU is actually incompatible with Cloud Run, or whether prior failures were caused by deploy/runtime configuration gaps.

## Executive Summary

The previous conclusion "Qwen3-ASR 0.6B CPU cannot run on Cloud Run" is not supported by the current evidence.

The stronger conclusion is:

- Qwen3-ASR 0.6B CPU is implemented in this repository and is plausibly deployable on Cloud Run CPU.
- The current production configuration does not support it yet.
- The observed failure mode is explained by deploy/runtime gaps, not by a known Cloud Run platform incompatibility.

For alpha-test timelines, keeping `STT_PROVIDER=vosk` and improving post-processing remains the fastest path.
For medium-term STT quality, Qwen should stay on the roadmap, but only behind a dedicated deployment plan.

## Final Judgement

### What is true

- Qwen 0.6B CPU is already implemented in backend code.
- Cloud Run currently serves Vosk, not Qwen.
- The current production Docker and Cloud Run settings are insufficient for Qwen runtime.
- A corrected Cloud Run deployment for Qwen is feasible enough to justify a targeted PoC.

### What is not proven

- Qwen 0.6B CPU has not yet been demonstrated end-to-end on this repository's current Cloud Run service.
- Current CI does not prove live model loading or real Cloud Run inference.
- The exact production memory headroom for stable inference under load remains unvalidated.

## Repository Findings

### Qwen provider exists in code

The repository includes a real Qwen STT path:

- `backend/agents/stt_agent.py`
  - `QwenSTTClient`
  - `Qwen06BCpuSTTClient`
  - `STTAgent(... stt_provider="qwen0.6b-cpu")`

The implementation uses:

- `Qwen/Qwen3-ASR-0.6B`
- `Qwen3ASRModel.from_pretrained(...)`
- CPU mode via `device="cpu"` in `Qwen06BCpuSTTClient`

This means the project is not missing the application-level integration.

### Dependency declaration exists, but runtime proof is weaker than originally stated

The repo declares:

- `backend/requirements.txt`: `qwen-asr>=0.0.6`
- `backend/pyproject.toml`: `qwen-asr>=0.0.6` in audio extras

However:

- The local Python environment used for this validation did not have `torch`, `transformers`, `accelerate`, or `qwen_asr` installed.
- The checked-in `backend/uv.lock` does not currently reflect these packages.

Therefore, the strict claim "production image definitely contains torch and transformers" is weaker than the original memo implied.

What we can say with confidence is:

- The production Docker build installs `requirements.txt`.
- `qwen-asr` is declared there.
- Qwen official package documentation states that `pip install -U qwen-asr` pulls required runtime dependencies for the transformers backend.

### Production Dockerfile is not Qwen-ready

Current production Docker characteristics:

- non-root user with `--home /nonexistent`
- no `HF_HOME` override
- no Qwen model download step
- Vosk models are downloaded at build time

This creates three concrete gaps for Qwen:

1. Hugging Face cache default path resolves under the user's home, which is problematic with `/nonexistent`.
2. Model weights are not bundled into the image.
3. If runtime download is attempted, Cloud Run filesystem writes consume instance memory.

## Cloud Run Findings

### Current live revision

The revision currently serving traffic is:

- `engineer-cafe-backend-00070-t98`

Verified configuration:

- `STT_PROVIDER=vosk`
- `TTS_PROVIDER=piper`
- `memory=2Gi`
- `cpu=2`
- `minScale=1`

This confirms that production is currently operating in Vosk mode, not Qwen mode.

### Latest service generation is partially misleading unless separated from ready traffic

The latest created revision is:

- `engineer-cafe-backend-00071-l5q`

It failed because the image tag `vosk-fix` was not found.

This matters because:

- the service object shows the latest template
- traffic is still pinned to the last ready revision

So any analysis of current production behavior must use the ready revision, not only the latest service template.

### Cloud Run platform constraints are compatible with the proposed fix

Cloud Run official docs confirm:

- filesystem writes are allowed
- the filesystem is in-memory
- writing files consumes instance memory
- 2 vCPU services can use up to 8 GiB memory

Therefore:

- `HF_HOME=/tmp/...` is a permission fix, not a memory fix
- pre-bundling model files is preferable to runtime download
- raising memory from 2 Gi to 4 Gi is operationally valid on the current 2 vCPU service shape

## GitHub Findings

### Relevant history

- Issue `#370` is closed after Qwen PoC work landed.
- PR `#408` is merged and introduced the Qwen 0.6B CPU provider.
- PR `#421` is merged and moved production defaults away from Qwen risk on Cloud Run.
- PR `#424` is open, CI is green, and it is independent of the Qwen deployment question.

### Why Issue #425 needed correction

The previous Issue `#425` body assumed:

- Qwen cannot run on Cloud Run
- Google Cloud STT also cannot run there

This is too broad.

More accurate wording is:

- Qwen is not currently deployed successfully on Cloud Run in this repo.
- Google STT path is also not currently deployment-ready in this repo.
- For near-term alpha support, Vosk plus post-processing is still the quickest operational choice.

## Official Documentation Findings

### Hugging Face

`HF_HOME` defaults to `~/.cache/huggingface`.

That interacts badly with:

- a non-root user
- home set to `/nonexistent`

### Qwen package docs

Qwen docs explicitly state:

- model weights are downloaded automatically at runtime when loading by model name
- if runtime environments cannot download weights, users should pre-download them to a local directory

That aligns directly with the required build-time bundling fix.

### Cloud Run docs

Cloud Run docs explicitly state:

- writable filesystem exists
- it is in-memory
- file writes count against instance memory
- instances exceeding memory limits are terminated

This supports the conclusion that 2 Gi is too tight for a runtime-downloaded 0.6B model path.

## Decision Analysis

### Is the original investigation direction valid?

Yes, with one correction.

Valid:

- Qwen failure was driven by environment mismatch.
- The main blockers are writable cache path, model availability, and memory sizing.
- Separate service deployment is the safer architecture.

Needs correction:

- Do not claim that Qwen is already proven on Cloud Run.
- Do not claim that current production image already guarantees all transitive runtime packages.

### Is Issue #425 still a valid short-term plan?

Yes, but for the right reason.

Short-term:

- keep `STT_PROVIDER=vosk`
- improve transcript quality with a post-processing step

Why:

- this is faster to ship
- production already runs Vosk
- PR #424 and alpha-test work do not need to wait for a Qwen deployment PoC

### Should Qwen be abandoned?

No.

The evidence does not support abandonment.
It supports moving Qwen into a dedicated deployment track with explicit resource and packaging changes.

## Required Changes for a Real Qwen Cloud Run PoC

1. Set `HF_HOME` before importing Hugging Face libraries.
2. Add a build-time Qwen model download step and pass a local model path at runtime.
3. Increase memory to at least `4Gi`.
4. Prefer a dedicated Cloud Run STT service over colocating with the main backend.
5. Add a real smoke test that performs one transcription after deploy.

## Recommended Project Direction

### Immediate

- Merge or continue `PR #424` independently.
- Update Issue `#425` to remove the incorrect "Qwen is impossible on Cloud Run" premise.
- Proceed with `Vosk -> LLM cleanup` only as the short-term alpha path.

### Next

- Open a focused Qwen deployment issue or subtask:
  - Dockerfile changes
  - model bundling
  - 4 Gi deploy target
  - dedicated service design
  - smoke test

### Longer-term

- Compare:
  - Vosk + LLM cleanup
  - Qwen 0.6B dedicated Cloud Run service
  - faster-whisper / whisper.cpp CPU alternatives

## Validation Performed

- Inspected local implementation and Dockerfile
- Inspected open issue / PR state on GitHub
- Inspected current Cloud Run service and live revision settings
- Checked official Hugging Face, Qwen, and Cloud Run docs
- Ran `pytest backend/tests/agents/test_stt_agent.py -q`
  - Result: `71 passed`

Note:

- This test pass validates provider-switching code paths and unit expectations.
- It does not prove live Qwen model loading in Cloud Run.

## References

- `backend/agents/stt_agent.py`
- `backend/Dockerfile`
- `backend/requirements.txt`
- `backend/pyproject.toml`
- `.github/workflows/ci.yml`
- `docs/STT-Migration-Guide-qwen3-asr.md`
- `docs/DEPLOYMENT.md`
- Issue `#370`
- Issue `#423`
- Issue `#425`
- PR `#408`
- PR `#421`
- PR `#424`
- Cloud Run docs: memory limits, container runtime contract
- Hugging Face docs: environment variables
- Qwen docs / PyPI: model loading and manual download guidance
