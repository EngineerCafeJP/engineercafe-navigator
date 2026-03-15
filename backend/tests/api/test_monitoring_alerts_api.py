"""Monitoring and alerts API tests."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.alerts import router as alerts_router
from backend.api.monitoring import router as monitoring_router

_test_app = FastAPI()
_test_app.include_router(monitoring_router)
_test_app.include_router(alerts_router)
client = TestClient(_test_app)


def _mock_result(*, data=None, count=None):
    result = MagicMock()
    result.data = data
    result.count = count
    return result


@patch("backend.api.monitoring._get_supabase")
def test_get_dashboard_returns_summary(mock_get_supabase):
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase
    mock_supabase.table.return_value.select.return_value.execute.return_value = _mock_result(
        count=7
    )

    response = client.get("/api/monitoring/dashboard?range=7d")

    assert response.status_code == 200
    body = response.json()
    assert body["timeRange"] == "7d"
    assert body["summary"]["knowledgeBaseEntries"] == 7
    assert body["health"]["status"] == "healthy"


@patch("backend.api.monitoring._get_supabase")
def test_get_migration_success_returns_count(mock_get_supabase):
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase
    mock_supabase.table.return_value.select.return_value.execute.return_value = _mock_result(
        count=12
    )

    response = client.get("/api/monitoring/migration-success")

    assert response.status_code == 200
    body = response.json()
    assert body["migration"]["totalEntries"] == 12
    assert body["migration"]["embeddingModel"] == "text-embedding-3-small"
    assert body["overall_status"] == "success"


@patch("backend.api.alerts._get_supabase")
def test_receive_alert_inserts_alert(mock_get_supabase):
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase

    response = client.post(
        "/api/alerts",
        json={
            "type": "response_time",
            "severity": "warning",
            "metric": "latency_ms",
            "value": 1500,
            "threshold": 1000,
            "source": "vercel",
            "metadata": {"region": "nrt1"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["received"] is True
    assert body["action"] == "logged"
    mock_supabase.table.return_value.insert.assert_called_once()


@patch("backend.api.alerts._get_supabase")
def test_list_alerts_returns_filtered_results(mock_get_supabase):
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase
    query = MagicMock()
    mock_supabase.table.return_value.select.return_value.order.return_value.limit.return_value = (
        query
    )
    query.eq.return_value = query
    query.execute.return_value = _mock_result(
        data=[
            {
                "type": "error_rate",
                "severity": "critical",
                "metric": "error_rate",
                "value": 0.2,
                "threshold": 0.1,
                "source": "monitor",
            }
        ]
    )

    response = client.get("/api/alerts?severity=critical&limit=10")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["alerts"][0]["severity"] == "critical"
    query.eq.assert_called_once_with("severity", "critical")
