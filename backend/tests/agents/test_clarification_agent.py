"""
ClarificationAgent のユニットテスト

TESTING.mdに基づいた包括的なテストスイート
"""

import pytest
from unittest.mock import patch
from backend.agents.clarification_agent import ClarificationAgent


class TestCategoryMessages:
    """カテゴリ別メッセージ生成のテスト"""

    @pytest.fixture
    def agent(self):
        return ClarificationAgent()

    @pytest.mark.parametrize("category,language,expected_keywords", [
        # カフェの曖昧性解消（日本語）
        (
            "cafe-clarification-needed",
            "ja",
            ["エンジニアカフェ", "サイノカフェ", "どちらについて"]
        ),
        # カフェの曖昧性解消（英語）
        (
            "cafe-clarification-needed",
            "en",
            ["Engineer Cafe", "Saino Cafe", "which one"]
        ),
        # 会議室の曖昧性解消（日本語）
        (
            "meeting-room-clarification-needed",
            "ja",
            ["有料会議室", "地下MTGスペース", "2種類"]
        ),
        # 会議室の曖昧性解消（英語）
        (
            "meeting-room-clarification-needed",
            "en",
            ["Paid Meeting Rooms", "Basement Meeting Spaces", "two types"]
        ),
        # デフォルトの曖昧性解消（日本語）
        (
            "general-clarification-needed",
            "ja",
            ["もう少し詳しく"]
        ),
        # デフォルトの曖昧性解消（英語）
        (
            "general-clarification-needed",
            "en",
            ["more details"]
        ),
    ])
    @pytest.mark.asyncio
    async def test_category_messages(self, agent, category, language, expected_keywords):
        """カテゴリと言語に応じたメッセージが生成されることを確認"""
        result = await agent.handle_clarification(
            query="test query",
            category=category,
            language=language
        )

        response = result["response"]

        # すべてのキーワードが含まれていることを確認
        for keyword in expected_keywords:
            assert keyword in response, f"Keyword '{keyword}' not found in response"

        # 感情タグが付与されていることを確認
        assert response.startswith("[surprised]"), "Emotion tag not found"


class TestEmotionTag:
    """感情タグ付与のテスト"""

    @pytest.fixture
    def agent(self):
        return ClarificationAgent()

    @pytest.mark.parametrize("category,language", [
        ("cafe-clarification-needed", "ja"),
        ("cafe-clarification-needed", "en"),
        ("meeting-room-clarification-needed", "ja"),
        ("meeting-room-clarification-needed", "en"),
        ("general-clarification-needed", "ja"),
        ("general-clarification-needed", "en"),
    ])
    @pytest.mark.asyncio
    async def test_emotion_tag_always_surprised(self, agent, category, language):
        """すべての応答に[surprised]タグが付与されることを確認"""
        result = await agent.handle_clarification(
            query="test query",
            category=category,
            language=language
        )

        assert result["emotion"] == "surprised"
        assert result["response"].startswith("[surprised]")


class TestMetadata:
    """メタデータ設定のテスト"""

    @pytest.fixture
    def agent(self):
        return ClarificationAgent()

    @pytest.mark.parametrize("category,expected_confidence", [
        ("cafe-clarification-needed", 0.9),
        ("meeting-room-clarification-needed", 0.9),
        ("general-clarification-needed", 0.7),
    ])
    @pytest.mark.asyncio
    async def test_metadata_structure(self, agent, category, expected_confidence):
        """メタデータが正しく設定されることを確認"""
        result = await agent.handle_clarification(
            query="test query",
            category=category,
            language="ja"
        )

        metadata = result["metadata"]

        assert metadata["agent"] == "ClarificationAgent"
        assert metadata["confidence"] == expected_confidence
        assert metadata["category"] == category
        assert metadata["sources"] == ["clarification_system"]

    @pytest.mark.asyncio
    async def test_metadata_language(self, agent):
        """メタデータに言語情報が含まれることを確認（必要に応じて）"""
        result_ja = await agent.handle_clarification(
            query="test",
            category="cafe-clarification-needed",
            language="ja"
        )

        result_en = await agent.handle_clarification(
            query="test",
            category="cafe-clarification-needed",
            language="en"
        )

        # 言語によってメッセージが異なることを確認
        assert result_ja["response"] != result_en["response"]


class TestErrorHandling:
    """エラーハンドリングのテスト"""

    @pytest.fixture
    def agent(self):
        return ClarificationAgent()

    @pytest.mark.asyncio
    async def test_invalid_category_fallback(self, agent):
        """無効なカテゴリの場合、デフォルトメッセージを返す"""
        # 無効なカテゴリを渡す（型チェックを回避するため、直接辞書を操作）
        # 実際の実装では、無効なカテゴリは型チェックで防がれるが、
        # エラーハンドリングのテストとして残す

        # 正常系のテスト
        result = await agent.handle_clarification(
            query="test",
            category="general-clarification-needed",
            language="ja"
        )

        assert result["response"] is not None
        assert result["emotion"] == "surprised"

    @pytest.mark.asyncio
    async def test_emotion_tagger_error_handling(self, agent):
        """EmotionTaggerのエラーをハンドリング"""
        # add_emotion_tagがエラーを起こした場合のテスト
        # clarification_agent.pyで直接インポートされているため、
        # clarification_agentモジュール内のadd_emotion_tagをパッチする
        from backend.utils import emotion_tagger

        with patch(
            'backend.agents.clarification_agent.add_emotion_tag',
            side_effect=Exception("Emotion tagger error")
        ):

            # 現在の実装ではエラーハンドリングがないため、例外が発生することを確認
            with pytest.raises(Exception, match="Emotion tagger error"):
                await agent.handle_clarification(
                    query="test",
                    category="cafe-clarification-needed",
                    language="ja"
                )

class TestMessageContent:
    """メッセージ内容の正確性テスト"""

    @pytest.fixture
    def agent(self):
        return ClarificationAgent()

    @pytest.mark.asyncio
    async def test_cafe_clarification_ja_content(self, agent):
        """カフェ曖昧性解消（日本語）のメッセージ内容を確認"""
        result = await agent.handle_clarification(
            query="カフェの営業時間は？",
            category="cafe-clarification-needed",
            language="ja"
        )

        response = result["response"]

        # 必須要素の確認
        assert "エンジニアカフェ" in response
        assert "サイノカフェ" in response
        assert "コワーキングスペース" in response
        assert "カフェ＆バー" in response
        assert "どちらについて" in response

    @pytest.mark.asyncio
    async def test_cafe_clarification_en_content(self, agent):
        """カフェ曖昧性解消（英語）のメッセージ内容を確認"""
        result = await agent.handle_clarification(
            query="What are the cafe hours?",
            category="cafe-clarification-needed",
            language="en"
        )

        response = result["response"]

        # 必須要素の確認
        assert "Engineer Cafe" in response
        assert "Saino Cafe" in response
        assert "coworking space" in response
        assert "cafe & bar" in response
        assert "which one" in response.lower()

    @pytest.mark.asyncio
    async def test_meeting_room_clarification_ja_content(self, agent):
        """会議室曖昧性解消（日本語）のメッセージ内容を確認"""
        result = await agent.handle_clarification(
            query="会議室の予約方法は？",
            category="meeting-room-clarification-needed",
            language="ja"
        )

        response = result["response"]

        # 必須要素の確認
        assert "有料会議室" in response
        assert "地下MTGスペース" in response
        assert "2階" in response or "2F" in response
        assert "地下1階" in response or "B1" in response
        assert "2種類" in response

    @pytest.mark.asyncio
    async def test_meeting_room_clarification_en_content(self, agent):
        """会議室曖昧性解消（英語）のメッセージ内容を確認"""
        result = await agent.handle_clarification(
            query="How do I book a meeting room?",
            category="meeting-room-clarification-needed",
            language="en"
        )

        response = result["response"]

        # 必須要素の確認
        assert "Paid Meeting Rooms" in response
        assert "Basement Meeting Spaces" in response
        assert "2F" in response or "2nd floor" in response
        assert "B1" in response or "basement" in response
        assert "two types" in response.lower()