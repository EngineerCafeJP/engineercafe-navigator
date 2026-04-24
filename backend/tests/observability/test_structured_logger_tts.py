from __future__ import annotations

import json

from backend.observability import structured_logger as structured_logger_module


def test_log_tts_cache_event_outputs_json_with_tts_cache_hit(capsys):
    logger = structured_logger_module._get_tts_cache_logger()
    marker = structured_logger_module._TTS_CACHE_LOG_HANDLER_MARKER

    for handler in list(logger.handlers):
        if getattr(handler, marker, False):
            logger.removeHandler(handler)
            handler.close()

    structured_logger_module.log_tts_cache_event(
        hit=True,
        cache_key="ja:neutral:こんにちは",
        language="ja",
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip())

    assert payload["event"] == "tts_cache"
    assert payload["tts_cache_hit"] is True
    assert payload["cache_key"] == "ja:neutral:こんにちは"
    assert payload["language"] == "ja"
