"""
SlideAgent のユニットテスト
"""

from agents.slide_agent import SlideAgent


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
