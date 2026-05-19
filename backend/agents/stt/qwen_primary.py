from __future__ import annotations

import asyncio
import importlib
import os
import time
import uuid
from typing import Any, Dict, Optional

from .common import (
    HedgedFallback,
    RejectedQwenPrimary,
    RejectedVoskFallback,
    TranscriptionResult,
    _duration_ms,
    _qwen_postprocess_enabled,
    _wav_metadata,
    logger,
    log_stt_event,
    log_stt_qwen_complete,
    log_stt_winner,
)
from .heuristics import (
    _normalize_vosk_route_transcript,
    _qwen_primary_transcript_suspicious,
    _vosk_fallback_transcript_suspicious,
    _vosk_transcript_trusted_for_early_return,
)


def _public_symbol(name: str, fallback: Any) -> Any:
    try:
        return getattr(importlib.import_module("backend.agents.stt_agent"), name)
    except Exception:
        return fallback


def _log_stt_event(**kwargs: Any) -> None:
    _public_symbol("log_stt_event", log_stt_event)(**kwargs)


def _log_stt_qwen_complete(**kwargs: Any) -> None:
    _public_symbol("log_stt_qwen_complete", log_stt_qwen_complete)(**kwargs)


def _log_stt_winner(**kwargs: Any) -> None:
    _public_symbol("log_stt_winner", log_stt_winner)(**kwargs)


async def transcribe_qwen_primary(
    self,
    audio_data: bytes,
    language: Optional[str] = None,
) -> Dict[str, Any]:
    """Qwen primary + Vosk fallback-only path (ADR-007/016).

    Qwen が ``QWEN_STT_HEDGE_DELAY_SECONDS`` 秒以内に成功すれば即座に返す。
    hedge delay を超えたら Qwen は継続しつつ Vosk fallback と race し、
    先に成功した結果を返す。Qwen の hard timeout / error 時も Vosk を使う。
    """

    stt_trace_id = f"stt-{uuid.uuid4().hex[:12]}"
    overall_started_at = time.perf_counter()
    qwen_postprocess_enabled = _qwen_postprocess_enabled()

    audio_data = await self._prepare_qwen_primary_audio(
        audio_data,
        stt_trace_id=stt_trace_id,
        language=language,
    )
    prepared_audio_metadata = _wav_metadata(audio_data)

    async def _run_qwen():
        qwen_started_at = time.perf_counter()
        _log_stt_event(
            event="stt_qwen_start",
            stt_trace_id=stt_trace_id,
            provider="qwen-primary",
            language=language,
            timeout_s=self._qwen_timeout,
            hedge_delay_s=self._qwen_hedge_delay,
            hedge_grace_s=self._qwen_hedge_grace,
            latency_budget_s=self._qwen_latency_budget,
            audio_bytes=len(audio_data),
            qwen_postprocess_enabled=qwen_postprocess_enabled,
        )
        try:
            result = await asyncio.wait_for(
                self.stt_client.transcribe(
                    audio_data,
                    language=language,
                    stt_trace_id=stt_trace_id,
                ),
                timeout=self._qwen_timeout,
            )
        except asyncio.CancelledError:
            qwen_duration_ms = _duration_ms(qwen_started_at)
            _log_stt_qwen_complete(
                stt_trace_id=stt_trace_id,
                provider="qwen-primary",
                language=language,
                audio_duration_ms=prepared_audio_metadata.get("audio_duration_ms"),
                latency_ms=qwen_duration_ms,
                confidence=None,
                transcript_length=0,
                winner=False,
                success=False,
                cancelled=True,
                error_type="CancelledError",
                stt_qwen_duration_ms=qwen_duration_ms,
                qwen_postprocess_enabled=qwen_postprocess_enabled,
            )
            raise
        except Exception as exc:
            qwen_duration_ms = _duration_ms(qwen_started_at)
            _log_stt_qwen_complete(
                stt_trace_id=stt_trace_id,
                provider="qwen-primary",
                language=language,
                audio_duration_ms=prepared_audio_metadata.get("audio_duration_ms"),
                latency_ms=qwen_duration_ms,
                confidence=None,
                transcript_length=0,
                winner=False,
                success=False,
                error_type=type(exc).__name__,
                stt_qwen_duration_ms=qwen_duration_ms,
                qwen_postprocess_enabled=qwen_postprocess_enabled,
            )
            raise

        qwen_duration_ms = _duration_ms(qwen_started_at)
        _log_stt_qwen_complete(
            stt_trace_id=stt_trace_id,
            provider="qwen-primary",
            language=result.language,
            audio_duration_ms=prepared_audio_metadata.get("audio_duration_ms"),
            latency_ms=qwen_duration_ms,
            transcript_length=len(result.text),
            transcript=result.text,
            winner=False,
            success=True,
            transcript_chars=len(result.text),
            confidence=result.confidence,
            stt_qwen_duration_ms=qwen_duration_ms,
            qwen_postprocess_enabled=qwen_postprocess_enabled,
        )
        return result

    async def _run_vosk():
        vosk_started_at = time.perf_counter()
        _log_stt_event(
            event="stt_vosk_start",
            stt_trace_id=stt_trace_id,
            provider="vosk-fallback",
            language=language,
            audio_bytes=len(audio_data),
        )
        try:
            if language is None:
                result = await self._vosk_fallback_client.transcribe_auto_detect(
                    audio_data,
                    stt_trace_id=stt_trace_id,
                )
            else:
                result = await self._vosk_fallback_client.transcribe(
                    audio_data,
                    language,
                    stt_trace_id=stt_trace_id,
                )
        except asyncio.CancelledError:
            _log_stt_event(
                event="stt_vosk_complete",
                stt_trace_id=stt_trace_id,
                provider="vosk-fallback",
                language=language,
                success=False,
                cancelled=True,
                vosk_fallback_started=True,
                stt_vosk_duration_ms=_duration_ms(vosk_started_at),
            )
            raise
        except Exception as exc:
            _log_stt_event(
                event="stt_vosk_complete",
                stt_trace_id=stt_trace_id,
                provider="vosk-fallback",
                language=language,
                success=False,
                error_type=type(exc).__name__,
                stt_vosk_duration_ms=_duration_ms(vosk_started_at),
            )
            raise

        normalized_text = _normalize_vosk_route_transcript(result.text, result.language)
        if normalized_text != result.text:
            _log_stt_event(
                event="stt_vosk_route_normalize",
                stt_trace_id=stt_trace_id,
                provider="vosk-fallback",
                language=result.language,
                success=True,
                transcript_chars=len(result.text),
                normalized_chars=len(normalized_text),
                stt_vosk_duration_ms=_duration_ms(vosk_started_at),
            )
            result = TranscriptionResult(
                text=normalized_text,
                confidence=result.confidence,
                language=result.language,
                word_confidences=result.word_confidences,
            )

        _log_stt_event(
            event="stt_vosk_complete",
            stt_trace_id=stt_trace_id,
            provider="vosk-fallback",
            language=result.language,
            success=True,
            transcript_chars=len(result.text),
            confidence=result.confidence,
            stt_vosk_duration_ms=_duration_ms(vosk_started_at),
        )
        return result

    vosk_fallback_allowed = asyncio.Event()

    async def _run_vosk_after_qwen_failure():
        vosk_task_started_at = time.perf_counter()
        try:
            await vosk_fallback_allowed.wait()
        except asyncio.CancelledError:
            _log_stt_event(
                event="stt_vosk_complete",
                stt_trace_id=stt_trace_id,
                provider="vosk-fallback",
                language=language,
                success=False,
                cancelled=True,
                vosk_fallback_started=False,
                stt_vosk_duration_ms=_duration_ms(vosk_task_started_at),
            )
            raise
        return await _run_vosk()

    def _remaining_latency_budget() -> float | None:
        if self._qwen_latency_budget is None:
            return None
        return self._qwen_latency_budget - (time.perf_counter() - overall_started_at)

    def _reject_suspicious_qwen_result(
        result: TranscriptionResult,
    ) -> RejectedQwenPrimary | None:
        if not _qwen_primary_transcript_suspicious(
            result.text,
            result.language,
            result.confidence,
        ):
            return None
        _log_stt_event(
            event="stt_qwen_rejected",
            stt_trace_id=stt_trace_id,
            provider="qwen-primary",
            language=result.language,
            success=False,
            transcript_chars=len(result.text),
            confidence=result.confidence,
            stt_overall_duration_ms=_duration_ms(overall_started_at),
            rejection_reason="suspicious_transcript",
        )
        return RejectedQwenPrimary("Rejected suspicious Qwen primary transcript")

    async def _await_qwen_after_vosk_failure() -> TranscriptionResult:
        remaining_budget = _remaining_latency_budget()
        if remaining_budget is None:
            return await qwen_task
        if remaining_budget <= 0:
            raise asyncio.TimeoutError("Qwen exceeded configured STT latency budget")
        try:
            return await asyncio.wait_for(
                asyncio.shield(qwen_task),
                timeout=remaining_budget,
            )
        except asyncio.TimeoutError:
            _log_stt_event(
                event="stt_qwen_latency_budget_complete",
                stt_trace_id=stt_trace_id,
                provider="qwen-primary",
                language=language,
                success=False,
                error_type="TimeoutError",
                latency_budget_s=self._qwen_latency_budget,
                stt_qwen_duration_ms=_duration_ms(overall_started_at),
            )
            raise

    qwen_task = asyncio.create_task(_run_qwen())
    vosk_task = asyncio.create_task(_run_vosk_after_qwen_failure())

    try:
        qwen_result: TranscriptionResult | Exception | None = None
        vosk_result: TranscriptionResult | Exception | None = None
        qwen_error_for_log: Exception | None = None
        hedge_started = False
        hedge_wait_duration_ms: int | None = None
        grace_wait_duration_ms: int | None = None

        if self._qwen_hedge_delay is None:
            try:
                qwen_result = await qwen_task
            except Exception as exc:
                qwen_result = exc
                qwen_error_for_log = exc
        else:
            try:
                qwen_result = await asyncio.wait_for(
                    asyncio.shield(qwen_task),
                    timeout=self._qwen_hedge_delay,
                )
            except asyncio.TimeoutError:
                hedge_started = True
                hedge_wait_duration_ms = _duration_ms(overall_started_at)
                qwen_error_for_log = HedgedFallback(
                    f"Qwen exceeded hedge delay {self._qwen_hedge_delay:.2f}s"
                )
                _log_stt_event(
                    event="stt_qwen_hedge_start",
                    stt_trace_id=stt_trace_id,
                    provider="qwen-primary",
                    language=language,
                    success=False,
                    stt_qwen_duration_ms=_duration_ms(overall_started_at),
                    stt_hedge_wait_duration_ms=hedge_wait_duration_ms,
                    hedge_delay_s=self._qwen_hedge_delay,
                    hedge_grace_s=self._qwen_hedge_grace,
                    latency_budget_s=self._qwen_latency_budget,
                )
                vosk_fallback_allowed.set()
                done, _pending = await asyncio.wait(
                    {qwen_task, vosk_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if qwen_task in done:
                    try:
                        qwen_result = await qwen_task
                    except Exception as exc:
                        qwen_result = exc
                        qwen_error_for_log = exc
                elif vosk_task in done:
                    try:
                        vosk_result = await vosk_task
                    except Exception as exc:
                        vosk_result = exc
                    vosk_trusted = isinstance(
                        vosk_result, TranscriptionResult
                    ) and _vosk_transcript_trusted_for_early_return(
                        vosk_result.text,
                        vosk_result.language,
                    )
                    if vosk_trusted:
                        _log_stt_event(
                            event="stt_vosk_early_accept",
                            stt_trace_id=stt_trace_id,
                            provider="vosk-fallback",
                            language=vosk_result.language,
                            success=True,
                            transcript_chars=len(vosk_result.text),
                            confidence=vosk_result.confidence,
                            hedge_grace_s=self._qwen_hedge_grace,
                            stt_overall_duration_ms=_duration_ms(overall_started_at),
                        )
                    if (
                        isinstance(vosk_result, TranscriptionResult)
                        and self._qwen_hedge_grace > 0
                        and not qwen_task.done()
                        and not vosk_trusted
                    ):
                        remaining_budget = self._qwen_hedge_grace
                        latency_budget_remaining = _remaining_latency_budget()
                        if latency_budget_remaining is not None:
                            remaining_budget = min(remaining_budget, latency_budget_remaining)
                        if remaining_budget <= 0:
                            _log_stt_event(
                                event="stt_qwen_hedge_grace_skipped",
                                stt_trace_id=stt_trace_id,
                                provider="qwen-primary",
                                language=language,
                                success=False,
                                hedge_grace_s=self._qwen_hedge_grace,
                                latency_budget_s=self._qwen_latency_budget,
                                stt_qwen_duration_ms=_duration_ms(overall_started_at),
                            )
                            remaining_budget = 0.0
                        if remaining_budget > 0:
                            grace_started_at = time.perf_counter()
                            _log_stt_event(
                                event="stt_qwen_hedge_grace_start",
                                stt_trace_id=stt_trace_id,
                                provider="qwen-primary",
                                language=language,
                                success=False,
                                hedge_grace_s=self._qwen_hedge_grace,
                                latency_budget_s=self._qwen_latency_budget,
                                effective_hedge_grace_s=remaining_budget,
                                stt_qwen_duration_ms=_duration_ms(overall_started_at),
                            )
                            try:
                                qwen_result = await asyncio.wait_for(
                                    asyncio.shield(qwen_task),
                                    timeout=remaining_budget,
                                )
                                grace_wait_duration_ms = _duration_ms(grace_started_at)
                            except asyncio.TimeoutError:
                                grace_wait_duration_ms = _duration_ms(grace_started_at)
                                _log_stt_event(
                                    event="stt_qwen_hedge_grace_complete",
                                    stt_trace_id=stt_trace_id,
                                    provider="qwen-primary",
                                    language=language,
                                    success=False,
                                    error_type="TimeoutError",
                                    hedge_grace_s=self._qwen_hedge_grace,
                                    latency_budget_s=self._qwen_latency_budget,
                                    effective_hedge_grace_s=remaining_budget,
                                    stt_qwen_grace_wait_duration_ms=grace_wait_duration_ms,
                                    stt_qwen_duration_ms=_duration_ms(overall_started_at),
                                )
                            except Exception as exc:
                                qwen_result = exc
                                qwen_error_for_log = exc
            except Exception as exc:
                qwen_result = exc
                qwen_error_for_log = exc

        if isinstance(qwen_result, TranscriptionResult):
            qwen_rejection = _reject_suspicious_qwen_result(qwen_result)
            if qwen_rejection is not None:
                qwen_result = qwen_rejection
                qwen_error_for_log = qwen_rejection
            else:
                if not vosk_task.done():
                    vosk_task.cancel()
                    await asyncio.gather(vosk_task, return_exceptions=True)
                _log_stt_winner(
                    stt_trace_id=stt_trace_id,
                    winner_provider="qwen-primary",
                    stt_winner="qwen",
                    provider="qwen-primary",
                    language=qwen_result.language,
                    confidence=qwen_result.confidence,
                    latency_ms=_duration_ms(overall_started_at),
                    alternatives=[
                        ("qwen-primary", qwen_result.confidence),
                        ("vosk-fallback", None),
                    ],
                    success=True,
                    stt_overall_duration_ms=_duration_ms(overall_started_at),
                    stt_hedge_started=hedge_started,
                    stt_hedge_wait_duration_ms=hedge_wait_duration_ms,
                    stt_qwen_grace_wait_duration_ms=grace_wait_duration_ms,
                    hedge_grace_s=self._qwen_hedge_grace,
                    qwen_postprocess_enabled=qwen_postprocess_enabled,
                )
                return {
                    "success": True,
                    "transcript": qwen_result.text,
                    "confidence": qwen_result.confidence,
                    "language": qwen_result.language,
                    "provider": "qwen-primary",
                }

        # Qwen failed or exceeded the hedge latency budget -> Vosk fallback
        if qwen_error_for_log is None:
            qwen_error_for_log = (
                qwen_result if isinstance(qwen_result, Exception) else HedgedFallback()
            )
        logger.warning(
            "Qwen STT failed or exceeded hedge delay, using Vosk fallback: %s",
            qwen_error_for_log,
        )
        vosk_fallback_allowed.set()
        if vosk_result is None:
            try:
                vosk_result = await vosk_task
            except Exception as exc:
                vosk_result = exc

        if isinstance(vosk_result, TranscriptionResult) and _vosk_fallback_transcript_suspicious(
            vosk_result.text,
            vosk_result.language,
            vosk_result.confidence,
        ):
            _log_stt_event(
                event="stt_vosk_rejected",
                stt_trace_id=stt_trace_id,
                provider="vosk-fallback",
                language=vosk_result.language,
                success=False,
                transcript_chars=len(vosk_result.text),
                confidence=vosk_result.confidence,
                stt_overall_duration_ms=_duration_ms(overall_started_at),
                qwen_error_type=type(qwen_error_for_log).__name__,
                rejection_reason="low_confidence_fragmented_transcript",
            )
            vosk_result = RejectedVoskFallback("Rejected suspicious Vosk fallback transcript")

        if (
            isinstance(vosk_result, Exception)
            and not isinstance(vosk_result, RejectedVoskFallback)
            and self._qwen_hedge_delay is not None
            and not qwen_task.done()
        ):
            try:
                qwen_result = await _await_qwen_after_vosk_failure()
            except asyncio.TimeoutError as exc:
                qwen_result = HedgedFallback(str(exc))
                qwen_error_for_log = qwen_result
            except Exception as exc:
                qwen_result = exc
                qwen_error_for_log = exc
            if isinstance(qwen_result, TranscriptionResult):
                qwen_rejection = _reject_suspicious_qwen_result(qwen_result)
                if qwen_rejection is not None:
                    qwen_result = qwen_rejection
                    qwen_error_for_log = qwen_rejection
                else:
                    _log_stt_winner(
                        stt_trace_id=stt_trace_id,
                        winner_provider="qwen-primary",
                        stt_winner="qwen",
                        provider="qwen-primary",
                        language=qwen_result.language,
                        confidence=qwen_result.confidence,
                        latency_ms=_duration_ms(overall_started_at),
                        alternatives=[
                            ("qwen-primary", qwen_result.confidence),
                            (
                                "vosk-fallback",
                                (
                                    vosk_result.confidence
                                    if isinstance(vosk_result, TranscriptionResult)
                                    else None
                                ),
                            ),
                        ],
                        success=True,
                        stt_overall_duration_ms=_duration_ms(overall_started_at),
                        stt_hedge_started=hedge_started,
                        stt_hedge_wait_duration_ms=hedge_wait_duration_ms,
                        stt_qwen_grace_wait_duration_ms=grace_wait_duration_ms,
                        hedge_grace_s=self._qwen_hedge_grace,
                        qwen_postprocess_enabled=qwen_postprocess_enabled,
                        vosk_error_type=type(vosk_result).__name__,
                    )
                    return {
                        "success": True,
                        "transcript": qwen_result.text,
                        "confidence": qwen_result.confidence,
                        "language": qwen_result.language,
                        "provider": "qwen-primary",
                    }

        if isinstance(vosk_result, TranscriptionResult):
            transcript = vosk_result.text
            postprocessed = False
            if os.getenv("STT_LLM_POSTPROCESS", "false").lower() == "true":
                corrected = await self._llm_post_process(transcript, vosk_result.language)
                if corrected != transcript:
                    postprocessed = True
                    transcript = corrected
            _log_stt_winner(
                stt_trace_id=stt_trace_id,
                winner_provider="vosk-fallback",
                stt_winner="vosk",
                provider="vosk-fallback",
                language=vosk_result.language,
                confidence=vosk_result.confidence,
                latency_ms=_duration_ms(overall_started_at),
                alternatives=[
                    ("vosk-fallback", vosk_result.confidence),
                    ("qwen-primary", None),
                ],
                success=True,
                stt_overall_duration_ms=_duration_ms(overall_started_at),
                stt_hedge_started=hedge_started,
                stt_hedge_wait_duration_ms=hedge_wait_duration_ms,
                stt_qwen_grace_wait_duration_ms=grace_wait_duration_ms,
                hedge_grace_s=self._qwen_hedge_grace,
                vosk_postprocessed=postprocessed,
                qwen_error_type=type(qwen_error_for_log).__name__,
            )
            return {
                "success": True,
                "transcript": transcript,
                "confidence": vosk_result.confidence,
                "language": vosk_result.language,
                "provider": "vosk-fallback",
                "postprocessed": postprocessed,
            }

        # Both failed
        _log_stt_winner(
            stt_trace_id=stt_trace_id,
            winner_provider="none",
            stt_winner="none",
            success=False,
            latency_ms=_duration_ms(overall_started_at),
            stt_overall_duration_ms=_duration_ms(overall_started_at),
            stt_hedge_started=hedge_started,
            stt_hedge_wait_duration_ms=hedge_wait_duration_ms,
            stt_qwen_grace_wait_duration_ms=grace_wait_duration_ms,
            qwen_error_type=type(qwen_error_for_log).__name__,
            vosk_error_type=type(vosk_result).__name__,
        )
        raise RuntimeError(f"Both Qwen and Vosk STT failed: qwen={qwen_result}, vosk={vosk_result}")
    finally:
        pending_tasks = [task for task in (qwen_task, vosk_task) if not task.done()]
        for task in pending_tasks:
            task.cancel()
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)
