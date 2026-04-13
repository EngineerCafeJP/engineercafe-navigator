"""
CharacterControlAgent のユニットテスト

テスト実行方法 (backendディレクトリで実行):
    # すべてのテストを実行
    pytest tests/agents/test_character_control_agent.py

    # 特定のテストクラスのみ実行
    pytest tests/agents/test_character_control_agent.py::TestCharacterControlAgent

    # 特定のテストメソッドのみ実行
    pytest tests/agents/test_character_control_agent.py::\
TestCharacterControlAgent::test_generate_lipsync_data_basic

    # 詳細な出力で実行
    pytest tests/agents/test_character_control_agent.py -v

    # カバレッジ付きで実行
    pytest tests/agents/test_character_control_agent.py --cov=backend.agents.character_control_agent

    # プロジェクトルートから実行する場合
    cd backend && pytest tests/agents/test_character_control_agent.py
"""

import pytest
from unittest.mock import patch
from backend.agents.character_control_agent import CharacterControlAgent
from backend.utils.emotion_mapping import EmotionMapping


class TestCharacterControlAgent:
    """CharacterControlAgent のテストクラス"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        self.agent = CharacterControlAgent()

    # ==========================================================================
    # 初期化テスト
    # ==========================================================================

    def test_initialization_default(self):
        """デフォルト設定での初期化テスト"""
        agent = CharacterControlAgent()
        assert agent.current_expression == "neutral"
        assert agent.current_intensity == 1.0
        assert agent.current_expression_duration == 2.0
        assert agent.current_animation == "idle"
        assert agent._kanji_converter is not None

    def test_initialization_default_values(self):
        """デフォルト値の確認"""
        assert self.agent.DEFAULT_EXPRESSION == "neutral"
        assert self.agent.DEFAULT_INTENSITY == 1.0
        assert self.agent.DEFAULT_EXPRESSION_DURATION == 2.0
        assert self.agent.DEFAULT_ANIMATION == "idle"

    # ==========================================================================
    # 感情→表情マッピングテスト
    # ==========================================================================

    def test_map_emotion_to_expression_happy(self):
        """happy感情のマッピング"""
        result = self.agent.map_emotion_to_expression("happy")
        assert result["expression"] == "happy"
        assert 0.0 <= result["intensity"] <= 1.0
        assert result["duration"] == 2.0

    def test_map_emotion_to_expression_sad(self):
        """sad感情のマッピング"""
        result = self.agent.map_emotion_to_expression("sad")
        assert result["expression"] == "sad"
        assert 0.0 <= result["intensity"] <= 1.0
        assert result["duration"] == 2.0

    def test_map_emotion_to_expression_neutral(self):
        """neutral感情のマッピング"""
        result = self.agent.map_emotion_to_expression("neutral")
        assert result["expression"] == "neutral"
        assert 0.0 <= result["intensity"] <= 1.0

    def test_map_emotion_to_expression_excited(self):
        """excited感情のマッピング（happyにマッピングされる）"""
        result = self.agent.map_emotion_to_expression("excited")
        assert result["expression"] == "happy"
        assert 0.0 <= result["intensity"] <= 1.0

    def test_map_emotion_to_expression_invalid_none(self):
        """無効な感情値（None）の処理"""
        result = self.agent.map_emotion_to_expression(None)
        assert result["expression"] == "neutral"
        assert 0.0 <= result["intensity"] <= 1.0

    def test_map_emotion_to_expression_invalid_empty(self):
        """無効な感情値（空文字列）の処理"""
        result = self.agent.map_emotion_to_expression("")
        assert result["expression"] == "neutral"

    def test_map_emotion_to_expression_invalid_type(self):
        """無効な感情値（型エラー）の処理"""
        result = self.agent.map_emotion_to_expression(123)
        assert result["expression"] == "neutral"

    def test_map_emotion_to_expression_unknown(self):
        """未知の感情値の処理"""
        result = self.agent.map_emotion_to_expression("unknown_emotion")
        assert result["expression"] == "neutral"

    # ==========================================================================
    # アニメーション選択テスト
    # ==========================================================================

    def test_select_animation_happy(self):
        """happy感情のアニメーション選択"""
        animation = self.agent.select_animation("happy")
        assert animation == "greeting"

    def test_select_animation_sad(self):
        """sad感情のアニメーション選択"""
        animation = self.agent.select_animation("sad")
        assert animation == "thinking"

    def test_select_animation_neutral(self):
        """neutral感情のアニメーション選択"""
        animation = self.agent.select_animation("neutral")
        assert animation == "idle"

    def test_select_animation_angry(self):
        """angry感情のアニメーション選択（SupportedAnimation: talking）"""
        animation = self.agent.select_animation("angry")
        assert animation == "talking"

    def test_select_animation_surprised(self):
        """surprised感情のアニメーション選択（SupportedAnimation: surprised）"""
        animation = self.agent.select_animation("surprised")
        assert animation == "surprised"

    def test_select_animation_relaxed(self):
        """relaxed感情のアニメーション選択"""
        animation = self.agent.select_animation("relaxed")
        assert animation == "thinking"

    def test_select_animation_invalid_none(self):
        """無効な感情値（None）のアニメーション選択"""
        animation = self.agent.select_animation(None)
        assert animation == "idle"

    def test_select_animation_invalid_empty(self):
        """無効な感情値（空文字列）のアニメーション選択"""
        animation = self.agent.select_animation("")
        assert animation == "idle"

    def test_select_animation_with_context(self):
        """コンテキスト付きアニメーション選択（将来の拡張用）"""
        context = {"some_key": "some_value"}
        animation = self.agent.select_animation("happy", context)
        assert animation == "greeting"
        # 現時点ではcontextは未使用だが、エラーにならないことを確認

    # ==========================================================================
    # VRM制御コマンド生成テスト
    # ==========================================================================

    def test_generate_vrm_command_basic(self):
        """基本的なVRM制御コマンド生成"""
        cmd = self.agent.generate_vrm_command("happy", 0.8)

        assert "expressions" in cmd
        assert "lookAt" in cmd
        assert "humanoid" in cmd
        assert len(cmd["expressions"]) == 1
        assert cmd["expressions"][0]["name"] == "happy"
        assert cmd["expressions"][0]["value"] == 0.8
        assert cmd["expressions"][0]["transition"] == 2.0

    def test_generate_vrm_command_with_animation(self):
        """アニメーション付きVRM制御コマンド生成"""
        cmd = self.agent.generate_vrm_command("happy", 0.8, "greeting")
        assert cmd["humanoid"]["pose"] == "greeting"

    def test_generate_vrm_command_without_animation(self):
        """アニメーションなしVRM制御コマンド生成"""
        cmd = self.agent.generate_vrm_command("happy", 0.8, None)
        assert cmd["humanoid"]["pose"] is None

    def test_generate_vrm_command_lookat_default(self):
        """lookAt設定のデフォルト値確認"""
        cmd = self.agent.generate_vrm_command("happy", 0.8)
        assert cmd["lookAt"]["position"]["x"] == 0
        assert cmd["lookAt"]["position"]["y"] == 1.5
        assert cmd["lookAt"]["position"]["z"] == 2.0
        assert cmd["lookAt"]["target"] == "camera"

    def test_generate_vrm_command_intensity_range_upper(self):
        """強度値の上限チェック（1.0を超える値）"""
        cmd = self.agent.generate_vrm_command("happy", 2.0)
        assert 0.0 <= cmd["expressions"][0]["value"] <= 1.0

    def test_generate_vrm_command_intensity_range_lower(self):
        """強度値の下限チェック（0.0未満の値）"""
        cmd = self.agent.generate_vrm_command("happy", -1.0)
        assert 0.0 <= cmd["expressions"][0]["value"] <= 1.0

    def test_generate_vrm_command_invalid_expression_none(self):
        """無効な表情名（None）の処理"""
        cmd = self.agent.generate_vrm_command(None, 0.8)
        assert cmd["expressions"][0]["name"] == "neutral"

    def test_generate_vrm_command_invalid_expression_empty(self):
        """無効な表情名（空文字列）の処理"""
        cmd = self.agent.generate_vrm_command("", 0.8)
        assert cmd["expressions"][0]["name"] == "neutral"

    def test_generate_vrm_command_invalid_intensity_type(self):
        """無効な強度値（型エラー）の処理"""
        cmd = self.agent.generate_vrm_command("happy", "invalid")
        assert isinstance(cmd["expressions"][0]["value"], (int, float))
        assert 0.0 <= cmd["expressions"][0]["value"] <= 1.0

    # ==========================================================================
    # リップシンクデータ生成テスト
    # ==========================================================================

    def test_generate_lipsync_data_basic(self):
        """基本的なリップシンクデータ生成"""
        data = self.agent.generate_lipsync_data("Hello", audio_duration=1.0)

        assert len(data) > 0
        assert "time" in data[0]
        assert "volume" in data[0]
        assert "mouthOpen" in data[0]
        assert "mouthShape" in data[0]
        assert data[0]["mouthShape"] in ["A", "I", "U", "E", "O", "Closed"]

    def test_generate_lipsync_data_japanese(self):
        """日本語テキストのリップシンクデータ生成"""
        data = self.agent.generate_lipsync_data("こんにちは", audio_duration=1.0)
        assert len(data) > 0
        assert data[0]["mouthShape"] in ["A", "I", "U", "E", "O", "Closed"]

    def test_generate_lipsync_data_frame_structure(self):
        """リップシンクデータのフレーム構造確認"""
        data = self.agent.generate_lipsync_data("Hello", audio_duration=0.5)
        assert len(data) > 0

        for frame in data:
            assert "time" in frame
            assert "volume" in frame
            assert "mouthOpen" in frame
            assert "mouthShape" in frame
            assert isinstance(frame["time"], (int, float))
            assert 0.0 <= frame["volume"] <= 1.0
            assert 0.0 <= frame["mouthOpen"] <= 1.0

    def test_generate_lipsync_data_invalid_duration_negative(self):
        """無効な音声長（負の値）の処理"""
        data = self.agent.generate_lipsync_data("Hello", audio_duration=-1.0)
        assert len(data) > 0  # フォールバック実装が動作

    def test_generate_lipsync_data_invalid_duration_zero(self):
        """無効な音声長（0）の処理"""
        data = self.agent.generate_lipsync_data("Hello", audio_duration=0.0)
        assert len(data) > 0  # フォールバック実装が動作

    def test_generate_lipsync_data_invalid_text_empty(self):
        """無効なテキスト（空文字列）の処理"""
        data = self.agent.generate_lipsync_data("", audio_duration=1.0)
        assert len(data) > 0  # フォールバック実装が動作

    def test_generate_lipsync_data_invalid_text_none(self):
        """無効なテキスト（None）の処理"""
        data = self.agent.generate_lipsync_data(None, audio_duration=1.0)
        assert len(data) > 0  # フォールバック実装が動作

    def test_generate_lipsync_data_long_duration(self):
        """長い音声長のリップシンクデータ生成"""
        data = self.agent.generate_lipsync_data("Hello World", audio_duration=5.0)
        assert len(data) > 0
        # フレーム数は duration / 0.05 に比例
        assert len(data) >= 50  # 5.0秒 / 0.05 = 100フレーム以上

    # ==========================================================================
    # processメソッドの統合テスト
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_process_basic(self):
        """基本的なprocess処理"""
        result = await self.agent.process("happy")

        assert result["name"] == "greeting"
        assert "keyframes" in result
        assert len(result["keyframes"]) > 0
        assert "happy" in result["keyframes"][0]["expressions"]

    @pytest.mark.asyncio
    async def test_process_with_text(self):
        """テキスト付きprocess処理"""
        result = await self.agent.process("happy", "こんにちは")

        assert result["name"] == "greeting"
        assert result["text"] == "こんにちは"
        assert "keyframes" in result

    @pytest.mark.asyncio
    async def test_process_with_lipsync(self):
        """リップシンク付きprocess処理"""
        result = await self.agent.process("happy", "こんにちは", 1.0)

        assert result["name"] == "greeting"
        assert result["text"] == "こんにちは"
        # keyframes内のexpressionsにVisemeが含まれるか確認
        viseme_names = ["aa", "ih", "ou", "ee", "oh", "neutral"]
        has_viseme = any(
            name in kf["expressions"] for kf in result["keyframes"] for name in viseme_names
        )
        assert has_viseme

    @pytest.mark.asyncio
    async def test_process_with_animation(self):
        """アニメーション名（name）のprocess処理"""
        result = await self.agent.process("happy")

        assert result["name"] == "greeting"

    @pytest.mark.asyncio
    async def test_process_different_emotions(self):
        """異なる感情でのprocess処理"""
        emotions = ["happy", "sad", "neutral", "angry", "surprised", "relaxed"]

        for emotion in emotions:
            result = await self.agent.process(emotion)
            assert "name" in result
            assert "keyframes" in result
            assert len(result["keyframes"]) > 0

    @pytest.mark.asyncio
    async def test_process_error_handling_invalid_emotion(self):
        """無効な感情値でのエラーハンドリング"""
        result = await self.agent.process(None)
        assert "name" in result
        assert "keyframes" in result
        assert "error" not in result  # エラー時も正常な構造を返す

    @pytest.mark.asyncio
    async def test_process_with_context(self):
        """コンテキスト付きprocess処理"""
        context = {"some_key": "some_value"}
        result = await self.agent.process("happy", context=context)
        assert result["name"] == "greeting"

    # ==========================================================================
    # エラーハンドリングテスト
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_process_exception_handling(self):
        """processメソッドの例外処理"""
        # EmotionMappingが例外を投げる場合をモック化
        with patch.object(
            EmotionMapping, "get_expression_with_intensity", side_effect=Exception("Test error")
        ):
            result = await self.agent.process("happy")
            # エラー時もデフォルト値を返す（新形式）
            assert "name" in result
            assert "keyframes" in result

    def test_map_emotion_to_expression_exception_handling(self):
        """map_emotion_to_expressionの例外処理"""
        with patch.object(
            EmotionMapping, "get_expression_with_intensity", side_effect=Exception("Test error")
        ):
            result = self.agent.map_emotion_to_expression("happy")
            # エラー時もデフォルト値を返す
            assert result["expression"] == "neutral"
            assert 0.0 <= result["intensity"] <= 1.0

    def test_select_animation_exception_handling(self):
        """select_animationの例外処理"""
        with patch.object(
            EmotionMapping, "get_animation_for_emotion", side_effect=Exception("Test error")
        ):
            animation = self.agent.select_animation("happy")
            # エラー時もデフォルト値を返す
            assert animation == "idle"

    def test_generate_vrm_command_exception_handling(self):
        """generate_vrm_commandの例外処理"""
        # 例外が発生してもデフォルト値を返すことを確認
        # builtins.max をモックするとログフォーマッター内でも max() が呼ばれ無限再帰が発生するため、
        # float() をモックして例外を発生させる
        with patch("builtins.float", side_effect=Exception("Test error")):
            cmd = self.agent.generate_vrm_command("happy", 0.8)
            assert "expressions" in cmd
            assert cmd["expressions"][0]["name"] == "neutral"

    # ==========================================================================
    # エッジケーステスト
    # ==========================================================================

    def test_combine_emotions_single(self):
        """単一感情の統合"""
        result = self.agent.combine_emotions(["happy"])
        assert result == "happy"

    def test_combine_emotions_multiple(self):
        """複数感情の統合（現時点では最初の感情を返す）"""
        result = self.agent.combine_emotions(["happy", "sad", "excited"])
        assert result == "happy"  # 現時点では最初の感情を返す

    def test_combine_emotions_empty(self):
        """空の感情リストの統合"""
        result = self.agent.combine_emotions([])
        assert result == "neutral"

    @pytest.mark.asyncio
    async def test_process_no_text_no_audio(self):
        """テキストも音声もないprocess処理"""
        result = await self.agent.process("happy")
        assert result["name"] == "greeting"
        assert "text" not in result or result.get("text") is None
        # キーフレームは1件のみ（lipsyncなし）
        assert len(result["keyframes"]) == 1
        # メイン表情のみ（Visemeなし）
        expressions = result["keyframes"][0]["expressions"]
        viseme_count = sum(1 for k in expressions if k in ["aa", "ih", "ou", "ee", "oh"])
        assert viseme_count == 0

    @pytest.mark.asyncio
    async def test_process_text_without_audio_duration(self):
        """テキストはあるが音声長がないprocess処理"""
        result = await self.agent.process("happy", "こんにちは", None)
        assert result["name"] == "greeting"
        assert result["text"] == "こんにちは"
        # 音声長がない場合、文字数から自動計算されるため、keyframesが生成される
        assert len(result["keyframes"]) >= 1

    # ==========================================================================
    # 統合テスト
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """完全なワークフローのテスト"""
        # 1. 感情→表情マッピング
        expression_params = self.agent.map_emotion_to_expression("happy")
        assert expression_params["expression"] == "happy"

        # 2. アニメーション選択
        animation = self.agent.select_animation("happy")
        assert animation == "greeting"

        # 3. VRM制御コマンド生成（generate_vrm_commandは残存）
        vrm_command = self.agent.generate_vrm_command(
            expression_params["expression"], expression_params["intensity"], animation
        )
        assert vrm_command["expressions"][0]["name"] == "happy"
        assert vrm_command["humanoid"]["pose"] == "greeting"

        # 4. リップシンクデータ生成
        lipsync_data = self.agent.generate_lipsync_data("Hello", audio_duration=1.0)
        assert len(lipsync_data) > 0

        # 5. processメソッドで統合（greetings.json形式）
        result = await self.agent.process("happy", "Hello", 1.0)
        assert result["name"] == "greeting"
        assert result["text"] == "Hello"
        assert len(result["keyframes"]) > 1  # 表情 + Viseme含む複数フレーム
