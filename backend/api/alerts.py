import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def _get_supabase():
    from backend.utils.supabase_helper import get_supabase_client

    return get_supabase_client()


class AlertPayload(BaseModel):
    type: str
    severity: str = "info"
    metric: str = ""
    value: float = 0
    threshold: float = 0
    source: str = ""
    metadata: dict[str, Any] | None = None


@router.post("")
async def receive_alert(request: Request, alert: AlertPayload):
    del request
    supabase = _get_supabase()
    now = datetime.now(timezone.utc)

    insert_data = {
        "type": alert.type,
        "severity": alert.severity,
        "metric": alert.metric,
        "value": alert.value,
        "threshold": alert.threshold,
        "source": alert.source,
        "metadata": alert.metadata or {},
        "created_at": now.isoformat(),
    }

    try:
        supabase.table("production_alerts").insert(insert_data).execute()
    except Exception as exc:
        logger.error("Failed to log alert: %s", exc)

    return {
        "received": True,
        "alert_id": f"alert-{int(now.timestamp())}",
        "action": "logged",
        "automated": False,
        "timestamp": now.isoformat(),
    }


@router.get("")
async def list_alerts(
    request: Request,
    severity: str | None = None,
    limit: int = 50,
):
    del request
    supabase = _get_supabase()

    query = (
        supabase.table("production_alerts").select("*").order("created_at", desc=True).limit(limit)
    )

    if severity:
        query = query.eq("severity", severity)

    result = query.execute()
    alerts = result.data or []

    return {
        "alerts": alerts,
        "count": len(alerts),
    }
