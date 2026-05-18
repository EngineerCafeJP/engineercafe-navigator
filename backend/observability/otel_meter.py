"""Vendor-neutral OpenTelemetry metric helpers for Wave 3 observability.

The backend should start cleanly even when OpenTelemetry is not installed. This module
therefore wraps instruments behind tiny no-op proxies and imports OTel lazily.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Callable

VOICE_ROUND_TRIP_MS = "voice_round_trip_ms"
CHAT_RESPONSE_MS = "chat_response_ms"
STT_LATENCY_MS = "stt_latency_ms"
TTS_LATENCY_MS = "tts_latency_ms"
AGENT_ROUTE_COUNT = "agent_route_count"
STT_WINNER_COUNT = "stt_winner_count"
ERROR_COUNT = "error_count"
FRONTEND_AUDIO_WATCHDOG_COUNT = "frontend_audio_watchdog_count"
FRONTEND_FALLBACK_COUNT = "frontend_fallback_count"

METER_NAME = "backend.observability.wave3"

PrimitiveAttribute = str | bool | int | float
Attributes = dict[str, PrimitiveAttribute]


@dataclass(frozen=True)
class NoopInstrument:
    """Drop-in counter/histogram used when OTel is unavailable."""

    name: str
    unit: str | None = None

    def add(self, amount: int | float, attributes: Attributes | None = None) -> None:
        return None

    def record(self, amount: int | float, attributes: Attributes | None = None) -> None:
        return None


class InstrumentProxy:
    """Normalize OTel instruments and no-op instruments to a small safe API."""

    def __init__(self, instrument: Any, *, name: str, unit: str | None = None) -> None:
        self.instrument = instrument
        self.name = name
        self.unit = unit

    def add(self, amount: int | float, attributes: Attributes | None = None) -> None:
        add = getattr(self.instrument, "add", None)
        if not callable(add):
            return None
        try:
            add(amount, attributes=attributes or {})
        except Exception:
            return None
        return None

    def record(self, amount: int | float, attributes: Attributes | None = None) -> None:
        record = getattr(self.instrument, "record", None)
        if not callable(record):
            return None
        try:
            record(amount, attributes=attributes or {})
        except Exception:
            return None
        return None


def _load_default_meter() -> Any | None:
    try:
        metrics = importlib.import_module("opentelemetry.metrics")
    except ImportError:
        return None

    get_meter = getattr(metrics, "get_meter", None)
    if not callable(get_meter):
        return None

    try:
        return get_meter(METER_NAME)
    except Exception:
        return None


def _coerce_ms(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def _attrs(payload: dict[str, Any], keys: tuple[str, ...]) -> Attributes:
    attributes: Attributes = {}
    for key in keys:
        value = payload.get(key)
        if isinstance(value, (str, bool, int, float)):
            attributes[key] = value
    return attributes


class ObservabilityMeter:
    """Small wrapper around Wave 3 metrics with no-op fallback semantics."""

    def __init__(self, meter: Any | None = None) -> None:
        self._meter = meter if meter is not None else _load_default_meter()
        self.enabled = self._meter is not None

        self.voice_round_trip_ms = self._create_histogram(VOICE_ROUND_TRIP_MS, unit="ms")
        self.chat_response_ms = self._create_histogram(CHAT_RESPONSE_MS, unit="ms")
        self.stt_latency_ms = self._create_histogram(STT_LATENCY_MS, unit="ms")
        self.tts_latency_ms = self._create_histogram(TTS_LATENCY_MS, unit="ms")
        self.agent_route_count = self._create_counter(AGENT_ROUTE_COUNT)
        self.stt_winner_count = self._create_counter(STT_WINNER_COUNT)
        self.error_count = self._create_counter(ERROR_COUNT)
        self.frontend_audio_watchdog_count = self._create_counter(FRONTEND_AUDIO_WATCHDOG_COUNT)
        self.frontend_fallback_count = self._create_counter(FRONTEND_FALLBACK_COUNT)

    def _create_histogram(self, name: str, *, unit: str) -> InstrumentProxy:
        if self._meter is None:
            return InstrumentProxy(NoopInstrument(name=name, unit=unit), name=name, unit=unit)

        create_histogram: Callable[..., Any] | None = getattr(
            self._meter,
            "create_histogram",
            None,
        )
        if not callable(create_histogram):
            return InstrumentProxy(NoopInstrument(name=name, unit=unit), name=name, unit=unit)

        try:
            instrument = create_histogram(name, unit=unit)
        except Exception:
            instrument = NoopInstrument(name=name, unit=unit)
        return InstrumentProxy(instrument, name=name, unit=unit)

    def _create_counter(self, name: str) -> InstrumentProxy:
        if self._meter is None:
            return InstrumentProxy(NoopInstrument(name=name), name=name)

        create_counter: Callable[..., Any] | None = getattr(self._meter, "create_counter", None)
        if not callable(create_counter):
            return InstrumentProxy(NoopInstrument(name=name), name=name)

        try:
            instrument = create_counter(name)
        except Exception:
            instrument = NoopInstrument(name=name)
        return InstrumentProxy(instrument, name=name)

    def record_event_payload(self, payload: dict[str, Any]) -> None:
        event = str(payload.get("event") or "")

        if event == "chat_response":
            self.record_chat_response(payload)
        elif event == "stt_qwen_complete":
            self.record_stt_qwen_complete(payload)
        elif event == "stt_winner":
            self.record_stt_winner(payload)
        elif event in {"tts_synthesis_complete", "tts_synthesis_error"}:
            self.record_tts_synthesis(payload)
        elif event == "agent_routing":
            self.record_agent_routing(payload)
        elif event == "voice_round_trip":
            self.record_voice_round_trip(payload)
        elif event in {
            "thinking_watchdog_expire",
            "fallback_tts_triggered",
            "user_interaction_gate_timeout",
            "audio_playback_failed",
            "frontend_telemetry",
        }:
            self.record_frontend_telemetry(payload)

    def record_chat_response(self, payload: dict[str, Any]) -> None:
        latency_ms = _coerce_ms(payload.get("latency_ms"))
        if latency_ms is not None:
            self.chat_response_ms.record(
                latency_ms,
                attributes=_attrs(payload, ("route", "agent_route", "intent", "language")),
            )

    def record_stt_qwen_complete(self, payload: dict[str, Any]) -> None:
        latency_ms = _coerce_ms(payload.get("latency_ms"))
        attributes = _attrs(payload, ("provider", "language", "winner"))
        if latency_ms is not None:
            self.stt_latency_ms.record(latency_ms, attributes=attributes)
        if payload.get("winner") is True:
            self.stt_winner_count.add(1, attributes=attributes)

    def record_stt_winner(self, payload: dict[str, Any]) -> None:
        self.stt_winner_count.add(
            1,
            attributes=_attrs(payload, ("winner_provider", "language")),
        )

    def record_tts_synthesis(self, payload: dict[str, Any]) -> None:
        latency_ms = _coerce_ms(payload.get("latency_ms"))
        attributes = _attrs(
            payload,
            ("provider", "language", "fallback_used", "fallback_provider", "success"),
        )
        if latency_ms is not None:
            self.tts_latency_ms.record(latency_ms, attributes=attributes)
        if payload.get("success") is False:
            self.error_count.add(1, attributes=_attrs(payload, ("event", "error_type")))

    def record_agent_routing(self, payload: dict[str, Any]) -> None:
        self.agent_route_count.add(
            1,
            attributes=_attrs(payload, ("routed_to", "intent", "fallback_used")),
        )

    def record_voice_round_trip(self, payload: dict[str, Any]) -> None:
        total_ms = _coerce_ms(payload.get("total_ms"))
        if total_ms is not None:
            self.voice_round_trip_ms.record(
                total_ms,
                attributes=_attrs(payload, ("success", "error_type")),
            )
        if payload.get("success") is False:
            self.error_count.add(1, attributes=_attrs(payload, ("event", "error_type")))

    def record_frontend_telemetry(self, payload: dict[str, Any]) -> None:
        event = str(payload.get("telemetry_event") or payload.get("event") or "")
        attributes = _attrs(payload, ("event", "telemetry_event", "session_id"))
        if event == "thinking_watchdog_expire":
            self.frontend_audio_watchdog_count.add(1, attributes=attributes)
        elif event == "fallback_tts_triggered":
            self.frontend_fallback_count.add(1, attributes=attributes)
        elif event in {"user_interaction_gate_timeout", "audio_playback_failed"}:
            self.error_count.add(1, attributes=attributes)


_DEFAULT_METER: ObservabilityMeter | None = None


def get_otel_meter() -> ObservabilityMeter:
    global _DEFAULT_METER
    if _DEFAULT_METER is None:
        _DEFAULT_METER = ObservabilityMeter()
    return _DEFAULT_METER


def reset_otel_meter_for_tests() -> None:
    global _DEFAULT_METER
    _DEFAULT_METER = None
