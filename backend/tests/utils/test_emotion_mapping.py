"""Tests for backend.utils.emotion_mapping — VRM emotion mapping."""

from backend.utils.emotion_mapping import EmotionMapping


class TestMapToExpression:
    def test_direct_mapping(self):
        assert EmotionMapping.map_to_expression("happy") == "happy"

    def test_alias_mapping(self):
        assert EmotionMapping.map_to_expression("excited") == "happy"
        assert EmotionMapping.map_to_expression("helpful") == "happy"

    def test_unknown_returns_neutral(self):
        assert EmotionMapping.map_to_expression("nonexistent") == "neutral"

    def test_none_returns_neutral(self):
        assert EmotionMapping.map_to_expression(None) == "neutral"

    def test_empty_returns_neutral(self):
        assert EmotionMapping.map_to_expression("") == "neutral"

    def test_case_insensitive(self):
        assert EmotionMapping.map_to_expression("HAPPY") == "happy"


class TestGetAnimationForEmotion:
    def test_happy_animation(self):
        assert EmotionMapping.get_animation_for_emotion("happy") == "greeting"

    def test_sad_animation(self):
        assert EmotionMapping.get_animation_for_emotion("sad") == "thinking"


class TestGetIntensityForEmotion:
    def test_happy_intensity(self):
        assert EmotionMapping.get_intensity_for_emotion("happy") == 1.0

    def test_unknown_alias_intensity(self):
        assert EmotionMapping.get_intensity_for_emotion("nonexistent") == 1.0


class TestGetExpressionWithIntensity:
    def test_happy_combined(self):
        result = EmotionMapping.get_expression_with_intensity("happy")
        assert result["expression"] == "happy"
        assert result["intensity"] == 1.0

    def test_unknown_returns_neutral(self):
        result = EmotionMapping.get_expression_with_intensity("nonexistent")
        assert result["expression"] == "neutral"
        assert result["intensity"] == 1.0


class TestExtractVisemeFromLipsyncData:
    def test_valid_lipsync_data(self):
        data = [{"time": 0.0, "volume": 0.5, "mouthOpen": 0.3, "mouthShape": "A"}]
        result = EmotionMapping.extract_viseme_from_lipsync_data(data)
        assert result is not None
        assert result["name"] == "aa"
        assert result["value"] == 0.3
        assert result["transition"] == EmotionMapping.VISEME_TRANSITION_DURATION

    def test_empty_lipsync_data(self):
        assert EmotionMapping.extract_viseme_from_lipsync_data([]) is None
        assert EmotionMapping.extract_viseme_from_lipsync_data(None) is None

    def test_closed_mouth_shape(self):
        data = [{"time": 0.0, "volume": 0.0, "mouthOpen": 0.0, "mouthShape": "Closed"}]
        result = EmotionMapping.extract_viseme_from_lipsync_data(data)
        assert result is not None
        assert result["name"] == "neutral"
        assert result["value"] == 0.0
