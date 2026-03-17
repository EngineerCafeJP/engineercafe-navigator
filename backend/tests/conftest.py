"""Pytest configuration and fixtures"""

import os
import sys
from pathlib import Path
import pytest
import asyncio

# ---------------------------------------------------------------------------
# CLI option & marker handling (must be in root conftest for pytest discovery)
# ---------------------------------------------------------------------------


def pytest_addoption(parser):
    """--run-e2e オプションを追加"""
    parser.addoption(
        "--run-e2e",
        action="store_true",
        default=False,
        help="run end-to-end tests that require real API keys",
    )


def pytest_collection_modifyitems(config, items):
    """e2e マーカー付きテストを --run-e2e なしでスキップ"""
    if config.getoption("--run-e2e"):
        return

    skip_e2e = pytest.mark.skip(reason="need --run-e2e option to run")
    for item in items:
        # @pytest.mark.e2e が明示的に付与されたテストのみスキップ
        # (ディレクトリ名 "e2e" によるマッチを除外)
        if item.get_closest_marker("e2e") is not None:
            item.add_marker(skip_e2e)


# Add project root to Python path
# For imports like "from backend.agents import ..."
project_root = Path(__file__).parent.parent.parent  # engineer-cafe-navigator2025/
sys.path.insert(0, str(project_root))

# Load .env.local first (real API keys for integration/RAGAS tests),
# then fall back to dummy values for pure unit tests.
_backend_dir = Path(__file__).parent.parent
_env_local = _backend_dir / ".env.local"
if _env_local.exists():
    from dotenv import load_dotenv

    load_dotenv(_env_local, override=False)

# Fallback defaults for CI / environments without .env.local
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_KEY", "test-key")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("OPENROUTER_API_KEY", "test-openrouter-key")
os.environ.setdefault("ENVIRONMENT", "test")


# ==============================================================================
# Event Loop Fixtures
# ==============================================================================


@pytest.fixture(scope="session")
def event_loop():
    """
    イベントループのフィクスチャ（セッションスコープ）

    pytest-asyncioで非同期テストを実行するためのイベントループを提供します。
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ==============================================================================
# OpenRouter Provider Fixtures
# ==============================================================================


@pytest.fixture(autouse=True)
def _reset_rag_circuit_breaker():
    """Reset the RAG circuit breaker between tests to prevent state leakage"""
    from backend.tools.enhanced_rag import _rag_circuit_breaker

    _rag_circuit_breaker.reset()
    yield
    _rag_circuit_breaker.reset()


@pytest.fixture
def mock_openrouter_provider():
    """
    モックOpenRouterProviderのフィクスチャ

    実際のAPI呼び出しを行わず、テスト用のモックレスポンスを返します。

    Returns:
        Mock: OpenRouterProviderのモック
    """
    from unittest.mock import Mock, AsyncMock

    provider = Mock()
    provider.generate = AsyncMock(
        return_value={
            "text": "モックレスポンス",
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        }
    )
    return provider


@pytest.fixture
def qa_response_config():
    """
    QA応答用のモデル設定フィクスチャ

    Returns:
        Dict[str, Any]: モデル設定
    """
    return {"model": "openai/gpt-4-turbo", "temperature": 0.7, "max_tokens": 1000}


@pytest.fixture
def facility_info_config():
    """
    施設情報用のモデル設定フィクスチャ

    Returns:
        Dict[str, Any]: モデル設定
    """
    return {"model": "google/gemini-pro", "temperature": 0.5, "max_tokens": 800}


# ==============================================================================
# Test Data Fixtures
# ==============================================================================


@pytest.fixture
def sample_query():
    """
    サンプルクエリのフィクスチャ

    Returns:
        str: テスト用のサンプルクエリ
    """
    return "営業時間を教えてください"


@pytest.fixture
def sample_session_id():
    """
    サンプルセッションIDのフィクスチャ

    Returns:
        str: テスト用のセッションID
    """
    return "test-session-12345"


@pytest.fixture
def sample_language():
    """
    サンプル言語設定のフィクスチャ

    Returns:
        str: テスト用の言語設定（デフォルト: "ja"）
    """
    return "ja"


# ==============================================================================
# Agent Fixtures
# ==============================================================================


@pytest.fixture
def mock_memory_agent():
    """
    モックMemoryAgentのフィクスチャ

    Returns:
        Mock: MemoryAgentのモック
    """
    from unittest.mock import Mock, AsyncMock

    agent = Mock()
    agent.process_memory_query = AsyncMock(
        return_value={
            "answer": "テスト回答",
            "emotion": "neutral",
            "metadata": {"status": "success"},
        }
    )
    return agent
