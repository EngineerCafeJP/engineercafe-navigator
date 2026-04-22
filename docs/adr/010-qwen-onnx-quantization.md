# ADR 010: Qwen3-ASR ONNX + INT4 quantization spike

Date: 2026-04-22

## Status

Proposed: **No-Go for Phase 2 ONNX/INT4 implementation as currently scoped**

## Context

Issue #491 proposed converting `Qwen/Qwen3-ASR-0.6B` from the current PyTorch CPU
runtime to ONNX Runtime with INT4 quantization. The target was to reduce live STT
latency from roughly p50 4.0s to p50 1.5s.

This ADR records Phase 1 spike results only. No runtime code was changed because:

- OpenCode is working on #487 in `backend/utils/language_processor.py` and
  `backend/workflows/main_workflow.py`.
- session-1771 is working in `backend/api/*`.
- The Phase 1 instruction explicitly required a Go/No-Go decision before Phase 2/3.

## Current implementation

The production STT path is `STT_PROVIDER=qwen-primary`.

In `backend/agents/stt_agent.py`, `qwen-primary` creates:

- `Qwen06BCpuSTTClient` as the primary recognizer.
- `LocalSTTClient` as a Vosk fallback.
- `QWEN_STT_TIMEOUT` defaulting to 10s.

Important behavior:

```python
qwen_result, vosk_result = await asyncio.gather(
    _run_qwen(), _run_vosk(), return_exceptions=True
)
```

This waits for both Qwen and Vosk to complete. It is not a "return the fastest valid
winner" race. If Qwen finishes quickly but Vosk is slow because of model load or CPU
contention, the request still waits for Vosk.

Also, Qwen success uses `QwenSTTClient.transcribe()`, whose Japanese LLM correction is
controlled by `STT_QWEN_POSTPROCESS_ENABLED`, not by `STT_LLM_POSTPROCESS`.
`STT_LLM_POSTPROCESS=true` currently applies to the Vosk fallback branch and the
Vosk-only provider path, not to successful Qwen-primary results.

## Phase 1 environment

Worktree:

- `/tmp/engineer-cafe-navigator2025-work5-491`
- Base: `origin/develop` at `b5a5299c6`

Spike dependencies installed into the local Work5 `.venv` only:

- `qwen-asr==0.0.6`
- `torch==2.11.0`
- `transformers==4.57.6`
- `optimum==2.1.0`
- `optimum-onnx==0.1.0`
- `onnx==1.21.0`
- `onnxruntime==1.24.4`

These dependencies were not added to project files during Phase 1.

## ONNX export feasibility

Command:

```bash
uv run optimum-cli export onnx \
  --model Qwen/Qwen3-ASR-0.6B \
  --task automatic-speech-recognition \
  /tmp/qwen-asr-onnx-spike-fp32
```

Result: **failed**.

Error:

```text
ValueError: The checkpoint you are trying to load has model type `qwen3_asr`
but Transformers does not recognize this architecture.
```

Root cause:

- `qwen_asr.inference.qwen3_asr` registers `qwen3_asr` with Transformers at import time:
  - `AutoConfig.register("qwen3_asr", Qwen3ASRConfig)`
  - `AutoModel.register(Qwen3ASRConfig, Qwen3ASRForConditionalGeneration)`
  - `AutoProcessor.register(Qwen3ASRConfig, Qwen3ASRProcessor)`
- The standalone `optimum-cli` path calls `AutoConfig.from_pretrained()` before importing
  the `qwen_asr` package, so the architecture is unknown.

After importing `qwen_asr.inference.qwen3_asr`, local Python can resolve the config and
model mapping:

```text
Qwen3ASRConfig
model_type=qwen3_asr
AutoModel -> Qwen3ASRForConditionalGeneration
```

However, this does not make standard Optimum export automatically usable.

## Custom export feasibility

`Qwen3ASRForConditionalGeneration.forward` is not implemented as a normal model forward;
the class inherits the default `_forward_unimplemented`.

The inference path is:

```python
inputs = processor(text=sub_text, audio=sub_wavs, return_tensors="pt", padding=True)
text_ids = model.generate(**inputs, max_new_tokens=max_new_tokens)
decoded = processor.batch_decode(text_ids.sequences[:, inputs["input_ids"].shape[1]:])
```

This means Qwen3-ASR is a generation model, not a simple encoder-only ASR model. A
production ONNX path would need to export and serve the autoregressive generation graph,
including decoder cache handling. That is closer to building a custom Optimum ORT model
integration than running a one-command export.

INT4 quantization also depends on having a valid ONNX graph first. Since FP32 ONNX export
did not succeed, INT4 was not attempted.

## Local PyTorch baseline

Sample:

- `frontend/e2e/fixtures/voice/sample.wav`
- sample rate: 16kHz
- duration: 1.811s
- expected transcript: "Tell me about Engineer Cafe."

Command shape:

```python
model = Qwen3ASRModel.from_pretrained(
    "Qwen/Qwen3-ASR-0.6B",
    torch_dtype=torch.float32,
    device_map="cpu",
    low_cpu_mem_usage=True,
    max_new_tokens=256,
)
model.transcribe(audio=(pcm, 16000), language="English")
```

Result on local Apple Silicon environment:

| Metric | Result |
| --- | ---: |
| Model load | 5.348s |
| Iteration 1 | 0.601s |
| Iteration 2 | 0.490s |
| Iteration 3 | 0.293s |
| Iteration 4 | 0.294s |
| Iteration 5 | 0.293s |
| Warm p50 | 0.294s |
| Max | 0.601s |
| Transcript | `Tell me about Engineer Cafe.` |

Interpretation:

- Qwen3-ASR 0.6B PyTorch itself can be fast once warm.
- The observed Cloud Run STT p50 around 4s is unlikely to be explained by Qwen PyTorch
  inference alone.
- The current `qwen-primary` implementation waits for Vosk as well as Qwen, so Vosk model
  load / CPU contention can dominate latency even when Qwen succeeds quickly.

## Live Piper Plus TTS -> STT accuracy check

Command:

```bash
LIVE_BACKEND_URL=https://engineer-cafe-backend-639959525777.asia-northeast1.run.app \
LIVE_BACKEND_API_KEY="$(gcloud secrets versions access latest \
  --secret=API_SECRET_KEY --project=aipartner-426616)" \
uv run pytest --run-e2e tests/e2e/test_stt_japanese_accuracy.py -v -m e2e --no-header
```

The test synthesizes Japanese audio through live `/api/voice` TTS, which uses Piper Plus
in the current Cloud Run configuration, then sends that audio back through live STT.

Per-sample result from the first parametrized pass:

| Sample | Result | Observed transcript |
| --- | --- | --- |
| `proper_noun_cafe` | failed | `現地 に た` |
| `coworking_katakana` | passed | n/a |
| `business_hours` | passed | n/a |
| `event_info` | passed | n/a |
| `wifi_alphanumeric` | failed | `はい 日 の パスワード は あり ます か` |
| `reception_procedure` | failed | `駆けつけました。ご確認ください。` |
| `community_manager` | failed | `今年 に か な 姉 じゃあ に 澤田 し たい` |
| `meeting_reserve` | failed | `エンジニアカフェは予約できますか？` |
| `fukuoka_city` | passed | n/a |
| `basement_space` | failed | `下の子は、エンジニアカフェ(Engineer Cafe)にいます。` |

Effective first-pass accuracy: **4/10 = 40%**.

The aggregate test then hit the existing `/api/voice` rate limit:

```text
429 {"error":"Rate limit exceeded: 20 per 1 minute"}
```

Interpretation:

- The live Piper Plus round-trip currently exposes accuracy regressions independent of
  ONNX speed work.
- The aggregate test duplicates the 10 TTS+STT calls after the parametrized test, causing
  20+ requests/minute and triggering the `/api/voice` rate limit. This validates follow-up
  #502 as a real test-design issue.

## Decision

Do **not** proceed to Phase 2 ONNX/INT4 implementation yet.

Reasons:

1. Standard Optimum ONNX export fails because `qwen3_asr` is not registered unless the
   `qwen_asr` package is imported first.
2. The model does not expose a normal `forward`; inference is through `generate()`.
   Custom ONNX export would require a non-trivial autoregressive generation integration.
3. Local PyTorch warm inference is already sub-second on the sample fixture. That suggests
   the current Cloud Run p50 is dominated by orchestration/fallback/postprocess behavior,
   not purely by PyTorch compute.
4. Live Piper Plus TTS -> STT accuracy is currently only 4/10 on the first pass, so
   optimizing inference speed alone will not make the user-facing STT path alpha-ready.

## Recommended next step

Pivot #491 from "ONNX/INT4 first" to "remove avoidable qwen-primary latency and accuracy
regression first":

1. Change `qwen-primary` from `asyncio.gather()` to a safe winner-race:
   - return Qwen immediately if it succeeds within timeout;
   - keep Vosk only as fallback when Qwen fails or times out;
   - do not wait for Vosk after Qwen success.
2. Align post-processing flags:
   - either set `STT_QWEN_POSTPROCESS_ENABLED=true` in Cloud Run, or make
     `STT_LLM_POSTPROCESS=true` also enable Qwen success-path post-processing.
3. Fix #502 before using the 10-sample live test as a release gate:
   - avoid running the same 10 TTS+STT calls twice inside one minute;
   - cache synthesized audio or make the aggregate test reuse per-sample results.
4. Re-measure live STT p50/p95 after the race fix and post-process alignment.
5. Revisit ONNX only if Qwen-only p50 remains above target.

## Go / No-Go

No-Go for ONNX/INT4 Phase 2 as scoped.

Go for a smaller backend optimization spike:

- implement qwen-primary winner-race behind a feature flag;
- verify Piper Plus TTS -> STT accuracy after Qwen post-process alignment;
- only then decide whether ONNX export is still needed.

## Related

- #491: Qwen3-ASR ONNX Runtime + INT4 quantization
- #484: OSS release preparation
- #502: STT test rate-limit follow-up
- #480 / #499: STT post-process and live Japanese accuracy suite
- #478 / #498: MP3 encoding event-loop blocker removal
