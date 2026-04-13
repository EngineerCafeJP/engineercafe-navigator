"""Live scenario coverage for real LangGraph answers.

These tests execute the actual workflow with real external dependencies and
assert high-signal facts for the most important visitor scenarios.
"""

from __future__ import annotations

import os
import uuid

import pytest

from backend.tests.e2e.conftest import (
    assert_keyword_groups,
    keyword_group_match,
)

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


def _assert_live_result(
    result: dict,
    *,
    fact_groups: list[list[str] | tuple[str, ...]],
    expected_agents: set[str] | None = None,
    context_groups: list[list[str] | tuple[str, ...]] | None = None,
    label: str,
) -> None:
    answer = result["answer"]
    assert answer, f"{label}: answer must not be empty"
    assert_keyword_groups(answer, fact_groups, msg=label)

    metadata = result.get("metadata") or {}
    agent = metadata.get("agent")
    if expected_agents and agent:
        assert (
            agent in expected_agents
        ), f"{label}: unexpected agent {agent!r}, expected one of {sorted(expected_agents)}"

    retrieved_contexts = result.get("retrieved_contexts") or []
    if context_groups and retrieved_contexts:
        flattened_context = "\n".join(retrieved_contexts)
        for group in context_groups:
            matched, _ = keyword_group_match(flattened_context, list(group))
            assert matched, (
                f"{label}: retrieved contexts did not include any of {group}. "
                f"Contexts: {flattened_context[:500]}..."
            )


class TestLiveLangGraphScenarios:
    async def test_first_visit_scenario(self, invoke_workflow, e2e_session_id):
        """初回訪問の基本導線: 施設紹介 -> 営業時間 -> Wi-Fi."""
        sid = str(uuid.uuid4())

        intro = await invoke_workflow("エンジニアカフェって何ですか？", session_id=sid)
        _assert_live_result(
            intro,
            fact_groups=[
                ["無料", "free"],
                ["コワーキング", "coworking"],
                ["赤煉瓦文化館", "red-brick", "red brick"],
            ],
            expected_agents={"BusinessInfoAgent", "GeneralKnowledgeAgent"},
            context_groups=[["赤煉瓦文化館", "engineer cafe"]],
            label="first-visit:intro",
        )

        hours = await invoke_workflow("営業時間は何時までですか？", session_id=sid)
        _assert_live_result(
            hours,
            fact_groups=[["22:00", "22時"]],
            expected_agents={"BusinessInfoAgent"},
            context_groups=[["22:00", "開館時間"]],
            label="first-visit:hours",
        )

        wifi = await invoke_workflow("WiFiは使えますか？", session_id=sid)
        _assert_live_result(
            wifi,
            fact_groups=[
                ["wifi", "wi-fi", "ワイファイ", "フリーワイファイ"],
                ["akarenga", "アカレンガ", "赤レンガ", "ssid", "エスエスアイディー"],
            ],
            expected_agents={"FacilityAgent", "BusinessInfoAgent"},
            context_groups=[["wifi", "wi-fi", "ssid", "engnecf"]],
            label="first-visit:wifi",
        )

    async def test_multilingual_intro_scenario(self, invoke_workflow, e2e_session_id):
        """英語話者向けの紹介と営業時間案内."""
        sid = str(uuid.uuid4())

        intro = await invoke_workflow("What is this place?", language="en", session_id=sid)
        _assert_live_result(
            intro,
            fact_groups=[
                ["free"],
                ["coworking"],
                ["engineer"],
            ],
            expected_agents={"BusinessInfoAgent", "GeneralKnowledgeAgent"},
            context_groups=[["engineer cafe", "coworking", "free"]],
            label="multilingual:intro",
        )

        hours = await invoke_workflow("What are the opening hours?", language="en", session_id=sid)
        _assert_live_result(
            hours,
            fact_groups=[["22:00"]],
            expected_agents={"BusinessInfoAgent"},
            context_groups=[["22:00"]],
            label="multilingual:hours",
        )

    async def test_multi_intent_hours_and_wifi(self, invoke_workflow, e2e_session_id):
        """営業時間と Wi-Fi パスワードの複合問い合わせ."""
        result = await invoke_workflow(
            "営業時間とWi-Fiのパスワードを教えてください",
            session_id=str(uuid.uuid4()),
        )
        _assert_live_result(
            result,
            fact_groups=[
                ["22:00", "22時"],
                ["akarenga-112years"],
                ["wifi", "wi-fi", "ssid"],
            ],
            expected_agents={"BusinessInfoAgent", "FacilityAgent"},
            context_groups=[
                ["22:00"],
                ["akarenga-112years", "engnecf"],
            ],
            label="multi-intent:hours+wifi",
        )

    async def test_event_listing_points_to_connpass(self, invoke_workflow, e2e_session_id):
        """日付依存を避けつつイベント導線を検証."""
        if not (os.getenv("GOOGLE_CALENDAR_ICAL_URL") or os.getenv("CONNPASS_API_KEY")):
            pytest.xfail("Event data sources are not configured in this environment")

        result = await invoke_workflow(
            "Connpassでイベントを確認できますか？",
            session_id=str(uuid.uuid4()),
        )
        _assert_live_result(
            result,
            fact_groups=[
                ["connpass"],
                ["イベント", "event"],
            ],
            expected_agents={"EventAgent", "GeneralKnowledgeAgent", "BusinessInfoAgent"},
            context_groups=[["connpass", "engineercafe.connpass.com"]],
            label="events:connpass",
        )
