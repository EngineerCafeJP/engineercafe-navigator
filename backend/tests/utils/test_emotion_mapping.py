"""Tests for backend.utils.emotion_mapping — VRM emotion mapping."""

from typing import get_args

from backend.utils.emotion_mapping import EmotionMapping, SupportedAnimation


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

    def test_helpful_uses_emotion_row_not_only_expression(self):
        """helpful は happy 表情だが、アニメは感情キーで greeting。"""
        assert EmotionMapping.get_animation_for_emotion("helpful") == "greeting"

    def test_angry_maps_to_supported_talking(self):
        assert EmotionMapping.get_animation_for_emotion("angry") == "talking"

    def test_surprised_emotion_maps_to_surprised_animation(self):
        assert EmotionMapping.get_animation_for_emotion("surprised") == "surprised"

    def test_animation_map_values_are_supported_animation(self):
        allowed = set(get_args(SupportedAnimation))
        assert set(EmotionMapping.ANIMATION_MAP.values()) <= allowed

    def test_unknown_emotion_returns_default_animation(self):
        assert EmotionMapping.get_animation_for_emotion("unknown_emotion") == "idle"
        assert EmotionMapping.get_animation_for_emotion("") == "idle"
        assert EmotionMapping.get_animation_for_emotion(None) == "idle"

    def test_expression_map_aliases_all_have_animation_entry(self):
        missing = set(EmotionMapping.EXPRESSION_MAP) - set(EmotionMapping.ANIMATION_MAP)
        assert not missing, f"ANIMATION_MAP missing keys: {missing}"


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
