"""
Clarification テンプレート統合テスト

clarification_templates ユーティリティがワークフローと正しく統合され、
オーケストレーターノードからインラインで適切な明確化メッセージを返すことを検証する。

テスト範囲:
- clarification_templates のカテゴリ別テンプレート応答
- 日本語/英語の両言語対応
- メタデータ構造の検証
- ワークフロー _orchestrator_node のインライン処理
"""

import os
import pytest
from backend.utils.clarification_templates import get_clarification_response


class TestMessageContent:
    """メッセージ内容の正確性テスト"""

    @pytest.mark.asyncio
    async def test_cafe_clarification_ja_content(self):
        """カフェ曖昧性解消（日本語）のメッセージ内容を確認"""
        result = get_clarification_response(category="cafe-clarification-needed", language="ja")

        response = result["response"]

        # 必須要素の確認
        assert "エンジニアカフェ" in response
        assert "サイノカフェ" in response
        assert "コワーキングスペース" in response
        assert "カフェ＆バー" in response
        assert "どちらについて" in response

    @pytest.mark.asyncio
    async def test_cafe_clarification_en_content(self):
        """カフェ曖昧性解消（英語）のメッセージ内容を確認"""
        result = get_clarification_response(category="cafe-clarification-needed", language="en")

        response = result["response"]

        # 必須要素の確認
        assert "Engineer Cafe" in response
        assert "Saino Cafe" in response
        assert "coworking space" in response
        assert "cafe & bar" in response
        assert "which one" in response.lower()

    @pytest.mark.asyncio
    async def test_meeting_room_clarification_ja_content(self):
        """会議室曖昧性解消（日本語）のメッセージ内容を確認"""
        result = get_clarification_response(
            category="meeting-room-clarification-needed",
            language="ja",
        )

        response = result["response"]

        # 必須要素の確認
        assert "有料会議室" in response
        assert "地下MTGスペース" in response
        assert "2階" in response or "2F" in response
        assert "地下1階" in response or "B1" in response
        assert "2種類" in response

    @pytest.mark.asyncio
    async def test_meeting_room_clarification_en_content(self):
        """会議室曖昧性解消（英語）のメッセージ内容を確認"""
        result = get_clarification_response(
            category="meeting-room-clarification-needed",
            language="en",
        )

        response = result["response"]

        # 必須要素の確認
        assert "Paid Meeting Rooms" in response
        assert "Basement Meeting Spaces" in response
        assert "2F" in response or "2nd floor" in response
        assert "B1" in response or "basement" in response
        assert "two types" in response.lower()


class TestClarificationTemplates:
    """clarification_templates ユニットテスト"""

    @pytest.mark.parametrize(
        "category,language,expected_keywords",
        [
            (
                "cafe-clarification-needed",
                "ja",
                ["エンジニアカフェ", "サイノカフェ", "どちらについて"],
            ),
            (
                "cafe-clarification-needed",
                "en",
                ["Engineer Cafe", "Saino Cafe", "which one"],
            ),
            (
                "meeting-room-clarification-needed",
                "ja",
                ["有料会議室", "地下MTGスペース", "2種類"],
            ),
            (
                "meeting-room-clarification-needed",
                "en",
                ["Paid Meeting Rooms", "Basement Meeting Spaces", "two types"],
            ),
            ("general-clarification-needed", "ja", ["もう少し詳しく"]),
            ("general-clarification-needed", "en", ["more details"]),
        ],
    )
    def test_template_keywords(self, category, language, expected_keywords):
        """カテゴリと言語に応じたテンプレートメッセージが正しいことを確認"""
        result = get_clarification_response(category=category, language=language)
        response = result["response"]

        for keyword in expected_keywords:
            assert keyword in response, f"Keyword '{keyword}' not found in response"

        # 感情タグが付与されていることを確認
        assert response.startswith("[surprised]"), "Emotion tag not found"

    @pytest.mark.parametrize(
        "category,language",
        [
            ("cafe-clarification-needed", "ja"),
            ("cafe-clarification-needed", "en"),
            ("meeting-room-clarification-needed", "ja"),
            ("meeting-room-clarification-needed", "en"),
            ("general-clarification-needed", "ja"),
            ("general-clarification-needed", "en"),
        ],
    )
    def test_emotion_tag_always_surprised(self, category, language):
        """すべての応答に[surprised]タグが付与されることを確認"""
        result = get_clarification_response(category=category, language=language)
        assert result["emotion"] == "surprised"
        assert result["response"].startswith("[surprised]")

    @pytest.mark.parametrize(
        "category,expected_confidence",
        [
            ("cafe-clarification-needed", 0.9),
            ("meeting-room-clarification-needed", 0.9),
            ("general-clarification-needed", 0.7),
        ],
    )
    def test_metadata_structure(self, category, expected_confidence):
        """メタデータが正しく設定されることを確認"""
        result = get_clarification_response(category=category, language="ja")
        metadata = result["metadata"]

        assert metadata["agent"] == "ClarificationAgent"
        assert metadata["confidence"] == expected_confidence
        assert metadata["category"] == category
        assert metadata["sources"] == ["clarification_system"]

    def test_unknown_category_fallback(self):
        """未知のカテゴリが general-clarification-needed にフォールバックされる"""
        # 型チェック回避で直接呼ぶ
        result = get_clarification_response(
            category="unknown-category",  # type: ignore[arg-type]
            language="ja",
        )

        assert result["response"] is not None
        assert result["emotion"] == "surprised"
        assert result["metadata"]["confidence"] == 0.7

    def test_language_difference(self):
        """言語によってメッセージが異なることを確認"""
        result_ja = get_clarification_response(category="cafe-clarification-needed", language="ja")
        result_en = get_clarification_response(category="cafe-clarification-needed", language="en")

        assert result_ja["response"] != result_en["response"]


class TestClarificationIntegration:
    """ワークフローとの統合テスト（オーケストレーターのインライン処理）"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        os.environ["OPENROUTER_API_KEY"] = "test_dummy_api_key_for_testing"

        from backend.workflows.main_workflow import MainWorkflow

        self.workflow = MainWorkflow()

    @pytest.mark.asyncio
    async def test_full_workflow_with_clarification(self):
        """Clarificationを含む完全なワークフローのテスト"""
        result = await self.workflow.ainvoke(
            {"query": "カフェの営業時間は？", "session_id": "test_session", "language": "ja"}
        )

        # OrchestratorAgentがルーティング先を決定
        assert result["answer"] is not None

        # ClarificationAgentにルーティングされた場合のみ確認
        metadata = result.get("metadata", {})
        if metadata.get("requires_followup"):
            assert "[surprised]" in result["answer"]
            assert result["emotion"] == "surprised"
            assert "clarification" in metadata
