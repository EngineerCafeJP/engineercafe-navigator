"""
Memory Agent骨組みテスト

骨組み実装が正常に動作することを確認するための基本的なテスト。
完全実装後は、より詳細なテストケースに置き換える。

TODO (専門エンジニア - takegg0311):
- 完全実装後のテストケース追加
- エッジケースのテスト
- 統合テストの追加
"""

import sys
from pathlib import Path

# Add backend directory to path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

import pytest  # noqa: E402

from utils.memory_interface import MemorySystemInterface, MemoryNotAvailableError  # noqa: E402
from utils.memory_helper import SimplifiedMemoryHelper, get_memory_helper  # noqa: E402
from agents.memory_agent import MemoryAgent  # noqa: E402


class TestMemoryInterface:
    """MemorySystemInterfaceのテスト"""

    def test_interface_protocol(self):
        """Protocolが正しく定義されているか確認"""
        # Protocolのメソッドが定義されているか確認
        assert hasattr(MemorySystemInterface, "get_previous_request_type")
        assert hasattr(MemorySystemInterface, "get_context")
        assert hasattr(MemorySystemInterface, "store_message")


class TestSimplifiedMemoryHelper:
    """SimplifiedMemoryHelperのテスト（骨組み）"""

    def test_initialization(self):
        """初期化が正常に動作するか確認"""
        helper = SimplifiedMemoryHelper()
        assert helper.agent_name == "langgraph_memory"
        assert helper.ttl_seconds == 180  # 3 minutes
        assert helper.max_entries == 100

    def test_singleton_instance(self):
        """シングルトンインスタンスが正しく動作するか確認"""
        instance1 = get_memory_helper()
        instance2 = get_memory_helper()
        assert instance1 is instance2  # 同じインスタンス

    def test_extract_request_type_hours(self):
        """営業時間系のリクエストタイプ抽出"""
        helper = SimplifiedMemoryHelper()
        assert helper._extract_request_type("営業時間は？") == "hours"
        assert helper._extract_request_type("What time do you open?") == "hours"

    def test_extract_request_type_price(self):
        """料金系のリクエストタイプ抽出"""
        helper = SimplifiedMemoryHelper()
        assert helper._extract_request_type("料金はいくら？") == "price"
        assert helper._extract_request_type("How much is it?") == "price"

    def test_extract_request_type_location(self):
        """場所系のリクエストタイプ抽出"""
        helper = SimplifiedMemoryHelper()
        assert helper._extract_request_type("場所はどこ？") == "location"
        assert helper._extract_request_type("Where is it?") == "location"

    def test_extract_request_type_none(self):
        """マッチしない場合はNoneを返す"""
        helper = SimplifiedMemoryHelper()
        assert helper._extract_request_type("こんにちは") is None
        assert helper._extract_request_type("Hello") is None

    @pytest.mark.asyncio
    async def test_cleanup_no_error(self):
        """クリーンアップがエラーなく実行できるか確認"""
        helper = SimplifiedMemoryHelper()
        # 骨組み実装でもエラーが出ないことを確認
        await helper.cleanup()

    @pytest.mark.asyncio
    async def test_get_memory_stats(self):
        """メモリ統計の取得（骨組み）"""
        helper = SimplifiedMemoryHelper()
        stats = await helper.get_memory_stats()
        # 骨組み実装では全て0/Noneが返る
        assert stats["active_turns"] == 0
        assert stats["oldest_turn"] is None
        assert stats["newest_turn"] is None


class TestMemoryAgent:
    """MemoryAgentのテスト（骨組み）"""

    def test_initialization_with_memory(self):
        """メモリシステムありで初期化"""
        memory_helper = SimplifiedMemoryHelper()
        agent = MemoryAgent(memory_system=memory_helper)
        assert agent.memory_system is not None

    def test_initialization_without_memory(self):
        """メモリシステムなしで初期化"""
        agent = MemoryAgent(memory_system=None)
        assert agent.memory_system is None

    @pytest.mark.asyncio
    async def test_process_query_no_memory_system(self):
        """メモリシステムなしで処理（エラーメッセージ確認）"""
        agent = MemoryAgent(memory_system=None)
        result = await agent.process_memory_query(
            query="さっき何を聞いた？", session_id="test_session", language="ja"
        )
        assert result["emotion"] == "sad"
        assert "メモリシステムが利用できません" in result["answer"]

    @pytest.mark.asyncio
    async def test_process_query_with_memory_system(self):
        """メモリシステムありで処理（骨組みプレースホルダー確認）"""
        memory_helper = SimplifiedMemoryHelper()
        agent = MemoryAgent(memory_system=memory_helper)
        result = await agent.process_memory_query(
            query="さっき何を聞いた？", session_id="test_session", language="ja"
        )
        # 骨組み実装ではプレースホルダーメッセージが返る
        assert "実装中" in result["answer"]
        assert result["metadata"]["status"] == "skeleton_implementation"

    def test_detect_memory_query_type(self):
        """メモリ関連質問タイプの判定（骨組み）"""
        agent = MemoryAgent()
        # 骨組み実装では"general_memory"が返る
        query_type = agent.detect_memory_query_type("さっき何を聞いた？")
        assert query_type == "general_memory"

    def test_determine_emotion_no_history(self):
        """履歴なしの感情タグ判定"""
        agent = MemoryAgent()
        emotion = agent._determine_emotion({"recent_messages": []}, "general_memory")
        assert emotion == "sad"

    def test_determine_emotion_with_history(self):
        """履歴ありの感情タグ判定"""
        agent = MemoryAgent()
        context = {"recent_messages": [{"role": "user", "content": "test"}]}
        emotion = agent._determine_emotion(context, "question_history")
        assert emotion == "relaxed"


class TestMemoryNotAvailableError:
    """MemoryNotAvailableErrorのテスト"""

    def test_error_can_be_raised(self):
        """エラーが正常に発生するか確認"""
        with pytest.raises(MemoryNotAvailableError):
            raise MemoryNotAvailableError("Test error")


# TODO: 完全実装後のテストケース
# - Supabase統合テスト
# - OpenRouter API統合テスト
# - 会話履歴の保存と取得の統合テスト
# - TTL（3分）の動作テスト
# - エラーハンドリングのテスト
