from backend.agents.voice.text import get_tts_timeout_seconds


def test_piper_timeout_defaults_to_twenty_seconds_and_honors_env(monkeypatch):
    monkeypatch.delenv("TTS_PIPER_PRIMARY_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("TTS_PRIMARY_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("TTS_PIPER_TIMEOUT_SECONDS", raising=False)

    assert get_tts_timeout_seconds("piper", "primary") == 20.0

    monkeypatch.setenv("TTS_PIPER_PRIMARY_TIMEOUT_SECONDS", "12.5")

    assert get_tts_timeout_seconds("piper", "primary") == 12.5
