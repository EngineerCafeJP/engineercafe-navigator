"""
Tests for backend/tools/web_search.py

Testing WebSearchTool class and helper functions:
- Source class
- WebSearchTool initialization
- search() method
- _get_system_instruction()
- _extract_sources()
- format_results_with_sources()
- should_use_web_search()
- get_web_search_tool() singleton
"""

import pytest
from unittest.mock import MagicMock, patch
from backend.tools.web_search import (
    Source,
    WebSearchTool,
    get_web_search_tool,
)

# ============================================================================
# Test Source Class
# ============================================================================


class TestSource:
    """Test Source data class"""

    def test_source_creation_and_to_dict(self):
        """Test Source creation and to_dict() method"""
        source = Source(uri="https://example.com", title="Example Site")
        assert source.uri == "https://example.com"
        assert source.title == "Example Site"

        result = source.to_dict()
        assert result == {"uri": "https://example.com", "title": "Example Site"}

    def test_source_with_empty_title(self):
        """Test Source with empty title"""
        source = Source(uri="https://example.com", title="")
        assert source.uri == "https://example.com"
        assert source.title == ""

        result = source.to_dict()
        assert result == {"uri": "https://example.com", "title": ""}


# ============================================================================
# Test WebSearchTool Initialization
# ============================================================================


@pytest.fixture
def mock_genai():
    """Mock google.generativeai module"""
    with patch("backend.tools.web_search.genai") as mock:
        # Mock GenerativeModel
        mock.GenerativeModel.return_value = MagicMock()

        # Mock types
        mock.types.GenerationConfig = MagicMock(return_value={})
        mock.types.HarmCategory.HARM_CATEGORY_HATE_SPEECH = "hate_speech"
        mock.types.HarmCategory.HARM_CATEGORY_HARASSMENT = "harassment"
        mock.types.HarmBlockThreshold.BLOCK_NONE = "block_none"

        yield mock


class TestWebSearchInit:
    """Test WebSearchTool initialization"""

    def test_init_without_api_key(self, monkeypatch, caplog):
        """Test initialization without API key - should log warning"""
        # Remove API keys from environment
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_GENERATIVE_AI_API_KEY", raising=False)

        with patch("backend.tools.web_search.genai") as mock_genai:
            tool = WebSearchTool()

            # Check warning was logged
            assert any("GOOGLE_API_KEY" in record.message for record in caplog.records)
            assert any("not set" in record.message for record in caplog.records)

            # Check model is None
            assert tool.model is None
            assert tool._api_key is None

            # genai.configure should not be called
            mock_genai.configure.assert_not_called()

    def test_init_with_api_key(self, monkeypatch, mock_genai):
        """Test initialization with API key - should initialize model"""
        # Set API key
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key-123")

        tool = WebSearchTool()

        # Check API key was set
        assert tool._api_key == "test-api-key-123"

        # Check genai.configure was called
        mock_genai.configure.assert_called_once_with(api_key="test-api-key-123")

        # Check model was initialized
        mock_genai.GenerativeModel.assert_called_once_with("gemini-2.0-flash-exp")
        assert tool.model is not None


# ============================================================================
# Test WebSearchTool.search()
# ============================================================================


class TestSearch:
    """Test WebSearchTool.search() method"""

    @pytest.mark.asyncio
    async def test_search_without_api_key(self, monkeypatch):
        """Test search without API key - should return error"""
        # Remove API keys
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_GENERATIVE_AI_API_KEY", raising=False)

        with patch("backend.tools.web_search.genai"):
            tool = WebSearchTool()
            result = await tool.search("test query")

        assert result["success"] is False
        assert result["text"] == ""
        assert result["sources"] == []
        assert "GOOGLE_API_KEY" in result["error"]

    @pytest.mark.asyncio
    async def test_search_successful(self, monkeypatch, mock_genai):
        """Test successful search with mocked response"""
        # Set API key
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key-123")

        # Create mock response
        mock_response = MagicMock()
        mock_response.text = "Search result text"

        # Mock grounding metadata
        mock_web_source = MagicMock()
        mock_web_source.uri = "https://example.com"
        mock_web_source.title = "Example Title"

        mock_chunk = MagicMock()
        mock_chunk.web = mock_web_source

        mock_grounding_metadata = MagicMock()
        mock_grounding_metadata.grounding_chunks = [mock_chunk]

        mock_candidate = MagicMock()
        mock_candidate.grounding_metadata = mock_grounding_metadata

        mock_response.candidates = [mock_candidate]

        # Setup model to return mock response
        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model

        tool = WebSearchTool()
        result = await tool.search("test query", language="ja")

        # Verify result
        assert result["success"] is True
        assert result["text"] == "Search result text"
        assert len(result["sources"]) == 1
        assert result["sources"][0]["uri"] == "https://example.com"
        assert result["sources"][0]["title"] == "Example Title"

        # Verify generate_content was called with correct parameters
        mock_model.generate_content.assert_called_once()
        call_args = mock_model.generate_content.call_args
        assert "test query" in call_args[0][0]
        assert "tools" in call_args[1]
        assert call_args[1]["tools"][0] == {"google_search": {}}

    @pytest.mark.asyncio
    async def test_search_with_exception(self, monkeypatch, mock_genai):
        """Test search with exception - should return error"""
        # Set API key
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key-123")

        # Setup model to raise exception
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = Exception("API Error")
        mock_genai.GenerativeModel.return_value = mock_model

        tool = WebSearchTool()
        result = await tool.search("test query")

        assert result["success"] is False
        assert result["text"] == ""
        assert result["sources"] == []
        assert "API Error" in result["error"]


# ============================================================================
# Test _get_system_instruction()
# ============================================================================


class TestGetSystemInstruction:
    """Test _get_system_instruction() method"""

    def test_get_system_instruction_japanese(self, monkeypatch, mock_genai):
        """Test Japanese system instruction contains Japanese text"""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        tool = WebSearchTool()
        instruction = tool._get_system_instruction("ja")

        # Check for Japanese characters
        assert "日本語" in instruction or "親切" in instruction or "質問" in instruction
        assert "Google検索" in instruction or "検索" in instruction

    def test_get_system_instruction_english(self, monkeypatch, mock_genai):
        """Test English system instruction contains English text"""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        tool = WebSearchTool()
        instruction = tool._get_system_instruction("en")

        # Check for English keywords
        assert "helpful" in instruction.lower() or "assistant" in instruction.lower()
        assert "Google search" in instruction or "search" in instruction.lower()


# ============================================================================
# Test should_use_web_search()
# ============================================================================


class TestShouldUseWebSearch:
    """Test should_use_web_search() static method"""

    def test_should_use_web_search_with_keyword(self):
        """Test query with web search keyword - should return True"""
        # Japanese keyword
        assert WebSearchTool.should_use_web_search("最新のAIニュース") is True

        # English keyword
        assert WebSearchTool.should_use_web_search("latest AI news") is True

        # Other keywords
        assert WebSearchTool.should_use_web_search("今日の天気はどうですか") is True
        assert WebSearchTool.should_use_web_search("current weather") is True

    def test_should_use_web_search_without_keyword(self):
        """Test query without web search keyword - should return False"""
        # General cafe question
        assert WebSearchTool.should_use_web_search("エンジニアカフェの営業時間") is False

        # Basic question
        assert WebSearchTool.should_use_web_search("おすすめのコーヒーは？") is False

        # No keywords
        assert WebSearchTool.should_use_web_search("hello world") is False


# ============================================================================
# Test format_results_with_sources()
# ============================================================================


class TestFormatResultsWithSources:
    """Test format_results_with_sources() method"""

    def test_format_results_with_sources(self, monkeypatch, mock_genai):
        """Test formatting text with sources list"""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        tool = WebSearchTool()

        text = "Search result text"
        sources = [
            {"uri": "https://example1.com", "title": "Example 1"},
            {"uri": "https://example2.com", "title": "Example 2"},
        ]

        # Test Japanese
        result = tool.format_results_with_sources(text, sources, language="ja")
        assert "Search result text" in result
        assert "情報源:" in result
        assert "1. Example 1: https://example1.com" in result
        assert "2. Example 2: https://example2.com" in result

        # Test English
        result_en = tool.format_results_with_sources(text, sources, language="en")
        assert "Search result text" in result_en
        assert "Sources:" in result_en
        assert "1. Example 1: https://example1.com" in result_en

    def test_format_results_without_sources(self, monkeypatch, mock_genai):
        """Test formatting text without sources - should return original text"""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        tool = WebSearchTool()

        text = "Search result text"
        result = tool.format_results_with_sources(text, [], language="ja")

        # Should return original text without sources section
        assert result == text
        assert "情報源:" not in result
        assert "Sources:" not in result


# ============================================================================
# Test get_web_search_tool() Singleton
# ============================================================================


class TestGetWebSearchTool:
    """Test get_web_search_tool() singleton function"""

    def test_get_web_search_tool_singleton(self, monkeypatch, mock_genai):
        """Test get_web_search_tool returns singleton instance"""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        # Clear singleton
        import backend.tools.web_search

        backend.tools.web_search._web_search_tool_instance = None

        # Get instance twice
        tool1 = get_web_search_tool()
        tool2 = get_web_search_tool()

        # Should be the same instance
        assert tool1 is tool2
        assert isinstance(tool1, WebSearchTool)
