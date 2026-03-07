"""
Agent smoke tests -- real-service integration verification.

These tests confirm that critical agents can connect to their backing
services and perform a minimal round-trip.  They are tagged with
``@pytest.mark.integration`` so CI can gate them behind environment
availability (e.g. ``pytest -m integration``).

Each test class has an ``autouse`` fixture that calls ``pytest.skip()``
when the required service is unreachable, keeping the suite green in
environments that lack the dependency.
"""

import asyncio
import base64
import os

import httpx
import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_service_available(url: str, timeout: float = 2.0) -> bool:
    """Return True if *url* responds with a non-5xx status code."""
    try:
        resp = httpx.get(url, timeout=timeout)
        return resp.status_code < 500
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 1. SlideAgent -- no external service required
# ---------------------------------------------------------------------------


class TestSlideAgentSmoke:
    """Verify SlideAgent can load narration files from disk and narrate."""

    def test_load_narration_ja(self):
        from backend.agents.slide_agent import SlideAgent

        agent = SlideAgent()
        result = agent.load_narration("ja")
        assert result is True, (
            "load_narration('ja') returned False. "
            "Ensure backend/slides/narration/engineer-cafe-ja.json exists."
        )

    def test_load_narration_en(self):
        from backend.agents.slide_agent import SlideAgent

        agent = SlideAgent()
        result = agent.load_narration("en")
        assert result is True, (
            "load_narration('en') returned False. "
            "Ensure backend/slides/narration/engineer-cafe-en.json exists."
        )

    def test_narration_data_has_slides(self):
        from backend.agents.slide_agent import SlideAgent

        agent = SlideAgent()
        agent.load_narration("ja")
        slides = agent.narration_data.get("slides", [])
        assert isinstance(slides, list), "narration_data['slides'] should be a list"
        assert len(slides) > 0, "narration_data['slides'] should not be empty"

    async def test_handle_slide_action_narrate(self):
        from backend.agents.slide_agent import SlideAgent

        agent = SlideAgent()
        loaded = agent.load_narration("ja")
        if not loaded:
            pytest.skip("Narration file not available")

        result = await agent.handle_slide_action(action="narrate", language="ja")
        assert "answer" in result, "narrate action should return a dict with 'answer' key"
        assert isinstance(result["answer"], str), "'answer' should be a string"
        assert len(result["answer"]) > 0, "'answer' should not be empty"


# ---------------------------------------------------------------------------
# 2. VoiceVox TTS -- requires local VoiceVox engine
# ---------------------------------------------------------------------------


class TestVoiceVoxSmoke:
    """Verify VoiceVox engine connectivity and basic TTS synthesis."""

    @pytest.fixture(autouse=True)
    def _require_voicevox(self):
        url = os.getenv("VOICEVOX_API_URL", "http://localhost:50021")
        if not _is_service_available(url):
            pytest.skip(
                "VoiceVox engine not available. "
                "Start it with: docker run -p 50021:50021 voicevox/voicevox_engine"
            )
        self.voicevox_url = url

    def test_speakers_endpoint(self):
        """GET /speakers should return a list of available speakers."""
        resp = httpx.get(f"{self.voicevox_url}/speakers", timeout=5.0)
        assert resp.status_code == 200, f"GET /speakers returned {resp.status_code}"
        speakers = resp.json()
        assert isinstance(speakers, list), "/speakers should return a JSON array"
        assert len(speakers) > 0, "At least one speaker should be registered"

    async def test_synthesize_wav(self):
        """Full audio_query + synthesis round-trip should produce WAV bytes."""
        from backend.agents.voice_agent import VoiceVoxClient

        client = VoiceVoxClient(api_url=self.voicevox_url)
        wav_b64 = await client.synthesize_wav_base64(
            text="テスト",
            lang="ja",
        )
        assert isinstance(wav_b64, str), "Result should be a base64 string"
        wav_bytes = base64.b64decode(wav_b64)
        # WAV files start with RIFF header
        assert wav_bytes[:4] == b"RIFF", "Decoded bytes should start with RIFF header (valid WAV)"
        assert len(wav_bytes) > 44, "WAV data should be larger than the 44-byte header"


# ---------------------------------------------------------------------------
# 3. Checkpointer -- requires Supabase PostgreSQL
# ---------------------------------------------------------------------------


class TestCheckpointerSmoke:
    """Verify AsyncPostgresSaver creation and teardown via Supabase DB."""

    @pytest.fixture(autouse=True)
    def _require_supabase_db(self):
        if not os.getenv("SUPABASE_DB_URI"):
            pytest.skip(
                "SUPABASE_DB_URI not set. "
                "Set it to a PostgreSQL connection string to run this test."
            )

    async def test_create_and_close_checkpointer(self):
        """create_checkpointer should return an AsyncPostgresSaver instance."""
        from backend.utils.checkpointer import (
            create_checkpointer,
            close_checkpointer,
            reset_checkpointer,
        )

        # Reset any existing singleton so we start clean
        await reset_checkpointer()

        try:
            checkpointer = await create_checkpointer()

            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            assert isinstance(
                checkpointer, AsyncPostgresSaver
            ), f"Expected AsyncPostgresSaver, got {type(checkpointer).__name__}"
        finally:
            # Clean up: close the connection and reset singleton
            await close_checkpointer()

    async def test_close_checkpointer_no_error(self):
        """close_checkpointer should complete without raising even if not initialized."""
        from backend.utils.checkpointer import close_checkpointer, reset_checkpointer

        await reset_checkpointer()
        # Calling close on an uninitialized checkpointer should be a no-op
        await close_checkpointer()


# ---------------------------------------------------------------------------
# 4. RAG search pipeline -- requires Supabase + OpenAI API key
# ---------------------------------------------------------------------------


class TestRAGSearchSmoke:
    """Verify that the RAG pipeline can connect to Supabase and run a search."""

    @pytest.fixture(autouse=True)
    def _require_supabase_and_openai(self):
        missing = []
        if not os.getenv("SUPABASE_URL"):
            missing.append("SUPABASE_URL")
        if not os.getenv("SUPABASE_KEY"):
            missing.append("SUPABASE_KEY")
        if not os.getenv("OPENAI_API_KEY"):
            missing.append("OPENAI_API_KEY")
        if missing:
            pytest.skip(
                f"Missing environment variable(s): {', '.join(missing)}. "
                "Set them to run RAG integration tests."
            )

    def test_supabase_client_creation(self):
        """EnhancedRAGSearch should initialize a Supabase client without error."""
        from backend.tools.enhanced_rag import EnhancedRAGSearch

        rag = EnhancedRAGSearch()
        assert rag.supabase is not None, "Supabase client should be initialized"

    async def test_search_returns_dict(self):
        """A simple search should return a dict with 'success' key."""
        from backend.tools.enhanced_rag import EnhancedRAGSearch

        rag = EnhancedRAGSearch()
        result = await asyncio.wait_for(
            rag.search(
                query="営業時間",
                category="hours",
                language="ja",
                max_results=3,
            ),
            timeout=30.0,
        )
        assert isinstance(result, dict), f"search() should return a dict, got {type(result)}"
        assert "success" in result, "Result dict should contain 'success' key"
