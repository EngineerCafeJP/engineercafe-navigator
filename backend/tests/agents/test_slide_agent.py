"""
SlideAgent のユニットテスト
"""

from backend.agents.slide_agent import SlideAgent


class TestSlideAgent:
    """SlideAgent のテストクラス"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        self.agent = SlideAgent()

    def test_initialization(self):
        """初期化のテスト"""
        assert self.agent.current_slide == 1
        assert self.agent.total_slides == 0
        assert self.agent.narration_data == {}

    def test_determine_character_action(self):
        """キャラクターアクション決定のテスト"""
        # greeting
        slide_data = {"narration": {"auto": "ようこそエンジニアカフェへ!"}}
        assert self.agent._determine_character_action(slide_data) == "greeting"

        # presenting
        slide_data = {"narration": {"auto": "サービスのご紹介です"}}
        assert self.agent._determine_character_action(slide_data) == "presenting"

        # explaining
        slide_data = {"narration": {"auto": "料金は以下の通りです"}}
        assert self.agent._determine_character_action(slide_data) == "explaining"

        # bowing
        slide_data = {"narration": {"auto": "ありがとうございました"}}
        assert self.agent._determine_character_action(slide_data) == "bowing"

        # neutral
        slide_data = {"narration": {"auto": "通常のナレーションです"}}
        assert self.agent._determine_character_action(slide_data) == "neutral"

    def test_extract_emotion_from_slide_content(self):
        """スライド内容から感情抽出のテスト"""
        # happy
        assert self.agent._extract_emotion_from_slide_content("ようこそ") == "happy"
        assert self.agent._extract_emotion_from_slide_content("Welcome to our cafe") == "happy"

        # confident
        assert self.agent._extract_emotion_from_slide_content("サービスのご紹介") == "confident"
        assert self.agent._extract_emotion_from_slide_content("Our service features") == "confident"

        # grateful
        assert (
            self.agent._extract_emotion_from_slide_content("ありがとうございました") == "grateful"
        )
        assert self.agent._extract_emotion_from_slide_content("Thank you very much") == "grateful"

        # neutral
        assert self.agent._extract_emotion_from_slide_content("通常の説明です") == "neutral"
        assert self.agent._extract_emotion_from_slide_content("Normal explanation") == "neutral"

    def test_handle_next_slide_at_end(self):
        """最後のスライドで次へ移動のテスト"""
        self.agent.current_slide = 5
        self.agent.total_slides = 5

        result = self.agent._handle_next_slide("ja")

        assert "最後のスライド" in result["answer"]
        assert result["emotion"] == "neutral"
        assert result["metadata"]["action"] == "next"
        assert result["slideNumber"] == 5

    def test_handle_previous_slide_at_beginning(self):
        """最初のスライドで前へ移動のテスト"""
        self.agent.current_slide = 1
        self.agent.total_slides = 5

        result = self.agent._handle_previous_slide("ja")

        assert "最初のスライド" in result["answer"]
        assert result["emotion"] == "neutral"
        assert result["metadata"]["action"] == "previous"
        assert result["slideNumber"] == 1

    def test_handle_goto_slide_out_of_range(self):
        """範囲外のスライドへ移動のテスト"""
        self.agent.total_slides = 5

        # スライド番号が小さすぎる
        result = self.agent._handle_goto_slide(0, "ja")
        assert "1から5の間で指定" in result["answer"]
        assert result["emotion"] == "neutral"

        # スライド番号が大きすぎる
        result = self.agent._handle_goto_slide(10, "ja")
        assert "1から5の間で指定" in result["answer"]
        assert result["emotion"] == "neutral"

        # 英語版
        result = self.agent._handle_goto_slide(10, "en")
        assert "between 1 and 5" in result["answer"]
        assert result["emotion"] == "neutral"


class TestSlideAgentIntegration:
    """SlideAgent の実動作統合テスト"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        self.agent = SlideAgent()

    def test_load_narration_japanese(self):
        """日本語ナレーションの読み込みテスト"""
        result = self.agent.load_narration("ja")
        assert result is True, "日本語ナレーションの読み込みに失敗"
        assert self.agent.total_slides > 0, "スライド数が0"
        assert "slides" in self.agent.narration_data
        assert len(self.agent.narration_data["slides"]) == self.agent.total_slides

    def test_load_narration_english(self):
        """英語ナレーションの読み込みテスト"""
        result = self.agent.load_narration("en")
        assert result is True, "英語ナレーションの読み込みに失敗"
        assert self.agent.total_slides > 0, "スライド数が0"
        assert "slides" in self.agent.narration_data
        assert len(self.agent.narration_data["slides"]) == self.agent.total_slides

    def test_narration_data_structure(self):
        """ナレーションデータ構造の検証"""
        self.agent.load_narration("ja")
        assert "slides" in self.agent.narration_data
        assert "metadata" in self.agent.narration_data
        assert "title" in self.agent.narration_data["metadata"]

        # 各スライドの構造を検証
        for slide in self.agent.narration_data["slides"]:
            assert "slideNumber" in slide
            assert "narration" in slide
            assert "auto" in slide["narration"]

    def test_slide_navigation_next(self):
        """次へナビゲーションの実動作テスト"""
        self.agent.load_narration("ja")
        initial_slide = self.agent.current_slide

        result = self.agent._handle_next_slide("ja")

        assert result["slideNumber"] == initial_slide + 1
        assert self.agent.current_slide == initial_slide + 1
        assert "metadata" in result
        # 正常にナビゲーションした場合は_handle_narrate_slideが呼ばれ、action="narrate"になる
        assert result["metadata"]["action"] == "narrate"

    def test_slide_navigation_previous(self):
        """前へナビゲーションの実動作テスト"""
        self.agent.load_narration("ja")
        self.agent.current_slide = 3  # 中間のスライドに設定

        result = self.agent._handle_previous_slide("ja")

        assert result["slideNumber"] == 2
        assert self.agent.current_slide == 2
        assert "metadata" in result
        # 正常にナビゲーションした場合は_handle_narrate_slideが呼ばれ、action="narrate"になる
        assert result["metadata"]["action"] == "narrate"

    def test_slide_navigation_goto(self):
        """指定スライドへの移動テスト"""
        self.agent.load_narration("ja")
        target = 3

        result = self.agent._handle_goto_slide(target, "ja")

        assert result["slideNumber"] == target
        assert self.agent.current_slide == target
        assert "metadata" in result
        # 正常にナビゲーションした場合は_handle_narrate_slideが呼ばれ、action="narrate"になる
        assert result["metadata"]["action"] == "narrate"

    def test_narrate_current_slide(self):
        """現在のスライドのナレーションテスト"""
        self.agent.load_narration("ja")
        self.agent.current_slide = 1

        result = self.agent._handle_narrate_slide(1, "ja")

        assert "answer" in result
        assert "emotion" in result
        assert "metadata" in result
        assert result["metadata"]["action"] == "narrate"
        assert result["slideNumber"] == 1

    def test_language_switching(self):
        """言語切り替えテスト"""
        # 日本語で読み込み
        ja_result = self.agent.load_narration("ja")
        ja_slides = self.agent.total_slides

        # 英語で読み込み
        en_result = self.agent.load_narration("en")
        en_slides = self.agent.total_slides

        assert ja_result is True
        assert en_result is True
        assert ja_slides == en_slides, "日本語と英語でスライド数が一致しない"

    def test_slide_boundary_conditions(self):
        """スライド境界条件のテスト"""
        self.agent.load_narration("ja")

        # 最初のスライドで前へ
        self.agent.current_slide = 1
        result = self.agent._handle_previous_slide("ja")
        assert "最初のスライド" in result["answer"]
        assert self.agent.current_slide == 1

        # 最後のスライドで次へ
        self.agent.current_slide = self.agent.total_slides
        result = self.agent._handle_next_slide("ja")
        assert "最後のスライド" in result["answer"]
        assert self.agent.current_slide == self.agent.total_slides
