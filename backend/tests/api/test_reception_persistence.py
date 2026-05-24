"""Persistence tests for the reception API session store."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator, Optional
from unittest.mock import Mock
import uuid

import pytest
from fastapi.testclient import TestClient

import backend.api.reception as reception_module
from backend.main import app
from backend.utils.reception_repository import ReceptionRepository

client = TestClient(app)

_VALID_RECEPTION_ID = "11111111-1111-1111-1111-111111111111"
_EXPIRED_RECEPTION_ID = "22222222-2222-2222-2222-222222222222"
_ACTIVE_RECEPTION_ID = "33333333-3333-3333-3333-333333333333"


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

    def gt(self, column: str, value: Any) -> _FakeTableQuery:
        self._filters.append(("gt", column, value))
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
            if operation == "gt":
                if _parse_timestamp(actual) <= _parse_timestamp(expected):
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


def _sample_session_data(
    *,
    stage: str = "greeting",
    status: str = "active",
    expires_at: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "id": _VALID_RECEPTION_ID,
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
    await repo.store_session(_VALID_RECEPTION_ID, session_data)

    stored = await repo.get_session(_VALID_RECEPTION_ID)
    assert stored is not None
    assert stored["session_data"]["session_id"] == "session-001"
    assert stored["visitor_name"] == "Taro"
    assert stored["status"] == "active"

    await repo.complete_session(_VALID_RECEPTION_ID)

    assert fake_client.storage["reception_sessions"][_VALID_RECEPTION_ID]["status"] == "completed"
    assert await repo.get_session(_VALID_RECEPTION_ID) is None


@pytest.mark.asyncio
async def test_repository_non_uuid_session_id_skips_primary_key_lookup() -> None:
    mock_client = Mock()
    repo = ReceptionRepository(mock_client)  # type: ignore[arg-type]

    assert await repo.get_session("alpha-b-20260502-B1-BIZ-002") is None
    await repo.complete_session("alpha-b-20260502-B1-BIZ-002")

    mock_client.table.assert_not_called()


@pytest.mark.asyncio
async def test_repository_non_uuid_conversation_session_id_resolves_stable_session() -> None:
    fake_client = _FakeSupabaseClient()
    repo = ReceptionRepository(fake_client)  # type: ignore[arg-type]

    synthetic_id = "alpha-m-recv-session-20260517"
    await repo.store_session(
        synthetic_id,
        _sample_session_data(stage="purpose_hearing", status="active")
        | {"id": synthetic_id, "session_id": synthetic_id},
    )

    found = await repo.get_session_by_conversation_id(synthetic_id)

    assert found is not None
    assert found["stage"] == "purpose_hearing"
    assert found["session_id"] is None
    assert found["session_data"]["session_id"] == synthetic_id


@pytest.mark.asyncio
async def test_repository_store_session_coerces_non_uuid_values_for_uuid_columns() -> None:
    fake_client = _FakeSupabaseClient()
    repo = ReceptionRepository(fake_client)  # type: ignore[arg-type]

    synthetic_id = "alpha-b-fast-20260502-B2-GREET-001"
    await repo.store_session(
        synthetic_id,
        _sample_session_data() | {"id": synthetic_id, "session_id": synthetic_id},
    )

    rows = fake_client.storage["reception_sessions"]
    assert len(rows) == 1
    stored_id, stored = next(iter(rows.items()))
    assert uuid.UUID(stored_id)
    assert stored_id != synthetic_id
    assert stored["session_id"] is None
    assert stored["session_data"]["session_id"] == synthetic_id


@pytest.mark.asyncio
async def test_repository_cleanup_expired_sessions() -> None:
    fake_client = _FakeSupabaseClient()
    repo = ReceptionRepository(fake_client)  # type: ignore[arg-type]

    await repo.store_session(
        _EXPIRED_RECEPTION_ID,
        _sample_session_data(
            expires_at=(datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
        ),
    )
    await repo.store_session(
        _ACTIVE_RECEPTION_ID,
        _sample_session_data(
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        )
        | {"id": _ACTIVE_RECEPTION_ID, "session_id": "session-002"},
    )

    expired_count = await repo.cleanup_expired()
    active_sessions = await repo.list_active_sessions()

    assert expired_count == 1
    assert fake_client.storage["reception_sessions"][_EXPIRED_RECEPTION_ID]["status"] == "expired"
    assert [row["id"] for row in active_sessions] == [_ACTIVE_RECEPTION_ID]


@pytest.mark.asyncio
async def test_repository_get_latest_sensor_event_returns_fresh_event_only() -> None:
    fake_client = _FakeSupabaseClient()
    repo = ReceptionRepository(fake_client)  # type: ignore[arg-type]

    fake_client.storage["sensor_events"] = {
        "1": {
            "id": 1,
            "device_id": "m5stack-001",
            "sensor_type": "pir_sr04",
            "distance_mm": 65,
            "triggered_at": datetime.now(timezone.utc).isoformat(),
        }
    }

    event = await repo.get_latest_sensor_event("m5stack-001")

    assert event is not None
    assert event["device_id"] == "m5stack-001"
    assert event["distance_mm"] == 65


@pytest.mark.asyncio
async def test_repository_get_latest_sensor_event_ignores_stale_event() -> None:
    fake_client = _FakeSupabaseClient()
    repo = ReceptionRepository(fake_client)  # type: ignore[arg-type]

    fake_client.storage["sensor_events"] = {
        "1": {
            "id": 1,
            "device_id": "m5stack-001",
            "sensor_type": "pir_sr04",
            "distance_mm": 65,
            "triggered_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
        }
    }

    event = await repo.get_latest_sensor_event("m5stack-001")

    assert event is None


@pytest.mark.asyncio
async def test_repository_get_latest_sensor_event_uses_default_60_second_ttl(
    monkeypatch,
) -> None:
    monkeypatch.delenv("SENSOR_TRIGGER_EVENT_TTL_SECONDS", raising=False)
    fake_client = _FakeSupabaseClient()
    repo = ReceptionRepository(fake_client)  # type: ignore[arg-type]

    fake_client.storage["sensor_events"] = {
        "1": {
            "id": 1,
            "device_id": "m5stack-001",
            "sensor_type": "pir_sr04",
            "distance_mm": 65,
            "triggered_at": (datetime.now(timezone.utc) - timedelta(seconds=59)).isoformat(),
        }
    }

    event = await repo.get_latest_sensor_event("m5stack-001")

    assert event is not None
    assert event["device_id"] == "m5stack-001"


@pytest.mark.asyncio
@pytest.mark.parametrize("env_value", ["invalid", "0", "-1"])
async def test_repository_get_latest_sensor_event_invalid_ttl_env_falls_back_to_60_seconds(
    monkeypatch, env_value
) -> None:
    monkeypatch.setenv("SENSOR_TRIGGER_EVENT_TTL_SECONDS", env_value)
    fake_client = _FakeSupabaseClient()
    repo = ReceptionRepository(fake_client)  # type: ignore[arg-type]

    fake_client.storage["sensor_events"] = {
        "1": {
            "id": 1,
            "device_id": "m5stack-001",
            "sensor_type": "pir_sr04",
            "distance_mm": 65,
            "triggered_at": (datetime.now(timezone.utc) - timedelta(seconds=61)).isoformat(),
        }
    }

    event = await repo.get_latest_sensor_event("m5stack-001")

    assert event is None


@pytest.mark.asyncio
async def test_repository_get_latest_sensor_event_uses_configured_ttl(monkeypatch) -> None:
    monkeypatch.setenv("SENSOR_TRIGGER_EVENT_TTL_SECONDS", "90")
    fake_client = _FakeSupabaseClient()
    repo = ReceptionRepository(fake_client)  # type: ignore[arg-type]

    fake_client.storage["sensor_events"] = {
        "1": {
            "id": 1,
            "device_id": "m5stack-001",
            "sensor_type": "pir_sr04",
            "distance_mm": 65,
            "triggered_at": (datetime.now(timezone.utc) - timedelta(seconds=75)).isoformat(),
        }
    }

    event = await repo.get_latest_sensor_event("m5stack-001")

    assert event is not None
    assert event["device_id"] == "m5stack-001"


@pytest.mark.asyncio
async def test_repository_get_latest_sensor_event_respects_since_epoch() -> None:
    fake_client = _FakeSupabaseClient()
    repo = ReceptionRepository(fake_client)  # type: ignore[arg-type]
    triggered_at = datetime.now(timezone.utc) - timedelta(seconds=5)

    fake_client.storage["sensor_events"] = {
        "1": {
            "id": 1,
            "device_id": "m5stack-001",
            "sensor_type": "pir_sr04",
            "distance_mm": 65,
            "triggered_at": triggered_at.isoformat(),
        }
    }

    event = await repo.get_latest_sensor_event(
        "m5stack-001",
        since_epoch=(triggered_at + timedelta(seconds=1)).timestamp(),
    )

    assert event is None


def test_reception_api_session_survives_restart() -> None:
    fake_client = _FakeSupabaseClient()
    reception_module._session_repository = ReceptionRepository(fake_client)  # type: ignore[arg-type]

    start = _start_session(session_id="sess-001")
    reception_session_id = start["reception_session_id"]

    reception_module._active_sessions.clear()
    reception_module._session_repository = ReceptionRepository(fake_client)  # type: ignore[arg-type]

    status = client.get(
        f"/api/reception/status/{reception_session_id}",
        params={"session_id": "sess-001"},
    )
    assert status.status_code == 200
    assert status.json()["stage"] == "greeting"
    assert status.json()["purpose"] is None
