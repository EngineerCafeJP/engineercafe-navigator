import asyncio

import pytest

from backend.services.stt_warmup_service import STTWarmupService


@pytest.mark.asyncio
async def test_warmup_skips_non_qwen_primary_provider():
    service = STTWarmupService()
    called = False

    async def warmup():
        nonlocal called
        called = True

    snapshot = await service.warmup(provider="vosk", warmup_factory=warmup)

    assert snapshot.status == "skipped"
    assert snapshot.provider == "vosk"
    assert called is False


@pytest.mark.asyncio
async def test_warmup_does_not_start_duplicate_tasks():
    service = STTWarmupService()
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def warmup():
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()

    first = await service.warmup(provider="qwen-primary", warmup_factory=warmup)
    await started.wait()
    second = await service.warmup(provider="qwen-primary", warmup_factory=warmup)

    assert first.status == "started"
    assert second.status == "warming"
    assert calls == 1

    release.set()
    ready = await service.warmup(
        provider="qwen-primary",
        warmup_factory=warmup,
        wait=True,
    )

    assert ready.status == "ready"
    assert calls == 1


@pytest.mark.asyncio
async def test_warmup_failure_is_reported_as_status():
    service = STTWarmupService()
    calls = 0

    async def warmup():
        nonlocal calls
        calls += 1
        raise RuntimeError("model load failed")

    failed = await service.warmup(
        provider="qwen-primary",
        warmup_factory=warmup,
        wait=True,
    )

    assert failed.status == "failed"
    assert failed.provider == "qwen-primary"
    assert "model load failed" in (failed.error or "")

    next_call = await service.warmup(provider="qwen-primary", warmup_factory=warmup)

    assert next_call.status == "failed"
    assert calls == 1


@pytest.mark.asyncio
async def test_warmup_can_raise_for_startup_failure():
    service = STTWarmupService()

    async def warmup():
        raise RuntimeError("startup warmup failed")

    with pytest.raises(RuntimeError, match="startup warmup failed"):
        await service.warmup(
            provider="qwen-primary",
            warmup_factory=warmup,
            wait=True,
            raise_on_failure=True,
        )
