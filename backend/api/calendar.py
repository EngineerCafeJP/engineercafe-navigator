"""Calendar API routes."""

from __future__ import annotations

import sys
from typing import Any, Callable, cast

from fastapi import APIRouter, HTTPException
from starlette.requests import Request

from backend.tools.calendar_service import CalendarService, TimeRange  # noqa: F401

_CALENDAR_TIME_RANGES = {"today", "tomorrow", "thisWeek", "nextWeek", "thisMonth"}

deps = sys.modules[__name__]


def configure_dependencies(module: Any) -> None:
    global deps
    deps = module


async def calendar_api(request: Request, timeRange: str = "thisWeek"):
    """Return calendar events fetched from the backend-managed ICS feed."""
    if timeRange not in _CALENDAR_TIME_RANGES:
        raise HTTPException(status_code=400, detail="Invalid timeRange")

    result = await deps.CalendarService().search_events(cast(deps.TimeRange, timeRange))
    if not result.get("success"):
        raise HTTPException(
            status_code=502,
            detail=result.get("error", "Failed to fetch calendar events"),
        )

    return result


def create_router(rate_limit: Callable[[str], Callable[[Any], Any]]) -> APIRouter:
    router = APIRouter(tags=["calendar"])
    router.add_api_route(
        "/api/calendar",
        rate_limit("60/minute")(calendar_api),
        methods=["GET"],
    )
    return router
