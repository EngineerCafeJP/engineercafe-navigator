import logging
from unittest.mock import AsyncMock, patch

import httpx
import pytest

import backend.main as main_mod
from backend.main import app

pytestmark = pytest.mark.asyncio


async def test_chat_emits_structured_observability_log(caplog, monkeypatch):
    monkeypatch.setattr(main_mod, "_API_SECRET_KEY", None)
    caplog.set_level(logging.INFO, logger="backend.observability.chat_response")

    mock_result = {
        "answer": "営業時間は9時からです。",
        "emotion": "neutral",
        "metadata": {
            "category": "business_info",
            "agent": "BusinessInfoAgent",
            "provider": "cerebras",
            "model": "gpt-oss-120b",
            "llm_latency_ms": 123,
            "sources": ["enhanced_rag"],
            "rag_fallback": False,
            "hallucination_flag": True,
            "ltm_store_write": "success",
        },
    }

    with patch.object(
        main_mod,
        "_run_workflow_with_tracking",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/chat",
                headers={"X-Request-ID": "req-obs-513"},
                json={"query": "営業時間は？", "session_id": "s1", "language": "ja"},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["requestId"] == "req-obs-513"
    assert body["phase"] == "chat"
    assert body["upstreamStatus"]["phase"] == "workflow"
    assert body["upstreamStatus"]["route"] == "business_info"
    records = [
        record
        for record in caplog.records
        if record.name == "backend.observability.chat_response"
        and getattr(record, "event", None) == "chat_response"
    ]
    assert records

    record = records[-1]
    assert record.request_id == "req-obs-513"
    assert record.language == "ja"
    assert record.route == "business_info"
    assert record.agent_class == "BusinessInfoAgent"
    assert record.provider == "cerebras"
    assert record.model == "gpt-oss-120b"
    assert record.llm_latency_ms == 123
    assert record.sources == ["enhanced_rag"]
    assert record.rag_fallback is False
    assert record.hallucination_flag is True
    assert record.ltm_store_write == "success"
    assert isinstance(record.latency_ms, int)
    assert record.latency_ms >= 0


async def test_chat_uses_response_language_for_metadata_and_logs(caplog, monkeypatch):
    monkeypatch.setattr(main_mod, "_API_SECRET_KEY", None)
    caplog.set_level(logging.INFO, logger="backend.observability.chat_response")

    mock_result = {
        "answer": "Engineer Cafe is a public engineer support facility in Fukuoka.",
        "emotion": "neutral",
        "language": "en",
        "metadata": {
            "category": "business_info",
            "sources": ["enhanced_rag"],
        },
    }

    with patch.object(
        main_mod,
        "_run_workflow_with_tracking",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/chat",
                headers={"X-Request-ID": "req-lang-780"},
                json={
                    "query": "tell me about engineer cafe",
                    "session_id": "s1",
                    "language": "ja",
                },
            )

    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["language"] == "en"
    assert body["metadata"]["response_language"] == "en"

    record = next(
        record
        for record in caplog.records
        if record.name == "backend.observability.chat_response"
        and getattr(record, "request_id", None) == "req-lang-780"
    )
    assert record.language == "en"
