"""
env_validator モジュールのテスト

validate_startup() が development / production 各環境で
正しく動作することを検証する。
"""

import logging
from unittest.mock import MagicMock, patch

import pytest

from backend.utils.env_validator import (
    REQUIRED_CORE,
    REQUIRED_PRODUCTION,
    REQUIRED_STORAGE,
    validate_startup,
)


# ============================================
# Helper: mock Settings factory
# ============================================


def _make_mock_settings(
    *,
    environment: str = "development",
    missing_keys: list[str] | None = None,
):
    """
    get_settings() の戻り値として使うモックを生成する。

    Args:
        environment: 環境名
        missing_keys: get_missing_keys が返すべきキー（None の場合は空リスト）
    """
    missing = missing_keys or []
    mock = MagicMock()
    mock.environment = environment
    mock.is_production = environment == "production"
    mock.is_test = environment == "test"
    mock.get_missing_keys.side_effect = lambda keys: [k for k in keys if k in missing]
    return mock


# ============================================
# TestConstants
# ============================================


class TestConstants:
    """定数の整合性テスト"""

    def test_required_core_contains_openrouter(self):
        """REQUIRED_CORE に openrouter_api_key が含まれる"""
        assert "openrouter_api_key" in REQUIRED_CORE

    def test_required_storage_contains_supabase_keys(self):
        """REQUIRED_STORAGE に Supabase 関連キーが含まれる"""
        assert "supabase_url" in REQUIRED_STORAGE
        assert "supabase_key" in REQUIRED_STORAGE
        assert "supabase_db_uri" in REQUIRED_STORAGE

    def test_required_production_is_core_plus_storage(self):
        """REQUIRED_PRODUCTION は CORE + STORAGE の合計"""
        assert REQUIRED_PRODUCTION == REQUIRED_CORE + REQUIRED_STORAGE

    def test_required_production_length(self):
        """REQUIRED_PRODUCTION の要素数 = CORE + STORAGE"""
        assert len(REQUIRED_PRODUCTION) == len(REQUIRED_CORE) + len(REQUIRED_STORAGE)


# ============================================
# TestValidateStartupDevelopment
# ============================================


class TestValidateStartupDevelopment:
    """development 環境での validate_startup() テスト"""

    @patch("backend.utils.env_validator.get_settings")
    def test_all_vars_set_no_warnings(self, mock_get_settings):
        """全変数が設定済み → warnings なし"""
        mock_get_settings.return_value = _make_mock_settings(
            environment="development",
            missing_keys=[],
        )
        result = validate_startup()

        assert result["missing"] == []
        assert result["warnings"] == []

    @patch("backend.utils.env_validator.get_settings")
    def test_missing_core_vars_warns_only(self, mock_get_settings):
        """コア変数が未設定 → 警告のみ（例外なし）"""
        mock_get_settings.return_value = _make_mock_settings(
            environment="development",
            missing_keys=["openrouter_api_key"],
        )
        result = validate_startup()

        assert "openrouter_api_key" in result["missing"]
        assert len(result["warnings"]) >= 1
        assert any("コア環境変数" in w for w in result["warnings"])

    @patch("backend.utils.env_validator.get_settings")
    def test_missing_storage_vars_warns_only(self, mock_get_settings):
        """ストレージ変数が未設定 → 警告のみ（例外なし）"""
        mock_get_settings.return_value = _make_mock_settings(
            environment="development",
            missing_keys=["supabase_url", "supabase_key", "supabase_db_uri"],
        )
        result = validate_startup()

        assert "supabase_url" in result["missing"]
        assert "supabase_key" in result["missing"]
        assert "supabase_db_uri" in result["missing"]
        assert len(result["warnings"]) >= 1
        assert any("ストレージ環境変数" in w for w in result["warnings"])

    @patch("backend.utils.env_validator.get_settings")
    def test_missing_both_core_and_storage_warns_only(self, mock_get_settings):
        """コアとストレージの両方が未設定 → 2 つの警告（例外なし）"""
        mock_get_settings.return_value = _make_mock_settings(
            environment="development",
            missing_keys=[
                "openrouter_api_key",
                "supabase_url",
                "supabase_key",
                "supabase_db_uri",
            ],
        )
        result = validate_startup()

        assert len(result["warnings"]) == 2
        assert any("コア環境変数" in w for w in result["warnings"])
        assert any("ストレージ環境変数" in w for w in result["warnings"])
        assert len(result["missing"]) == 4

    @patch("backend.utils.env_validator.get_settings")
    def test_does_not_raise_in_development(self, mock_get_settings):
        """development 環境では ValueError を発生させない"""
        mock_get_settings.return_value = _make_mock_settings(
            environment="development",
            missing_keys=list(REQUIRED_PRODUCTION),
        )
        # Should not raise
        result = validate_startup()
        assert len(result["missing"]) > 0


# ============================================
# TestValidateStartupProduction
# ============================================


class TestValidateStartupProduction:
    """production 環境での validate_startup() テスト"""

    @patch("backend.utils.env_validator.get_settings")
    def test_all_vars_set_success(self, mock_get_settings):
        """全変数が設定済み → 正常終了"""
        mock_get_settings.return_value = _make_mock_settings(
            environment="production",
            missing_keys=[],
        )
        result = validate_startup()

        assert result["missing"] == []
        assert result["warnings"] == []

    @patch("backend.utils.env_validator.get_settings")
    def test_missing_vars_raises_valueerror(self, mock_get_settings):
        """変数が未設定 → ValueError"""
        mock_get_settings.return_value = _make_mock_settings(
            environment="production",
            missing_keys=["openrouter_api_key", "supabase_url"],
        )
        with pytest.raises(ValueError, match="Production環境で必須環境変数が未設定"):
            validate_startup()

    @patch("backend.utils.env_validator.get_settings")
    def test_missing_single_var_raises_valueerror(self, mock_get_settings):
        """1 つだけ未設定でも ValueError"""
        mock_get_settings.return_value = _make_mock_settings(
            environment="production",
            missing_keys=["supabase_db_uri"],
        )
        with pytest.raises(ValueError, match="supabase_db_uri"):
            validate_startup()


# ============================================
# TestValidateStartupLogging
# ============================================


class TestValidateStartupLogging:
    """validate_startup() のログ出力テスト"""

    @patch("backend.utils.env_validator.get_settings")
    def test_development_missing_core_logs_warning(self, mock_get_settings, caplog):
        """development でコア変数が未設定 → WARNING ログ"""
        mock_get_settings.return_value = _make_mock_settings(
            environment="development",
            missing_keys=["openrouter_api_key"],
        )
        with caplog.at_level(logging.WARNING, logger="backend.utils.env_validator"):
            validate_startup()

        assert any("openrouter_api_key" in record.message for record in caplog.records)

    @patch("backend.utils.env_validator.get_settings")
    def test_development_all_set_logs_info(self, mock_get_settings, caplog):
        """development で全変数が設定済み → INFO ログ"""
        mock_get_settings.return_value = _make_mock_settings(
            environment="development",
            missing_keys=[],
        )
        with caplog.at_level(logging.INFO, logger="backend.utils.env_validator"):
            validate_startup()

        assert any("バリデーション OK" in record.message for record in caplog.records)

    @patch("backend.utils.env_validator.get_settings")
    def test_production_all_set_logs_info(self, mock_get_settings, caplog):
        """production で全変数が設定済み → INFO ログ"""
        mock_get_settings.return_value = _make_mock_settings(
            environment="production",
            missing_keys=[],
        )
        with caplog.at_level(logging.INFO, logger="backend.utils.env_validator"):
            validate_startup()

        assert any("production" in record.message for record in caplog.records)

    @patch("backend.utils.env_validator.get_settings")
    def test_production_missing_logs_error(self, mock_get_settings, caplog):
        """production で変数が未設定 → ERROR ログ"""
        mock_get_settings.return_value = _make_mock_settings(
            environment="production",
            missing_keys=["openrouter_api_key"],
        )
        with caplog.at_level(logging.ERROR, logger="backend.utils.env_validator"):
            with pytest.raises(ValueError):
                validate_startup()

        assert any(record.levelno == logging.ERROR for record in caplog.records)


# ============================================
# TestValidateStartupTestEnvironment
# ============================================


class TestValidateStartupTestEnvironment:
    """test 環境での validate_startup() テスト"""

    @patch("backend.utils.env_validator.get_settings")
    def test_test_environment_behaves_like_development(self, mock_get_settings):
        """test 環境は development と同様に警告のみ"""
        mock_get_settings.return_value = _make_mock_settings(
            environment="test",
            missing_keys=["openrouter_api_key"],
        )
        # Should not raise
        result = validate_startup()
        assert "openrouter_api_key" in result["missing"]
        assert len(result["warnings"]) >= 1
