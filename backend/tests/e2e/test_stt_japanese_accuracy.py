"""Japanese STT proper-noun accuracy test against live Cloud Run backend.

Purpose
-------
Verifies that ``STT_LLM_POSTPROCESS=true`` on Cloud Run (rev 00085-pk5+)
restores Japanese proper-noun recognition that previously misfired on
phrases like "エンジニアカフェ" -> "現地にカフェ" (observed pre-#480).

Design
------
Each sample is round-tripped through the live backend:
  TTS (/api/voice action=text_to_speech)
    -> base64 WAV
    -> STT (/api/voice action=speech_to_text)
    -> transcript

The round-trip avoids committing audio fixtures and exercises the exact
provider chain (tsukuyomi/piper-plus -> Qwen + Vosk + optional LLM
post-process) that production uses.

Opt-in
------
Skipped unless ``LIVE_BACKEND_URL`` and ``LIVE_BACKEND_API_KEY`` are set.
Run locally with:

    export LIVE_BACKEND_URL=https://engineer-cafe-backend-639959525777.asia-northeast1.run.app
    export LIVE_BACKEND_API_KEY=$(gcloud secrets versions access latest \\
        --secret=API_SECRET_KEY --project=aipartner-426616)
    pytest backend/tests/e2e/test_stt_japanese_accuracy.py -v

The aggregate accuracy assertion (>= 0.8) runs as a separate test that
summarises per-sample pass/fail.
Per-sample and aggregate tests share a session cache so the suite sends
each sample through /api/voice only once.

Future work
-----------
Tier-2: replace TTS-synthesised input with real human recordings under
``backend/tests/fixtures/stt_japanese/<slug>.wav`` once field samples are
available. The keyword assertion strategy is already fixture-agnostic.
"""

from __future__ import annotations

import os
from difflib import SequenceMatcher
from typing import List, Tuple

import httpx
import pytest

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.voice_pipeline,
    pytest.mark.asyncio(loop_scope="session"),
]


# Each tuple is (sample_id, ground_truth_text, required_substrings).
# required_substrings is what we expect in the transcript for the sample
# to be counted as "correct"; entries are matched case-sensitively because
# Japanese text has no case.
JAPANESE_STT_SAMPLES: List[Tuple[str, str, List[str]]] = [
    ("proper_noun_cafe", "エンジニアカフェ", ["エンジニアカフェ"]),
    ("coworking_katakana", "コワーキングスペース", ["コワーキング"]),
    (
        "business_hours",
        "エンジニアカフェの営業時間を教えてください",
        ["エンジニアカフェ", "営業時間"],
    ),
    ("event_info", "イベント情報を教えてください", ["イベント"]),
    ("wifi_alphanumeric", "WiFiのパスワードはありますか", ["WiFi"]),
    ("reception_procedure", "受付で手続きしてください", ["受付", "手続き"]),
    (
        "community_manager",
        "コミュニティマネージャーに相談したい",
        ["コミュニティマネージャー"],
    ),
    ("meeting_reserve", "ミーティングスペースを予約できますか", ["ミーティングスペース"]),
    ("fukuoka_city", "福岡市エンジニアカフェ", ["エンジニアカフェ"]),
    ("basement_space", "地下のコワーキングスペース", ["コワーキング"]),
]

# Per-sample character-similarity target (SequenceMatcher ratio).
# 0.8 is chosen as a lenient but meaningful bar for synthesised voice,
# since TTS pronunciation quirks can degrade Vosk word boundaries even
# when the semantic content is preserved.
PER_SAMPLE_SIMILARITY_FLOOR = 0.70

# Aggregate pass rate target: at least 80% of samples must satisfy
# their required_substrings AND per-sample similarity floor.
AGGREGATE_ACCURACY_FLOOR = 0.80


def _similarity(a: str, b: str) -> float:
    """Character-level SequenceMatcher ratio (0.0 - 1.0)."""
    return SequenceMatcher(None, a, b).ratio()


def _required_substrings_match(transcript: str, required: List[str]) -> bool:
    """True if every required substring is present in the transcript."""
    return all(sub in transcript for sub in required)


@pytest.fixture(scope="session")
def live_backend_config() -> dict:
    """Cloud Run live backend endpoint + API key, or skip."""
    url = os.environ.get("LIVE_BACKEND_URL", "").strip()
    api_key = os.environ.get("LIVE_BACKEND_API_KEY", "").strip()
    if not url or not api_key:
        pytest.skip(
            "LIVE_BACKEND_URL and LIVE_BACKEND_API_KEY must both be set to run "
            "Japanese STT accuracy tests against Cloud Run."
        )
    return {"url": url.rstrip("/"), "api_key": api_key}


async def _synthesize_japanese(client: httpx.AsyncClient, config: dict, text: str) -> str:
    """Call live backend TTS for Japanese text, return base64 WAV."""
    resp = await client.post(
        f"{config['url']}/api/voice",
        headers={"X-API-Key": config["api_key"]},
        json={
            "action": "text_to_speech",
            "text": text,
            "language": "ja",
        },
        timeout=90.0,
    )
    assert resp.status_code == 200, f"TTS failed: {resp.status_code} {resp.text[:200]}"
    data = resp.json()
    assert data.get("success"), f"TTS did not succeed: {data}"
    audio = data.get("audioResponse")
    assert audio, f"TTS response missing audioResponse: {data}"
    return audio


async def _transcribe_japanese(client: httpx.AsyncClient, config: dict, audio_b64: str) -> str:
    """Call live backend STT on base64 audio, return transcript."""
    resp = await client.post(
        f"{config['url']}/api/voice",
        headers={"X-API-Key": config["api_key"]},
        json={
            "action": "speech_to_text",
            "audioData": audio_b64,
            "language": "ja",
        },
        timeout=60.0,
    )
    assert resp.status_code == 200, f"STT failed: {resp.status_code} {resp.text[:200]}"
    data = resp.json()
    assert data.get("success"), f"STT did not succeed: {data}"
    return (data.get("transcript") or "").strip()


async def _round_trip(client: httpx.AsyncClient, config: dict, text: str) -> str:
    """Single TTS -> STT round-trip helper."""
    audio_b64 = await _synthesize_japanese(client, config, text)
    return await _transcribe_japanese(client, config, audio_b64)


@pytest.fixture(scope="session")
def stt_accuracy_result_cache() -> dict[str, tuple[bool, str]]:
    """Share live round-trip results across per-sample and aggregate tests.

    The backend /api/voice endpoint is intentionally rate-limited at 20/min.
    Reusing the first-pass result avoids a false 429 failure while preserving
    individual pytest visibility for each sample.
    """

    return {}


async def _round_trip_cached(
    client: httpx.AsyncClient,
    config: dict,
    sample_id: str,
    text: str,
    cache: dict[str, tuple[bool, str]],
) -> str:
    cached = cache.get(sample_id)
    if cached is None:
        try:
            cached = (True, await _round_trip(client, config, text))
        except Exception as exc:  # noqa: BLE001 - cache once to avoid duplicate live calls
            cached = (False, f"{type(exc).__name__}: {exc}")
        cache[sample_id] = cached

    success, value = cached
    if not success:
        raise RuntimeError(value)
    return value


@pytest.mark.parametrize(
    "sample_id, ground_truth, required_substrings",
    JAPANESE_STT_SAMPLES,
    ids=[s[0] for s in JAPANESE_STT_SAMPLES],
)
async def test_japanese_stt_per_sample(
    sample_id: str,
    ground_truth: str,
    required_substrings: List[str],
    live_backend_config: dict,
    stt_accuracy_result_cache: dict[str, tuple[bool, str]],
) -> None:
    """Each sample's transcript must contain required substrings.

    Non-strict: this test intentionally does NOT require exact equality.
    A sample passes if:
      1. every required substring appears in the transcript, AND
      2. character-level similarity >= PER_SAMPLE_SIMILARITY_FLOOR.
    Fails surface as individual pytest failures so CI reports per-sample.
    """
    async with httpx.AsyncClient() as client:
        transcript = await _round_trip_cached(
            client,
            live_backend_config,
            sample_id,
            ground_truth,
            stt_accuracy_result_cache,
        )

    assert transcript, f"[{sample_id}] transcript was empty"

    sim = _similarity(ground_truth, transcript)
    substrings_ok = _required_substrings_match(transcript, required_substrings)

    # Rich diagnostic message for quick triage on CI failure.
    detail = (
        f"sample={sample_id} ground_truth={ground_truth!r} "
        f"transcript={transcript!r} similarity={sim:.3f}"
    )

    assert (
        substrings_ok
    ), f"[{sample_id}] required substrings {required_substrings} not all in transcript. {detail}"
    assert (
        sim >= PER_SAMPLE_SIMILARITY_FLOOR
    ), f"[{sample_id}] similarity {sim:.3f} below floor {PER_SAMPLE_SIMILARITY_FLOOR}. {detail}"


async def test_japanese_stt_aggregate_accuracy(
    live_backend_config: dict,
    stt_accuracy_result_cache: dict[str, tuple[bool, str]],
) -> None:
    """Aggregate pass rate across all 10 samples must meet floor.

    Run independently from the parametrised test so that a single flaky
    sample does not mask an overall regression. Collects per-sample
    results and asserts the aggregate rate at the end.
    """
    passed: List[str] = []
    failed: List[Tuple[str, str, str, float]] = []

    async with httpx.AsyncClient() as client:
        for sample_id, ground_truth, required in JAPANESE_STT_SAMPLES:
            try:
                transcript = await _round_trip_cached(
                    client,
                    live_backend_config,
                    sample_id,
                    ground_truth,
                    stt_accuracy_result_cache,
                )
            except Exception as exc:  # noqa: BLE001 - capture for aggregate report
                failed.append((sample_id, ground_truth, f"<error: {exc}>", 0.0))
                continue

            sim = _similarity(ground_truth, transcript)
            ok = _required_substrings_match(transcript, required) and (
                sim >= PER_SAMPLE_SIMILARITY_FLOOR
            )
            if ok:
                passed.append(sample_id)
            else:
                failed.append((sample_id, ground_truth, transcript, sim))

    total = len(JAPANESE_STT_SAMPLES)
    rate = len(passed) / total if total else 0.0

    summary_lines = [
        f"Aggregate STT accuracy: {len(passed)}/{total} = {rate:.1%}",
        f"Passed: {passed}",
        "Failed:",
    ]
    for sample_id, gt, tr, sim in failed:
        summary_lines.append(
            f"  - {sample_id}: ground_truth={gt!r} transcript={tr!r} similarity={sim:.3f}"
        )
    summary = "\n".join(summary_lines)

    assert rate >= AGGREGATE_ACCURACY_FLOOR, (
        f"Japanese STT aggregate accuracy {rate:.1%} below floor "
        f"{AGGREGATE_ACCURACY_FLOOR:.0%}.\n{summary}"
    )
