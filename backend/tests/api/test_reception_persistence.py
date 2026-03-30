"""Persistence tests for the reception API session store."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator, Optional
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import backend.api.reception as reception_module
from backend.main import app
from backend.utils.reception_repository import ReceptionRepository

client = TestClient(app)


def _parse_timestamp(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    return value


@dataclass
class _FakeResult:
    data: list[dict[str, Any]]


class _FakeTableQuery:
    def __init__(self, storage: dict[str, dict[str, dict[str, Any]]], table_name: str) -> None:
        self._storage = storage
        self._table_name = table_name
        self._filters: list[tuple[str, str, Any]] = []
        self._limit: Optional[int] = None
        self._order_by: Optional[tuple[str, bool]] = None
        self._upsert_payload: Optional[dict[str, Any]] = None
        self._update_payload: Optional[dict[str, Any]] = None

    def select(self, *_args: Any, **_kwargs: Any) -> _FakeTableQuery:
        return self

    def eq(self, column: str, value: Any) -> _FakeTableQuery:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> _FakeTableQuery:
        self._filters.append(("in", column, values))
        return self

    def lt(self, column: str, value: Any) -> _FakeTableQuery:
        self._filters.append(("lt", column, value))
        return self

    def order(self, column: str, desc: bool = False) -> _FakeTableQuery:
        self._order_by = (column, desc)
        return self

    def limit(self, value: int) -> _FakeTableQuery:
        self._limit = value
        return self

    def update(self, payload: dict[str, Any]) -> _FakeTableQuery:
        self._update_payload = deepcopy(payload)
        return self

    def upsert(self, payload: dict[str, Any]) -> _FakeTableQuery:
        self._upsert_payload = deepcopy(payload)
        return self

    def execute(self) -> _FakeResult:
        table = self._storage.setdefault(self._table_name, {})

        if self._upsert_payload is not None:
            row_id = self._upsert_payload["id"]
            existing = deepcopy(table.get(row_id, {}))
            existing.update(deepcopy(self._upsert_payload))
            table[row_id] = existing
            return _FakeResult(data=[deepcopy(existing)])

        rows = [deepcopy(row) for row in table.values() if self._matches(row)]

        if self._update_payload is not None:
            updated_rows: list[dict[str, Any]] = []
            for row in rows:
                row_id = row["id"]
                current = deepcopy(table[row_id])
                current.update(deepcopy(self._update_payload))
                table[row_id] = current
                updated_rows.append(deepcopy(current))
            return _FakeResult(data=updated_rows)

        if self._order_by is not None:
            column, desc = self._order_by
            rows.sort(key=lambda row: str(row.get(column, "")), reverse=desc)

        if self._limit is not None:
            rows = rows[: self._limit]

        return _FakeResult(data=rows)

    def _matches(self, row: dict[str, Any]) -> bool:
        for operation, column, expected in self._filters:
            actual = row.get(column)
            if operation == "eq" and actual != expected:
                return False
            if operation == "in" and actual not in expected:
                return False
            if operation == "lt":
                if _parse_timestamp(actual) >= _parse_timestamp(expected):
                    return False
        return True


class _FakeSupabaseClient:
    def __init__(self) -> None:
        self.storage: dict[str, dict[str, dict[str, Any]]] = {}

    def table(self, name: str) -> _FakeTableQuery:
        return _FakeTableQuery(self.storage, name)


@pytest.fixture(autouse=True)
def reset_session_storage() -> Iterator[None]:
    reception_module._reset_session_storage()
    yield
    reception_module._reset_session_storage()


@dataclass
class _FakePurposeFlow:
    response_text: str = "Welcome to the coworking area."
    action_type: str = "guide"
    action_data: Optional[dict[str, Any]] = None


@dataclass
class _FakeHandoffResult:
    workflow_state: dict[str, Any] = None  # type: ignore[assignment]
    target_agent: str = "facility_agent"
    purpose_flow: _FakePurposeFlow = None  # type: ignore[assignment]
    requires_staff: bool = False

    def __post_init__(self) -> None:
        if self.workflow_state is None:
            self.workflow_state = {"step": "routed"}
        if self.purpose_flow is None:
            self.purpose_flow = _FakePurposeFlow()


def _sample_session_data(
    *,
    stage: str = "greeting",
    status: str = "active",
    expires_at: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "id": "rs-001",
        "session_id": "session-001",
        "stage": stage,
        "language": "ja",
        "trigger_type": "button_press",
        "created_at": "2026-03-15T00:00:00+00:00",
        "metadata": {"source": "test"},
        "purpose": {"category": "facility_use", "detail": "coworking"},
        "visitor_identity": {
            "visitor_type": "new",
            "user_id": None,
            "name": "Taro",
            "last_visit_date": None,
            "last_purpose": None,
            "visit_count": 0,
        },
        "visitor_name": "Taro",
        "visitor_type": "new",
        "status": status,
        "expires_at": expires_at or (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
    }


def _start_session(session_id: str = "sess-001") -> dict[str, Any]:
    response = client.post(
        "/api/reception/start",
        json={"session_id": session_id, "language": "ja", "trigger_type": "button_press"},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_repository_store_get_complete_lifecycle() -> None:
    fake_client = _FakeSupabaseClient()
    repo = ReceptionRepository(fake_client)  # type: ignore[arg-type]

    session_data = _sample_session_data()
    await repo.store_session("rs-001", session_data)

    stored = await repo.get_session("rs-001")
    assert stored is not None
    assert stored["session_data"]["session_id"] == "session-001"
    assert stored["visitor_name"] == "Taro"
    assert stored["status"] == "active"

    await repo.complete_session("rs-001")

    assert fake_client.storage["reception_sessions"]["rs-001"]["status"] == "completed"
    assert await repo.get_session("rs-001") is None


@pytest.mark.asyncio
async def test_repository_cleanup_expired_sessions() -> None:
    fake_client = _FakeSupabaseClient()
    repo = ReceptionRepository(fake_client)  # type: ignore[arg-type]

    await repo.store_session(
        "expired-session",
        _sample_session_data(
            expires_at=(datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
        ),
    )
    await repo.store_session(
        "active-session",
        _sample_session_data(
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        )
        | {"id": "active-session", "session_id": "session-002"},
    )

    expired_count = await repo.cleanup_expired()
    active_sessions = await repo.list_active_sessions()

    assert expired_count == 1
    assert fake_client.storage["reception_sessions"]["expired-session"]["status"] == "expired"
    assert [row["id"] for row in active_sessions] == ["active-session"]


def test_reception_api_session_survives_restart() -> None:
    fake_client = _FakeSupabaseClient()
    reception_module._session_repository = ReceptionRepository(fake_client)  # type: ignore[arg-type]

    start = _start_session(session_id="sess-001")
    reception_session_id = start["reception_session_id"]

    response = client.post(
        "/api/reception/respond",
        json={
            "session_id": "sess-001",
            "reception_session_id": reception_session_id,
            "message": "こんにちは",
        },
    )
    assert response.status_code == 200

    response = client.post(
        "/api/reception/respond",
        json={
            "session_id": "sess-001",
            "reception_session_id": reception_session_id,
            "message": "コワーキングスペースを利用したいです",
        },
    )
    assert response.status_code == 200

    reception_module._active_sessions.clear()
    reception_module._session_repository = ReceptionRepository(fake_client)  # type: ignore[arg-type]

    status = client.get(
        f"/api/reception/status/{reception_session_id}",
        params={"session_id": "sess-001"},
    )
    assert status.status_code == 200
    assert status.json()["stage"] == "routing"
    assert status.json()["purpose"] == "facility_use"

    fake_result = _FakeHandoffResult()
    mock_service = AsyncMock()
    mock_service.prepare_handoff.return_value = fake_result
    mock_workflow = AsyncMock()
    mock_workflow.ainvoke_from_reception = AsyncMock(return_value={"answer": "Welcome"})

    with (
        patch("backend.api.reception._get_handoff_service", return_value=mock_service),
        patch(
            "backend.workflows.main_workflow.get_workflow",
            new=AsyncMock(return_value=mock_workflow),
        ),
    ):
        complete = client.post(
            "/api/reception/complete",
            json={
                "session_id": "sess-001",
                "reception_session_id": reception_session_id,
            },
        )

    assert complete.status_code == 200
    assert fake_client.storage["reception_sessions"][reception_session_id]["status"] == "completed"
