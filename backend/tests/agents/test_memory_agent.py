"""
MemoryAgent のユニットテスト
"""

import os
import pytest
from unittest.mock import Mock, AsyncMock, patch

from backend.agents.memory_agent import MemoryAgent


class TestMemoryAgent:
    """MemoryAgent のテストクラス"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        os.environ["OPENROUTER_API_KEY"] = "test-api-key"

    @patch("backend.agents.memory_agent.get_llm_provider")
    @patch("backend.agents.memory_agent.get_model_config")
    def test_init_with_memory_system(self, mock_get_config, mock_get_provider):
        """メモリシステムありで初期化"""
        mock_get_config.return_value = Mock()
        mock_get_provider.return_value = Mock()
        mock_memory = Mock()

        agent = MemoryAgent(memory_system=mock_memory)

        assert agent.memory_system is mock_memory
        assert agent.provider is not None

    @patch("backend.agents.memory_agent.get_llm_provider")
    @patch("backend.agents.memory_agent.get_model_config")
    def test_init_without_memory_system(self, mock_get_config, mock_get_provider):
        """メモリシステムなしで初期化"""
        mock_get_config.return_value = Mock()
        mock_get_provider.return_value = Mock()

        agent = MemoryAgent(memory_system=None)

        assert agent.memory_system is None

    @patch("backend.agents.memory_agent.get_llm_provider")
    @patch("backend.agents.memory_agent.get_model_config")
    def test_init_without_api_key(self, mock_get_config, mock_get_provider):
        """APIキーなしで初期化（警告のみ）"""
        mock_get_config.return_value = Mock()
        mock_get_provider.side_effect = ValueError("API key not found")

        agent = MemoryAgent()

        assert agent.provider is None

    def test_detect_memory_query_type_question_history(self):
        """質問履歴タイプの判定"""
        agent = MemoryAgent.__new__(MemoryAgent)

        assert agent.detect_memory_query_type("何を聞いた？") == "question_history"
        assert agent.detect_memory_query_type("さっき質問したこと") == "question_history"
        assert agent.detect_memory_query_type("What did I ask?") == "question_history"
        assert agent.detect_memory_query_type("my previous question") == "question_history"

    def test_detect_memory_query_type_answer_history(self):
        """回答履歴タイプの判定"""
        agent = MemoryAgent.__new__(MemoryAgent)

        assert agent.detect_memory_query_type("答えは何だった？") == "answer_history"
        assert agent.detect_memory_query_type("回答を教えて") == "answer_history"
        assert agent.detect_memory_query_type("What was your answer?") == "answer_history"
        assert agent.detect_memory_query_type("What did you say?") == "answer_history"

    def test_detect_memory_query_type_other_option(self):
        """もう一つの方タイプの判定"""
        agent = MemoryAgent.__new__(MemoryAgent)

        assert agent.detect_memory_query_type("もう一つの方は？") == "other_option"
        assert agent.detect_memory_query_type("他の方を教えて") == "other_option"
        assert agent.detect_memory_query_type("The other one please") == "other_option"
        assert agent.detect_memory_query_type("What about the alternative?") == "other_option"

    def test_detect_memory_query_type_general_memory(self):
        """その他のメモリ関連タイプの判定"""
        agent = MemoryAgent.__new__(MemoryAgent)

        assert agent.detect_memory_query_type("覚えてる？") == "general_memory"
        assert agent.detect_memory_query_type("Do you remember?") == "general_memory"
        assert agent.detect_memory_query_type("前に話したこと") == "general_memory"

    def test_build_memory_prompt_question_history_ja(self):
        """質問履歴プロンプト構築（日本語）"""
        agent = MemoryAgent.__new__(MemoryAgent)

        context = {
            "context_string": (
                "ユーザー: WiFiのパスワードを教えてください\n"
                "アシスタント: WiFiのSSIDは"
                "「engnrcf-guest-5GHz」です。"
                "パスワードは受付でお渡しする名札の裏に"
                "記載しています。"
            )
        }
        prompt = agent.build_memory_prompt("何を聞いた？", context, "question_history", "ja")

        assert "エンジニアカフェのアシスタント" in prompt
        assert "過去に何を質問したか" in prompt
        assert "WiFiのパスワード" in prompt

    def test_build_memory_prompt_question_history_en(self):
        """質問履歴プロンプト構築（英語）"""
        agent = MemoryAgent.__new__(MemoryAgent)

        context = {
            "context_string": (
                "User: What's the WiFi password?\n"
                "Assistant: The SSID is 'engnrcf-guest-5GHz'."
                " The password is on the back of the name tag"
                " you receive at reception."
            )
        }
        prompt = agent.build_memory_prompt("What did I ask?", context, "question_history", "en")

        assert "Engineer Cafe assistant" in prompt
        assert "previous questions" in prompt
        assert "WiFi password" in prompt

    def test_build_memory_prompt_answer_history(self):
        """回答履歴プロンプト構築"""
        agent = MemoryAgent.__new__(MemoryAgent)

        context = {"context_string": "テスト会話"}
        prompt = agent.build_memory_prompt("答えは？", context, "answer_history", "ja")

        assert "過去の回答内容" in prompt

    def test_build_memory_prompt_other_option(self):
        """もう一つの方プロンプト構築"""
        agent = MemoryAgent.__new__(MemoryAgent)

        context = {"context_string": "テスト会話"}
        prompt = agent.build_memory_prompt("もう一つは？", context, "other_option", "ja")

        assert "もう一つの方" in prompt or "別の選択肢" in prompt

    def test_determine_emotion_no_history(self):
        """感情タグ決定（履歴なし）"""
        agent = MemoryAgent.__new__(MemoryAgent)

        context = {"recent_messages": []}
        emotion = agent._determine_emotion(context, "general_memory")

        assert emotion == "sad"

    def test_determine_emotion_other_option(self):
        """感情タグ決定（もう一つ系）"""
        agent = MemoryAgent.__new__(MemoryAgent)

        context = {"recent_messages": [{"role": "user", "content": "test"}]}
        emotion = agent._determine_emotion(context, "other_option")

        assert emotion == "happy"

    def test_determine_emotion_question_history(self):
        """感情タグ決定（質問履歴）"""
        agent = MemoryAgent.__new__(MemoryAgent)

        context = {"recent_messages": [{"role": "user", "content": "test"}]}
        emotion = agent._determine_emotion(context, "question_history")

        assert emotion == "relaxed"

    def test_determine_emotion_answer_history(self):
        """感情タグ決定（回答履歴）"""
        agent = MemoryAgent.__new__(MemoryAgent)

        context = {"recent_messages": [{"role": "user", "content": "test"}]}
        emotion = agent._determine_emotion(context, "answer_history")

        assert emotion == "relaxed"

    def test_determine_emotion_general(self):
        """感情タグ決定（一般）"""
        agent = MemoryAgent.__new__(MemoryAgent)

        context = {"recent_messages": [{"role": "user", "content": "test"}]}
        emotion = agent._determine_emotion(context, "general_memory")

        assert emotion == "neutral"

    def test_handle_no_memory_system_ja(self):
        """メモリシステムなしの処理（日本語）"""
        agent = MemoryAgent.__new__(MemoryAgent)

        result = agent._handle_no_memory_system("ja")

        assert "メモリシステムが利用できません" in result["answer"]
        assert result["emotion"] == "sad"
        assert result["metadata"]["status"] == "memory_unavailable"

    def test_handle_no_memory_system_en(self):
        """メモリシステムなしの処理（英語）"""
        agent = MemoryAgent.__new__(MemoryAgent)

        result = agent._handle_no_memory_system("en")

        assert "Memory system is not available" in result["answer"]
        assert result["emotion"] == "sad"

    def test_no_history_response_ja(self):
        """履歴なしレスポンス（日本語）"""
        agent = MemoryAgent.__new__(MemoryAgent)

        result = agent._no_history_response("ja")

        assert "会話履歴がありません" in result["answer"]
        assert result["emotion"] == "sad"
        assert result["metadata"]["status"] == "no_history"

    def test_no_history_response_en(self):
        """履歴なしレスポンス（英語）"""
        agent = MemoryAgent.__new__(MemoryAgent)

        result = agent._no_history_response("en")

        assert "don't have any conversation history" in result["answer"]
        assert result["emotion"] == "sad"

    @pytest.mark.asyncio
    @patch("backend.agents.memory_agent.get_llm_provider")
    @patch("backend.agents.memory_agent.get_model_config")
    async def test_process_memory_query_no_memory_system(self, mock_get_config, mock_get_provider):
        """メモリシステムなしでのクエリ処理"""
        mock_get_config.return_value = Mock()
        mock_get_provider.return_value = Mock()

        agent = MemoryAgent(memory_system=None)
        result = await agent.process_memory_query("何を聞いた？", "test-session", "ja")

        assert result["metadata"]["status"] == "memory_unavailable"
        assert result["emotion"] == "sad"

    @pytest.mark.asyncio
    @patch("backend.agents.memory_agent.get_llm_provider")
    @patch("backend.agents.memory_agent.get_model_config")
    async def test_process_memory_query_no_history(self, mock_get_config, mock_get_provider):
        """履歴なしでのクエリ処理"""
        mock_get_config.return_value = Mock()
        mock_get_provider.return_value = Mock()

        mock_memory = AsyncMock()
        mock_memory.get_context = AsyncMock(
            return_value={
                "recent_messages": [],
                "context_string": "",
                "inherited_request_type": None,
            }
        )

        agent = MemoryAgent(memory_system=mock_memory)
        result = await agent.process_memory_query("何を聞いた？", "test-session", "ja")

        assert result["metadata"]["status"] == "no_history"
        assert result["emotion"] == "sad"

    @pytest.mark.asyncio
    @patch("backend.agents.memory_agent.get_llm_provider")
    @patch("backend.agents.memory_agent.get_model_config")
    async def test_process_memory_query_success(self, mock_get_config, mock_get_provider):
        """成功時のクエリ処理"""
        mock_config = Mock()
        mock_get_config.return_value = mock_config

        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(
            return_value="WiFiのパスワードについて質問されていましたね。"
        )
        mock_get_provider.return_value = mock_provider

        mock_memory = AsyncMock()
        mock_memory.get_context = AsyncMock(
            return_value={
                "recent_messages": [
                    {"role": "user", "content": "WiFiのパスワードを教えてください"},
                    {
                        "role": "assistant",
                        "content": (
                            "WiFiのSSIDは「engnrcf-guest-5GHz」です。"
                            "パスワードは受付でお渡しする名札の裏に"
                            "記載しています。"
                        ),
                    },
                ],
                "context_string": (
                    "ユーザー: WiFiのパスワードを教えてください\n"
                    "アシスタント: WiFiのSSIDは"
                    "「engnrcf-guest-5GHz」です。"
                    "パスワードは受付でお渡しする名札の裏に"
                    "記載しています。"
                ),
                "inherited_request_type": "wifi",
            }
        )

        agent = MemoryAgent(memory_system=mock_memory)
        result = await agent.process_memory_query("何を聞いた？", "test-session", "ja")

        assert result["metadata"]["status"] == "success"
        assert result["metadata"]["query_type"] == "question_history"
        assert result["emotion"] == "relaxed"
        assert "WiFi" in result["answer"]

    @pytest.mark.asyncio
    @patch("backend.agents.memory_agent.get_llm_provider")
    @patch("backend.agents.memory_agent.get_model_config")
    async def test_generate_response_no_provider(self, mock_get_config, mock_get_provider):
        """プロバイダーなしでの回答生成"""
        mock_get_config.return_value = Mock()
        mock_get_provider.side_effect = ValueError("No API key")

        agent = MemoryAgent()
        result = await agent.generate_response("テストプロンプト", "ja")

        assert "回答を生成できませんでした" in result

    @pytest.mark.asyncio
    @patch("backend.agents.memory_agent.get_llm_provider")
    @patch("backend.agents.memory_agent.get_model_config")
    async def test_generate_response_error(self, mock_get_config, mock_get_provider):
        """回答生成エラー"""
        mock_config = Mock()
        mock_get_config.return_value = mock_config

        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(side_effect=Exception("API Error"))
        mock_get_provider.return_value = mock_provider

        agent = MemoryAgent()
        result = await agent.generate_response("テストプロンプト", "ja")

        assert "エラーが発生しました" in result

    @pytest.mark.asyncio
    @patch("backend.agents.memory_agent.get_llm_provider")
    @patch("backend.agents.memory_agent.get_model_config")
    async def test_close(self, mock_get_config, mock_get_provider):
        """クローズ処理"""
        mock_config = Mock()
        mock_get_config.return_value = mock_config

        mock_provider = AsyncMock()
        mock_provider.close = AsyncMock()
        mock_get_provider.return_value = mock_provider

        agent = MemoryAgent()
        await agent.close()

        mock_provider.close.assert_called_once()
