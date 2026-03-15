import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])


def _get_supabase():
    from backend.utils.supabase_helper import get_supabase_client

    return get_supabase_client()


@router.get("/dashboard")
async def get_dashboard(request: Request, range: str = "24h"):
    del request
    supabase = _get_supabase()
    now = datetime.now(timezone.utc)

    range_map = {"1h": 1, "24h": 24, "7d": 168, "30d": 720}
    time_range = range if range in range_map else "24h"

    kb_result = supabase.table("knowledge_base").select("id", count="exact").execute()
    kb_count = kb_result.count or 0

    health = {
        "status": "healthy",
        "database": "connected",
        "knowledgeBaseEntries": kb_count,
        "timestamp": now.isoformat(),
    }

    return {
        "timestamp": now.isoformat(),
        "timeRange": time_range,
        "health": health,
        "summary": {
            "knowledgeBaseEntries": kb_count,
            "systemStatus": "healthy",
        },
    }


@router.get("/migration-success")
async def get_migration_success(request: Request):
    del request
    supabase = _get_supabase()

    kb_result = supabase.table("knowledge_base").select("id", count="exact").execute()
    total_entries = kb_result.count or 0

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "migration": {
            "status": "completed",
            "totalEntries": total_entries,
            "embeddingModel": "text-embedding-3-small",
            "dimensions": 1536,
        },
        "overall_status": "success",
    }
