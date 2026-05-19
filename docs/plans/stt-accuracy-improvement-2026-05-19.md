# STT Accuracy Improvement Spike (2026-05-19)

## Scope

Issue: [#909](https://github.com/EngineerCafeJP/engineercafe-navigator/issues/909)

This is a research spike artifact, not a production STT implementation. It reads the current repo state and proposes how to evaluate Options A-E from #909 against the RC-3 failure:

> User said: `2階の会議室について`
> Qwen 0.6B transcript became: `エンジニアカフェであるイベントについて教えて`
> Downstream route became: `event`

The failure is not a small typo. It is catastrophic semantic drift from a short facility/meeting-room query to an event query. A viable fix must preserve route-critical entities, not only improve average character similarity.

## Local Baseline Readout

- Production voice stack is `STT_PROVIDER=qwen-primary`: Qwen3-ASR 0.6B CPU primary with Vosk fallback hedge. See `docs/architecture/stt-tts-stack-and-slide-audio-2026-05-09.md` and `docs/adr/007-stt-parallel-architecture.md`.
- `backend/api/voice.py` decodes `/api/voice` `speech_to_text`, calls `STTAgent.speech_to_text()`, and emits `stt_request_complete`.
- `backend/agents/stt_agent.py` now acts as a facade. For `qwen-primary`, it builds `Qwen06BCpuSTTClient`, `LocalSTTClient` fallback, timeout, hedge, grace, and latency-budget settings.
- `backend/agents/stt/qwen_primary.py` implements the Qwen-first / Vosk-hedged winner flow and logs `stt_qwen_*`, `stt_vosk_*`, and `stt_winner`.
- `backend/agents/stt/qwen_client.py` calls `Qwen3ASRModel.transcribe(audio=(pcm, sample_rate), language=...)`. The current local code does not pass vocabulary hints or grammar to Qwen.
- `backend/agents/stt_agent.py` can resolve custom grammar, but that path is used for Vosk-style grammar only. Qwen success bypasses `_resolve_grammar()`.
- `backend/agents/stt/postprocess.py` already has narrow deterministic Qwen corrections and optional Qwen LLM postprocess. The option is `STT_QWEN_POSTPROCESS_ENABLED=true`, not `STT_LLM_POSTPROCESS=true`.
- `STT_LLM_POSTPROCESS=true` applies to Vosk-only or Vosk-fallback postprocessing. It does not by itself correct a successful Qwen transcript.
- `backend/data/stt_vocabulary.json` currently has only six terms: `エンジニアカフェ`, `博多`, `天神`, `コワーキングスペース`, `ミートアップ`, `Wi-Fi`. It does not include `2階会議室`, `メインホール`, `集中スペース`, `Maker'sスペース`, `ミーティングスペース`, `防音室`, or `サイノカフェ`.
- ADR 016 records that post-alpha STT latency regressed again in production: Cloud Run revision `00192-bzt` had `stt_winner` p50 `6877ms`, p90 `9000ms`, max `10006ms`.
- ADR 010 recorded a live Japanese TTS->STT accuracy run where only 4/10 samples passed, with failures around proper nouns, Wi-Fi, reception, meeting space, and basement space.
- Current `STTAgent.allowed_providers` excludes `google`; Google STT references in older docs are legacy and no longer represent the current dispatch path.

## Option Tradeoff Table

| Option | Accuracy expectation | Latency expectation | Cost | OSS posture | Repo fit | Main risks | Spike verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A. Qwen vocabulary biasing | Potentially good for known facility names if Qwen API supports hints. Best match for RC-3 if the hint affects decoding before hallucinated event text is produced. | Near-zero incremental latency if native decoder/prompt biasing exists. | Low; no new provider or model. | Strong if Qwen remains the only STT model. | Not wired today. Current Qwen call passes only `audio` and `language`; local `qwen_asr` package is not installed in this checkout, so signature must be verified in an isolated env. | Qwen may not expose a safe hint parameter; prompt-like hints may be ignored or may increase hallucination. Current vocab is too sparse. | First spike check, but not enough to plan as implementation until API support is confirmed. |
| B. Larger Qwen model (1.7B / 3B) | May improve Japanese/noisy short utterances, but not guaranteed to fix facility-vs-event drift. Larger generative ASR can still confidently hallucinate under noise. | Likely worse on Cloud Run CPU. 0.6B already has 6-10s live tails; 1.7B/3B can push p95 beyond the `/api/voice` UX budget without GPU or larger instances. | Medium to high Cloud Run cost from memory/CPU/GPU and cold-start footprint. | Good if using Qwen Apache-2.0-compatible weights, but artifact provenance must be recorded. | `STT_PROVIDER=qwen` supports `QWEN_STT_MODEL_VARIANT=1.7b`; production `qwen-primary` is hardwired to 0.6B. No 3B variant is represented in local code. | Larger container/model, slower startup, higher steady cost, uncertain accuracy win. | Do not implement first. Only evaluate 1.7B if A/C fail and a preview environment can absorb the latency/cost. Treat 3B as unsupported until upstream and infra are verified. |
| C. STT postprocess with entity hints | Good for phonetic/proper-noun repair and route-critical normalization. Weak when the transcript has already changed intent with no phonetic evidence, as in RC-3. | Deterministic corrections are negligible. LLM postprocess adds up to the OpenRouter call timeout (`3.0s`) on Japanese Qwen requests. | Low for deterministic corrections; metered LLM cost if `STT_QWEN_POSTPROCESS_ENABLED=true`. | Mixed: deterministic path is OSS-friendly; LLM path depends on OpenRouter/provider terms. | Best current repo fit. Existing Qwen postprocess reads `backend/data/stt_vocabulary.json`, logs `stt_qwen_postprocess_complete`, and is opt-in by env. | Wrong knob risk: `STT_LLM_POSTPROCESS=true` does not fix Qwen success. LLM must not rewrite a wrong event transcript into a facility query without evidence. Vocabulary must be expanded first. | Recommended first field experiment together with A. It is reversible and already observable. It should not be declared sufficient until RC-3-like clips pass. |
| D. Whisper API / Google Cloud STT migration (paid) | Highest likely accuracy for noisy iPhone kiosk audio and short Japanese utterances, especially if using a current managed STT model. | Network + provider latency. Could be lower than current Qwen tail or worse under API contention; must measure from Asia/Japan deployment path. | High/variable. Exact vendor pricing must be rechecked on implementation date. | Weak. Adds SaaS dependency, API keys, provider terms, and privacy review. | Not currently wired. Current STT provider dispatch would need a new provider or reintroduction of a paid provider path. | Vendor lock-in, recurring cost, data handling review, outage mode, and contradiction with OSS-first posture. | Keep as an escalation path if A/C cannot eliminate catastrophic drift. Use preview-only spike before any production decision. |
| E. Two-stage STT (Qwen fast + paid accuracy) | Best practical accuracy if the second stage runs on short/risky/route-ambiguous utterances and can arbitrate catastrophic drift. | Always-on consensus is too slow. Selective escalation can preserve fast Qwen path for easy queries and spend latency only on risky cases. | Medium to high but controllable if paid STT is invoked selectively. | Mixed. Qwen remains OSS baseline, but final accuracy path depends on paid STT. | Conceptually matches existing hedge/winner telemetry, but current hedge is Qwen+Vosk, not Qwen+paid consensus. Needs new provider result schema and decision policy. | Highest implementation complexity. Needs careful arbitration so paid STT does not become an always-on dependency or mask routing bugs. | Best fallback design if terisuke accepts paid STT. Do not start here until A/C fail on the 30-query corpus. |

## Evaluation Plan

The acceptance test should score ASR quality and downstream routing together. Character similarity alone would not catch RC-3 if the transcript is fluent but semantically wrong.

### Test Setup

1. Record the 30 utterances below on the target device path from #909: iPhone Safari + Vercel preview + kiosk microphone/noise position.
2. Save one WAV/WebM clip per query and a manifest compatible with `backend/evaluation/datasets/onsite_voice_live_manifest.example.json`.
3. For the four RC-3 meeting-room cases, record three takes each if time permits. The summary should report both 30-query aggregate and RC-critical pass/fail.
4. Run each candidate in a preview/backend branch or isolated service. Do not toggle production defaults during the spike.
5. For each clip and option, call `/api/voice` `speech_to_text`, then `/api/chat` with the returned transcript.
6. Collect `stt_request_complete`, `stt_qwen_runtime_complete`, `stt_qwen_postprocess_complete`, `stt_vosk_runtime_complete`, and `stt_winner` logs by `stt_trace_id` where available.
7. Record provider, transcript, latency, postprocess changed flag, route, and answer source.

### Score Fields

| Field | Pass condition |
| --- | --- |
| `entity_preserved` | All critical terms or accepted alternatives appear in the transcript. |
| `catastrophic_drift` | Fail if transcript introduces a wrong intent-bearing entity such as `イベント` for meeting-room cases or drops the expected route entity. |
| `route_ok` | `/api/chat` route is in the expected route group. RC-3 cases fail if routed to `event`. |
| `cer_or_similarity` | Normalized character similarity against expected text, using `SequenceMatcher` as current tests do; target >= 0.70 for noisy live audio. |
| `latency_ok` | STT p95 <= 10s for spike comparability; preferred p50 <= 3s and no single RC-critical timeout. |
| `cost_event` | Track paid STT calls, LLM postprocess calls, and Cloud Run model memory/CPU/GPU setting. |

### Option-Specific Runs

- Baseline: current `qwen-primary`, current vocabulary, `STT_QWEN_POSTPROCESS_ENABLED=false`.
- Option A: same as baseline plus native Qwen vocabulary/hint if the `qwen-asr` package exposes it. If not supported, mark A as "API unsupported" rather than emulating production behavior with an untrusted prompt.
- Option B: `QWEN_STT_MODEL_VARIANT=1.7b` under the `qwen` provider or a preview-only `qwen-primary` variant. 3B requires a separate upstream/support check because local code does not know it.
- Option C: expand vocabulary and run `STT_QWEN_POSTPROCESS_ENABLED=true`; optionally run deterministic-only and LLM-enabled variants separately.
- Option D: preview-only paid provider, with exact pricing/model/API terms verified on the implementation date.
- Option E: preview-only Qwen+paid consensus, with paid STT invoked only for short, low-confidence, postprocess-changed, or route-ambiguous transcripts.

## 30-Query Kiosk Corpus

`expected_route` may be a route group when the current app can reasonably answer through either facility or business information. RC-3 success is "not event" plus correct meeting-room entity preservation.

| ID | Lang | Expected route | Utterance | Critical terms / forbidden drift |
| --- | --- | --- | --- | --- |
| STT-RC3-JA-01 | ja | facility\|business_info | 2階の会議室について教えてください。 | Must keep `2階`, `会議室`; fail if `イベント` dominates. |
| STT-RC3-JA-02 | ja | facility\|business_info | 二階の貸し会議室は予約できますか。 | Must keep `二階/2階`, `会議室`, `予約`; fail if event route. |
| STT-RC3-JA-03 | ja | facility\|business_info | 2階会議室の利用料金を知りたいです。 | Must keep `2階`, `会議室`, `料金`; fail if event route. |
| STT-RC3-JA-04 | ja | facility\|business_info | 会議室はエンジニアカフェの施設ですか。 | Must keep `会議室`, `エンジニアカフェ`; fail if event route. |
| STT-FAC-JA-05 | ja | facility | メインホールはどんなスペースですか。 | Must keep `メインホール`. |
| STT-FAC-JA-06 | ja | facility | 地下の集中スペースで電話できますか。 | Must keep `地下`, `集中スペース`, `電話`. |
| STT-FAC-JA-07 | ja | facility | 地下のMaker'sスペースでは何ができますか。 | Must keep `地下`, `Maker's/Makers`, `スペース`. |
| STT-FAC-JA-08 | ja | facility | ミーティングスペースを使いたいです。 | Must keep `ミーティングスペース`. |
| STT-FAC-JA-09 | ja | facility | 防音室は予約できますか。 | Must keep `防音室`, `予約`. |
| STT-FAC-JA-10 | ja | facility\|business_info | カフェスペースで作業できますか。 | Must not confuse `カフェスペース` with only event info. |
| STT-FAC-JA-11 | ja | facility | Wi-FiのSSIDとパスワードの確認方法を教えてください。 | Must keep `Wi-Fi/ワイファイ`, `SSID`, `パスワード`. |
| STT-FAC-JA-12 | ja | facility | 電源が使える席はありますか。 | Must keep `電源`, `席`. |
| STT-FAC-JA-13 | ja | facility | オンライン会議をしたいので静かな席はありますか。 | Must keep `オンライン会議`, `席`. |
| STT-FAC-JA-14 | ja | facility | 駐車場や駐輪場はありますか。 | Must keep `駐車場`, `駐輪場`. |
| STT-RECV-JA-15 | ja | business_info | 初めて来ました。受付をお願いします。 | Must keep `初めて`, `受付`. |
| STT-RECV-JA-16 | ja | business_info | 以前登録しています。今日は再受付だけで大丈夫ですか。 | Must keep `登録`, `再受付`. |
| STT-RECV-JA-17 | ja | business_info | 会員登録フォームのQRコードはどこですか。 | Must keep `会員登録`, `QRコード`. |
| STT-BIZ-JA-18 | ja | business_info | 今日の開館時間と最終受付を教えてください。 | Must keep `開館時間`, `最終受付`. |
| STT-BIZ-JA-19 | ja | business_info | 利用料金はいくらですか。 | Must keep `利用料金`. |
| STT-BIZ-JA-20 | ja | business_info | 予約なしでコワーキングスペースを使えますか。 | Must keep `予約なし`, `コワーキングスペース`. |
| STT-EVT-JA-21 | ja | event | 今日開催されるイベントを教えてください。 | Must keep `イベント`; fail if overcorrected to facility. |
| STT-EVT-JA-22 | ja | event | 今週の勉強会スケジュールを知りたいです。 | Must keep `勉強会`, `スケジュール`. |
| STT-EVT-JA-23 | ja | event | 初心者向けのAIイベントはありますか。 | Must keep `初心者`, `AI`, `イベント`. |
| STT-EVT-JA-24 | ja | event | connpassで申し込むイベントを確認してください。 | Must keep `connpass`, `イベント`. |
| STT-SAINO-JA-25 | ja | business_info\|facility | サイノカフェの営業時間を教えてください。 | Must keep `サイノカフェ`, `営業時間`; do not answer Engineer Cafe hours only. |
| STT-SAINO-JA-26 | ja | business_info\|facility | サイノカフェでコーヒーを飲めますか。 | Must keep `サイノカフェ`, `コーヒー`. |
| STT-FAC-EN-27 | en | facility\|business_info | Tell me about the second-floor meeting rooms. | Must keep `second-floor`, `meeting rooms`; fail if event route. |
| STT-FAC-EN-28 | en | facility\|business_info | Can I use the main hall as a coworking space? | Must keep `main hall`, `coworking`. |
| STT-FAC-EN-29 | en | facility | How can I check the Wi-Fi SSID and password? | Must keep `Wi-Fi`, `SSID`, `password`. |
| STT-EVT-EN-30 | en | event | What events are happening this week at Engineer Cafe? | Must keep `events`, `this week`, `Engineer Cafe`. |

## Recommendation

Recommended path:

1. Run A/C together first on a preview service.
   - A has the best theoretical fit for RC-3 because biasing can influence decoding before the wrong event transcript is emitted.
   - C has the best local implementation fit because Qwen postprocess, vocabulary loading, and postprocess telemetry already exist.
   - Before testing C, expand `backend/data/stt_vocabulary.json` or the candidate vocabulary source with the 30-query critical terms. The current six-term vocabulary is not enough.
2. Do not start with Option B.
   - 1.7B/3B model size is likely to worsen the already-visible Cloud Run tail unless GPU or larger instances are approved.
   - Larger Qwen should only be tested after A/C fail and after the team accepts higher startup/runtime cost.
3. If A is unsupported and C cannot recover RC-3, escalate to paid STT.
   - Prefer E over D for production architecture if terisuke accepts paid STT, because selective paid arbitration can preserve the OSS Qwen baseline and control cost.
   - Use D-only as the fastest emergency route if accuracy is the sole blocker and OSS posture is explicitly deprioritized.

Do not ship any option unless `STT-RC3-JA-01` through `STT-RC3-JA-04` pass without event routing and the event-control cases `STT-EVT-JA-21` through `STT-EVT-JA-24` still route to event.

## Follow-Up Issue Plan

### FU-43A: Qwen vocabulary hint API verification

Goal: determine whether `qwen-asr>=0.0.6` supports native vocabulary or phrase hints for ASR decoding.

Acceptance:

- Inspect package signature and upstream docs in an isolated env.
- If supported, implement a preview-only env/config path for Qwen hints.
- If unsupported, document no-go and do not emulate hints with an unverified prompt.
- Report latency and transcript deltas for the 30-query corpus.

### FU-43B: Qwen postprocess + domain vocabulary preview evaluation

Goal: test the lowest-risk local mitigation.

Acceptance:

- Expand the candidate STT vocabulary with RC-3 and kiosk facility terms.
- Run `STT_QWEN_POSTPROCESS_ENABLED=true` in preview only.
- Measure 30-query entity preservation, route correctness, postprocess changed rate, LLM call latency, and failure fallback behavior.
- Confirm whether `STT_LLM_POSTPROCESS` remains Vosk-only in docs/runbooks to avoid the wrong knob being used again.

### FU-43C: Paid STT provider preview spike

Goal: compare managed STT accuracy against current Qwen on the same audio corpus.

Acceptance:

- Verify current provider pricing, model availability, data handling, and region/latency on the implementation date.
- Add a preview-only provider path without changing production default.
- Measure the same 30-query corpus plus RC-critical repeats.
- Record per-minute cost estimate and p50/p95 latency.

### FU-43D: Selective two-stage STT consensus design

Goal: design Option E only if paid STT proves materially better than Qwen on RC-critical cases.

Acceptance:

- Define escalation rules: short utterance, low route confidence, suspicious Qwen transcript, postprocess changed, or facility/event ambiguity.
- Preserve fast Qwen return for safe transcripts.
- Emit structured logs for both STT candidates and final arbitration reason.
- Provide a rollback flag to disable paid arbitration immediately.

### FU-43E: Kiosk audio corpus and repeatable accuracy harness

Goal: make the 30-query STT matrix reusable.

Acceptance:

- Add a manifest for recorded kiosk clips with expected route, critical terms, and forbidden drift.
- Produce a script/report that runs STT, then `/api/chat`, and outputs per-case markdown/CSV.
- Include rate-limit spacing so the suite does not reproduce the ADR 010 `429` failure mode.
- Keep audio provenance and consent notes with the fixture manifest before committing real recordings.

## Terisuke Confirmation Needed

- Whether paid STT is acceptable as a preview-only comparison.
- Whether paid STT can be used selectively in production if A/C fail.
- Whether an added 1-3s postprocess cost is acceptable for Japanese Qwen requests during a field trial.
- Whether the 30-query corpus should be recorded on iPhone Safari only or also on the final kiosk microphone/M5Stack path.
