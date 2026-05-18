from __future__ import annotations

from backend.observability import otel_meter


class FakeInstrument:
    def __init__(self, name: str, unit: str | None = None) -> None:
        self.name = name
        self.unit = unit
        self.adds: list[tuple[int | float, dict[str, object]]] = []
        self.records: list[tuple[int | float, dict[str, object]]] = []

    def add(self, amount, attributes=None) -> None:
        self.adds.append((amount, attributes or {}))

    def record(self, amount, attributes=None) -> None:
        self.records.append((amount, attributes or {}))


class FakeMeter:
    def __init__(self) -> None:
        self.instruments: dict[str, FakeInstrument] = {}

    def create_histogram(self, name: str, unit: str | None = None) -> FakeInstrument:
        instrument = FakeInstrument(name=name, unit=unit)
        self.instruments[name] = instrument
        return instrument

    def create_counter(self, name: str) -> FakeInstrument:
        instrument = FakeInstrument(name=name)
        self.instruments[name] = instrument
        return instrument


def test_observability_meter_creates_wave3_instruments():
    fake_meter = FakeMeter()

    meter = otel_meter.ObservabilityMeter(fake_meter)

    assert meter.enabled is True
    assert set(fake_meter.instruments) == {
        "voice_round_trip_ms",
        "chat_response_ms",
        "stt_latency_ms",
        "tts_latency_ms",
        "agent_route_count",
        "stt_winner_count",
        "error_count",
        "frontend_audio_watchdog_count",
        "frontend_fallback_count",
    }
    assert fake_meter.instruments["voice_round_trip_ms"].unit == "ms"
    assert fake_meter.instruments["stt_latency_ms"].unit == "ms"


def test_observability_meter_records_payloads_to_expected_instruments():
    fake_meter = FakeMeter()
    meter = otel_meter.ObservabilityMeter(fake_meter)

    meter.record_event_payload(
        {
            "event": "stt_qwen_complete",
            "provider": "qwen-primary",
            "language": "ja",
            "latency_ms": 1820,
            "winner": True,
        }
    )
    meter.record_event_payload(
        {
            "event": "agent_routing",
            "routed_to": "facility",
            "intent": "facility_hours",
            "fallback_used": False,
        }
    )
    meter.record_event_payload(
        {
            "event": "voice_round_trip",
            "total_ms": 640,
            "success": False,
            "error_type": "TimeoutError",
        }
    )
    meter.record_event_payload({"event": "thinking_watchdog_expire", "session_id": "s1"})
    meter.record_event_payload({"event": "fallback_tts_triggered", "session_id": "s1"})

    assert fake_meter.instruments["stt_latency_ms"].records == [
        (1820, {"provider": "qwen-primary", "language": "ja", "winner": True})
    ]
    assert fake_meter.instruments["stt_winner_count"].adds == [
        (1, {"provider": "qwen-primary", "language": "ja", "winner": True})
    ]
    assert fake_meter.instruments["agent_route_count"].adds == [
        (
            1,
            {
                "routed_to": "facility",
                "intent": "facility_hours",
                "fallback_used": False,
            },
        )
    ]
    assert fake_meter.instruments["voice_round_trip_ms"].records == [
        (640, {"success": False, "error_type": "TimeoutError"})
    ]
    assert fake_meter.instruments["error_count"].adds == [
        (1, {"event": "voice_round_trip", "error_type": "TimeoutError"})
    ]
    assert fake_meter.instruments["frontend_audio_watchdog_count"].adds == [
        (1, {"event": "thinking_watchdog_expire", "session_id": "s1"})
    ]
    assert fake_meter.instruments["frontend_fallback_count"].adds == [
        (1, {"event": "fallback_tts_triggered", "session_id": "s1"})
    ]


def test_observability_meter_is_noop_when_opentelemetry_is_absent(monkeypatch):
    def import_module(name: str):
        if name == "opentelemetry.metrics":
            raise ImportError(name)
        return __import__(name)

    monkeypatch.setattr(otel_meter.importlib, "import_module", import_module)

    meter = otel_meter.ObservabilityMeter()

    assert meter.enabled is False
    meter.record_event_payload({"event": "voice_round_trip", "total_ms": 100, "success": True})
    meter.record_event_payload({"event": "tts_synthesis_error", "latency_ms": 20, "success": False})
    meter.record_event_payload({"event": "audio_playback_failed", "session_id": "s2"})


def test_instrument_proxy_swallows_exporter_errors():
    class FailingInstrument:
        def add(self, amount, attributes=None) -> None:
            raise RuntimeError("collector unavailable")

        def record(self, amount, attributes=None) -> None:
            raise RuntimeError("collector unavailable")

    proxy = otel_meter.InstrumentProxy(FailingInstrument(), name="error_count")

    assert proxy.add(1, attributes={"event": "voice_round_trip"}) is None
    assert proxy.record(100, attributes={"event": "voice_round_trip"}) is None
