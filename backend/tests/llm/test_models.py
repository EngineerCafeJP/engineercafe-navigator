"""
backend.llm.models モジュールのユニットテスト

SupportedModel enum、ModelConfig dataclass、MODEL_CONFIGS 辞書、
および get_model_config 関数の網羅的なテストを提供する。
"""

import pytest
from enum import Enum

from backend.llm.models import (
    ModelConfig,
    MODEL_CONFIGS,
    SupportedModel,
    get_model_config,
)

# ---------------------------------------------------------------------------
# SupportedModel Enum テスト
# ---------------------------------------------------------------------------


class TestSupportedModel:
    """SupportedModel enum のテストクラス"""

    def test_enum_is_str_subclass(self):
        """SupportedModel は str のサブクラスであること"""
        assert issubclass(SupportedModel, str)

    def test_enum_is_enum_subclass(self):
        """SupportedModel は Enum のサブクラスであること"""
        assert issubclass(SupportedModel, Enum)

    def test_enum_member_count(self):
        """SupportedModel は 25 個のメンバーを持つこと"""
        assert len(SupportedModel) == 25

    def test_enum_member_is_str_instance(self):
        """各メンバーは str インスタンスであること"""
        for member in SupportedModel:
            assert isinstance(member, str)
            assert isinstance(member.value, str)

    @pytest.mark.parametrize(
        "name, expected_value",
        [
            ("GEMINI_3_1_FLASH_LITE", "google/gemini-3.1-flash-lite-preview"),
            ("GEMINI_3_FLASH", "google/gemini-3-flash-preview"),
            ("GEMINI_2_5_FLASH_LITE", "google/gemini-2.5-flash-lite"),
            ("GEMINI_3_1_PRO", "google/gemini-3.1-pro-preview"),
            ("GEMINI_3_PRO", "google/gemini-3-pro-preview"),
            ("GEMINI_2_5_PRO", "google/gemini-2.5-pro"),
            ("GPT_5_5", "openai/gpt-5.5"),
            ("GPT_5_4", "openai/gpt-5.4"),
            ("GPT_5_4_MINI", "openai/gpt-5.4-mini"),
            ("GPT_5_4_NANO", "openai/gpt-5.4-nano"),
            ("GPT_5_2", "openai/gpt-5.2"),
            ("GPT_5_MINI", "openai/gpt-5-mini"),
            ("GPT_5_1", "openai/gpt-5.1-chat"),
            ("CLAUDE_SONNET_4_6", "anthropic/claude-sonnet-4.6"),
            ("CLAUDE_OPUS_4_5", "anthropic/claude-opus-4.5"),
            ("CLAUDE_HAIKU_4_5", "anthropic/claude-haiku-4.5"),
            ("CLAUDE_SONNET_4", "anthropic/claude-sonnet-4"),
            ("CLAUDE_3_5_SONNET", "anthropic/claude-3.5-sonnet"),
            ("LLAMA_3_3_NEMOTRON", "nvidia/llama-3.3-nemotron-super-49b-v1.5"),
            ("LLAMA_3_2_90B", "meta-llama/llama-3.2-90b-vision-instruct"),
            ("LLAMA_3_1_70B", "meta-llama/llama-3.1-70b-instruct"),
            ("MISTRAL_LARGE", "mistralai/mistral-large-2512"),
            ("MISTRAL_SMALL", "mistralai/mistral-small-creative"),
            ("DEVSTRAL", "mistralai/devstral-2512"),
            ("GPT_4_1_NANO", "openai/gpt-4.1-nano"),
        ],
    )
    def test_enum_values_are_correct(self, name: str, expected_value: str):
        """各 enum メンバーの値が正しいモデル ID 文字列であること"""
        member = SupportedModel[name]
        assert member.value == expected_value

    def test_enum_member_can_be_used_as_string(self):
        """enum メンバーが文字列として直接使用できること（str 継承のため）"""
        model = SupportedModel.GEMINI_3_1_FLASH_LITE
        assert model.startswith("google/")
        assert "gemini" in model

    def test_enum_lookup_by_value(self):
        """値から enum メンバーを逆引きできること"""
        member = SupportedModel("openai/gpt-5-mini")
        assert member is SupportedModel.GPT_5_MINI

    def test_enum_lookup_invalid_value_raises(self):
        """存在しない値での逆引きは ValueError を送出すること"""
        with pytest.raises(ValueError):
            SupportedModel("nonexistent/model")


# ---------------------------------------------------------------------------
# ModelConfig Dataclass テスト
# ---------------------------------------------------------------------------


class TestModelConfig:
    """ModelConfig dataclass のテストクラス"""

    def test_creation_with_defaults(self):
        """デフォルト値で ModelConfig を作成できること"""
        config = ModelConfig(model_id=SupportedModel.GPT_5_MINI)
        assert config.model_id == SupportedModel.GPT_5_MINI
        assert config.temperature == 0.7
        assert config.max_tokens == 2048
        assert config.top_p == 0.9
        assert config.fallback_model is None
        assert config.timeout == 30.0
        assert config.input_cost_per_1k == 0.0
        assert config.output_cost_per_1k == 0.0

    def test_creation_with_all_fields(self):
        """全フィールドを指定して ModelConfig を作成できること"""
        config = ModelConfig(
            model_id=SupportedModel.CLAUDE_SONNET_4_6,
            temperature=0.5,
            max_tokens=4096,
            top_p=0.8,
            fallback_model=SupportedModel.GPT_5_MINI,
            timeout=60.0,
            input_cost_per_1k=0.003,
            output_cost_per_1k=0.015,
        )
        assert config.model_id == SupportedModel.CLAUDE_SONNET_4_6
        assert config.temperature == 0.5
        assert config.max_tokens == 4096
        assert config.top_p == 0.8
        assert config.fallback_model == SupportedModel.GPT_5_MINI
        assert config.timeout == 60.0
        assert config.input_cost_per_1k == 0.003
        assert config.output_cost_per_1k == 0.015

    def test_creation_with_fallback_model(self):
        """fallback_model を設定した ModelConfig が正しく作成されること"""
        config = ModelConfig(
            model_id=SupportedModel.GEMINI_3_1_FLASH_LITE,
            fallback_model=SupportedModel.GEMINI_2_5_FLASH_LITE,
        )
        assert config.fallback_model == SupportedModel.GEMINI_2_5_FLASH_LITE
        assert config.fallback_model is not None

    # --- temperature バリデーション ---

    def test_temperature_at_lower_boundary(self):
        """temperature=0.0（下限）で ModelConfig を作成できること"""
        config = ModelConfig(model_id=SupportedModel.GPT_5_MINI, temperature=0.0)
        assert config.temperature == 0.0

    def test_temperature_at_upper_boundary(self):
        """temperature=2.0（上限）で ModelConfig を作成できること"""
        config = ModelConfig(model_id=SupportedModel.GPT_5_MINI, temperature=2.0)
        assert config.temperature == 2.0

    def test_temperature_below_range_raises_value_error(self):
        """temperature が 0.0 未満の場合 ValueError を送出すること"""
        with pytest.raises(ValueError, match="Temperature must be between 0.0 and 2.0"):
            ModelConfig(model_id=SupportedModel.GPT_5_MINI, temperature=-0.1)

    def test_temperature_above_range_raises_value_error(self):
        """temperature が 2.0 を超える場合 ValueError を送出すること"""
        with pytest.raises(ValueError, match="Temperature must be between 0.0 and 2.0"):
            ModelConfig(model_id=SupportedModel.GPT_5_MINI, temperature=2.1)

    # --- max_tokens バリデーション ---

    def test_max_tokens_minimum_valid(self):
        """max_tokens=1（最小有効値）で ModelConfig を作成できること"""
        config = ModelConfig(model_id=SupportedModel.GPT_5_MINI, max_tokens=1)
        assert config.max_tokens == 1

    def test_max_tokens_zero_raises_value_error(self):
        """max_tokens=0 の場合 ValueError を送出すること"""
        with pytest.raises(ValueError, match="max_tokens must be positive"):
            ModelConfig(model_id=SupportedModel.GPT_5_MINI, max_tokens=0)

    def test_max_tokens_negative_raises_value_error(self):
        """max_tokens が負数の場合 ValueError を送出すること"""
        with pytest.raises(ValueError, match="max_tokens must be positive"):
            ModelConfig(model_id=SupportedModel.GPT_5_MINI, max_tokens=-100)

    # --- top_p バリデーション ---

    def test_top_p_at_lower_boundary(self):
        """top_p=0.0（下限）で ModelConfig を作成できること"""
        config = ModelConfig(model_id=SupportedModel.GPT_5_MINI, top_p=0.0)
        assert config.top_p == 0.0

    def test_top_p_at_upper_boundary(self):
        """top_p=1.0（上限）で ModelConfig を作成できること"""
        config = ModelConfig(model_id=SupportedModel.GPT_5_MINI, top_p=1.0)
        assert config.top_p == 1.0

    def test_top_p_below_range_raises_value_error(self):
        """top_p が 0.0 未満の場合 ValueError を送出すること"""
        with pytest.raises(ValueError, match="top_p must be between 0.0 and 1.0"):
            ModelConfig(model_id=SupportedModel.GPT_5_MINI, top_p=-0.01)

    def test_top_p_above_range_raises_value_error(self):
        """top_p が 1.0 を超える場合 ValueError を送出すること"""
        with pytest.raises(ValueError, match="top_p must be between 0.0 and 1.0"):
            ModelConfig(model_id=SupportedModel.GPT_5_MINI, top_p=1.01)

    # --- cost フィールドが repr に含まれないことを確認 ---

    def test_cost_fields_not_in_repr(self):
        """input_cost_per_1k と output_cost_per_1k は repr に含まれないこと"""
        config = ModelConfig(
            model_id=SupportedModel.GPT_5_MINI,
            input_cost_per_1k=0.005,
            output_cost_per_1k=0.015,
        )
        config_repr = repr(config)
        assert "input_cost_per_1k" not in config_repr
        assert "output_cost_per_1k" not in config_repr


# ---------------------------------------------------------------------------
# MODEL_CONFIGS 辞書テスト
# ---------------------------------------------------------------------------


EXPECTED_USE_CASES = [
    "router",
    "qa_response",
    "clarification",
    "general_knowledge",
    "event_info",
    "facility_info",
    "vision",
]


class TestModelConfigs:
    """MODEL_CONFIGS 辞書のテストクラス"""

    def test_model_configs_has_expected_keys(self):
        """MODEL_CONFIGS が期待される 7 つのユースケースキーを持つこと"""
        assert set(MODEL_CONFIGS.keys()) == set(EXPECTED_USE_CASES)

    def test_model_configs_count(self):
        """MODEL_CONFIGS に 7 エントリがあること"""
        assert len(MODEL_CONFIGS) == 7

    @pytest.mark.parametrize("use_case", EXPECTED_USE_CASES)
    def test_each_config_is_model_config_instance(self, use_case: str):
        """各エントリが ModelConfig インスタンスであること"""
        assert isinstance(MODEL_CONFIGS[use_case], ModelConfig)

    @pytest.mark.parametrize("use_case", EXPECTED_USE_CASES)
    def test_each_config_has_valid_model_id(self, use_case: str):
        """各エントリの model_id が SupportedModel メンバーであること"""
        config = MODEL_CONFIGS[use_case]
        assert isinstance(config.model_id, SupportedModel)

    @pytest.mark.parametrize("use_case", EXPECTED_USE_CASES)
    def test_each_config_has_valid_fallback_model(self, use_case: str):
        """各エントリの fallback_model が SupportedModel メンバーまたは None であること"""
        config = MODEL_CONFIGS[use_case]
        if config.fallback_model is not None:
            assert isinstance(config.fallback_model, SupportedModel)

    @pytest.mark.parametrize("use_case", EXPECTED_USE_CASES)
    def test_each_config_has_non_none_fallback(self, use_case: str):
        """すべての MODEL_CONFIGS エントリが fallback_model を設定していること"""
        config = MODEL_CONFIGS[use_case]
        assert (
            config.fallback_model is not None
        ), f"use_case '{use_case}' に fallback_model が設定されていません"

    @pytest.mark.parametrize("use_case", EXPECTED_USE_CASES)
    def test_each_config_has_positive_max_tokens(self, use_case: str):
        """各エントリの max_tokens が正の整数であること"""
        config = MODEL_CONFIGS[use_case]
        assert config.max_tokens > 0

    @pytest.mark.parametrize("use_case", EXPECTED_USE_CASES)
    def test_each_config_temperature_in_range(self, use_case: str):
        """各エントリの temperature が有効範囲内であること"""
        config = MODEL_CONFIGS[use_case]
        assert 0.0 <= config.temperature <= 2.0

    @pytest.mark.parametrize("use_case", EXPECTED_USE_CASES)
    def test_each_config_top_p_in_range(self, use_case: str):
        """各エントリの top_p が有効範囲内であること"""
        config = MODEL_CONFIGS[use_case]
        assert 0.0 <= config.top_p <= 1.0

    def test_router_config_values(self):
        """router 設定が低温度・少トークンであること（一貫したルーティング判定のため）"""
        config = MODEL_CONFIGS["router"]
        assert config.model_id == SupportedModel.GEMINI_3_1_FLASH_LITE
        assert config.temperature == 0.3
        assert config.max_tokens == 256
        assert config.fallback_model == SupportedModel.GEMINI_2_5_FLASH_LITE

    def test_vision_config_values(self):
        """vision 設定が temperature=0.0 であること（決定論的認識のため）"""
        config = MODEL_CONFIGS["vision"]
        assert config.model_id == SupportedModel.GPT_4_1_NANO
        assert config.temperature == 0.0
        assert config.fallback_model == SupportedModel.GPT_5_4_NANO

    def test_general_knowledge_uses_gemini_pro(self):
        """general_knowledge が Gemini 3.1 Pro を使用すること（深い推論）"""
        config = MODEL_CONFIGS["general_knowledge"]
        assert config.model_id == SupportedModel.GEMINI_3_1_PRO
        assert config.fallback_model == SupportedModel.GEMINI_2_5_PRO

    def test_fallback_models_differ_from_primary(self):
        """各エントリの fallback_model が primary model_id と異なること"""
        for use_case, config in MODEL_CONFIGS.items():
            if config.fallback_model is not None:
                assert (
                    config.fallback_model != config.model_id
                ), f"use_case '{use_case}' の fallback_model が primary と同じです"


# ---------------------------------------------------------------------------
# get_model_config 関数テスト
# ---------------------------------------------------------------------------


class TestGetModelConfig:
    """get_model_config 関数のテストクラス"""

    @pytest.mark.parametrize("use_case", EXPECTED_USE_CASES)
    def test_returns_correct_config_for_valid_use_case(self, use_case: str):
        """有効なユースケースに対して正しい ModelConfig を返すこと"""
        config = get_model_config(use_case)
        assert config is MODEL_CONFIGS[use_case]

    def test_returns_model_config_type(self):
        """戻り値が ModelConfig インスタンスであること"""
        config = get_model_config("router")
        assert isinstance(config, ModelConfig)

    def test_unknown_use_case_raises_key_error(self):
        """存在しないユースケースで KeyError を送出すること"""
        with pytest.raises(KeyError, match="Unknown use case"):
            get_model_config("nonexistent_use_case")
