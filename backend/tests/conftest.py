"""
pytest設定とフィクスチャ
"""

import pytest
from dotenv import load_dotenv

# 環境変数の読み込み
load_dotenv()


@pytest.fixture
def sample_workflow_state():
    """サンプルのワークフロー状態"""
    return {
        "messages": [],
        "query": "営業時間は何時ですか？",
        "session_id": "test-session-123",
        "language": "ja",
        "routed_to": None,
        "answer": None,
        "emotion": None,
        "metadata": {},
        "context": {}
    }


@pytest.fixture
def mock_env_vars(monkeypatch):
    """モック環境変数"""
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-supabase-key")

