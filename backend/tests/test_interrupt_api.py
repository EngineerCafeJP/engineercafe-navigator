import json
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.utils.interrupt_manager import get_interrupt_manager


def test_interrupt_endpoint():
    from backend.main import app

    manager = get_interrupt_manager()
    manager.clear_interrupt("s1")

    client = TestClient(app)
    response = client.post("/api/interrupt", json={"session_id": "s1"})

    assert response.status_code == 200
    assert response.json() == {"status": "interrupted", "session_id": "s1"}
    assert manager.is_interrupted("s1")

    manager.clear_interrupt("s1")


def test_interrupt_requires_session_id():
    from backend.main import app

    client = TestClient(app)
    response = client.post("/api/interrupt", json={})

    assert response.status_code == 422


def test_chat_stream_emits_interrupted_event():
    from backend.main import app

    manager = get_interrupt_manager()
    manager.clear_interrupt("stream-session")

    async def mock_stream(_input_data):
        yield {"type": "token", "content": "first"}
        manager.request_interrupt("stream-session")
        yield {"type": "token", "content": "ignored"}

    mock_workflow = AsyncMock()
    mock_workflow.astream = mock_stream

    with patch(
        "backend.workflows.main_workflow.get_workflow",
        new_callable=AsyncMock,
        return_value=mock_workflow,
    ):
        client = TestClient(app)
        with client.stream(
            "POST",
            "/api/chat/stream",
            json={"query": "hello", "session_id": "stream-session"},
        ) as response:
            lines = [line for line in response.iter_lines() if line]

    payloads = [json.loads(line.removeprefix("data: ")) for line in lines if line != "data: [DONE]"]

    assert response.status_code == 200
    assert payloads == [
        {"type": "token", "content": "first"},
        {"type": "interrupted"},
    ]
    assert lines[-1] == "data: [DONE]"

    manager.clear_interrupt("stream-session")
