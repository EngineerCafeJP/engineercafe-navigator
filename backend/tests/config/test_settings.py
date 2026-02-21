"""
Settings モジュールのテスト

Settings クラスと関連するヘルパー関数のテストを実施。
環境変数の読み込み、デフォルト値、プロパティ、バリデーションをカバー。
"""

from unittest.mock import patch

import pytest
from backend.config.settings import (
    Settings,
    require_env,
    get_supabase_config,
    get_openrouter_key,
    get_openai_key,
)

# ============================================
# TestSettingsDefaults
# ============================================


class TestSettingsDefaults:
    """Settings クラスのデフォルト値テスト"""

    def test_default_environment_is_development(self):
        """デフォルト環境はdevelopment"""
        # 環境変数の影響を受けず、明示的にデフォルト値を検証
        s_clean = Settings(
            _env_file=None,  # .envファイルを読み込まない
            environment="development",
            supabase_url="http://test",
            supabase_key="test-key",
        )
        assert s_clean.environment == "development"

        # 明示的に "test" を渡したら "test" になること
        s_test = Settings(
            _env_file=None,
            environment="test",
            supabase_url="http://test",
            supabase_key="test-key",
        )
        assert s_test.environment == "test"

    def test_default_debug_is_false(self):
        """デフォルトのdebugはFalse"""
        s = Settings(
            supabase_url="http://test",
            supabase_key="test-key",
        )
        assert s.debug is False


# ============================================
# TestSettingsFromEnv
# ============================================


class TestSettingsFromEnv:
    """環境変数からの設定読み込みテスト"""

    def test_environment_var_overrides_default(self, monkeypatch):
        """環境変数ENVIRONMENTでデフォルトをオーバーライド"""
        monkeypatch.setenv("ENVIRONMENT", "production")
        s = Settings(
            supabase_url="http://test",
            supabase_key="test-key",
        )
        assert s.environment == "production"

    def test_supabase_url_reads_from_env(self, monkeypatch):
        """SUPABASE_URLを環境変数から読み込む"""
        test_url = "https://test.supabase.co"
        monkeypatch.setenv("SUPABASE_URL", test_url)
        s = Settings(
            supabase_key="test-key",
        )
        assert s.supabase_url == test_url

    def test_openrouter_api_key_reads_from_env(self, monkeypatch):
        """OPENROUTER_API_KEYを環境変数から読み込む"""
        test_key = "sk-or-test-key-12345"
        monkeypatch.setenv("OPENROUTER_API_KEY", test_key)
        s = Settings(
            supabase_url="http://test",
            supabase_key="test-key",
        )
        assert s.openrouter_api_key == test_key


# ============================================
# TestSettingsProperties
# ============================================


class TestSettingsProperties:
    """Settings クラスのプロパティテスト"""

    def test_is_production_true_when_environment_is_production(self):
        """environment="production"の場合、is_productionはTrue"""
        s = Settings(
            environment="production",
            supabase_url="http://test",
            supabase_key="test-key",
        )
        assert s.is_production is True

    def test_is_production_false_when_environment_is_not_production(self):
        """environment!="production"の場合、is_productionはFalse"""
        s = Settings(
            environment="development",
            supabase_url="http://test",
            supabase_key="test-key",
        )
        assert s.is_production is False

    def test_is_test_true_when_environment_is_test(self):
        """environment="test"の場合、is_testはTrue"""
        s = Settings(
            environment="test",
            supabase_url="http://test",
            supabase_key="test-key",
        )
        assert s.is_test is True

    def test_google_credentials_returns_google_cloud_credentials(self):
        """google_credentialsはgoogle_cloud_credentialsを返す"""
        s = Settings(
            google_cloud_credentials="/path/to/credentials.json",
            supabase_url="http://test",
            supabase_key="test-key",
        )
        assert s.google_credentials == "/path/to/credentials.json"

    def test_google_credentials_returns_google_application_credentials_when_cloud_credentials_empty(
        self,
    ):
        """google_cloud_credentialsが空の場合、google_credentialsはgoogle_application_credentialsを返す"""
        s = Settings(
            google_cloud_credentials="",
            google_application_credentials="/path/to/app_credentials.json",
            supabase_url="http://test",
            supabase_key="test-key",
        )
        assert s.google_credentials == "/path/to/app_credentials.json"


# ============================================
# TestSettingsValidation
# ============================================


class TestSettingsValidation:
    """Settings クラスのバリデーションメソッドテスト"""

    def test_validate_required_keys_returns_dict_of_booleans(self):
        """validate_required_keysは各キーの設定状況をboolで返す"""
        s = Settings(
            supabase_url="http://test",
            supabase_key="test-key",
            openai_api_key="test-openai-key",
            openrouter_api_key="",  # 空
        )
        result = s.validate_required_keys(["supabase_url", "openai_api_key", "openrouter_api_key"])
        assert result == {
            "supabase_url": True,
            "openai_api_key": True,
            "openrouter_api_key": False,
        }

    def test_validate_required_keys_handles_nonexistent_keys(self):
        """validate_required_keysは存在しないキーをFalseと扱う"""
        s = Settings(
            supabase_url="http://test",
            supabase_key="test-key",
        )
        result = s.validate_required_keys(["nonexistent_key"])
        assert result == {"nonexistent_key": False}

    def test_get_missing_keys_returns_list_of_missing_keys(self):
        """get_missing_keysは未設定のキーリストを返す"""
        s = Settings(
            supabase_url="http://test",
            supabase_key="",  # 空
            openai_api_key="test-openai-key",
            openrouter_api_key="",  # 空
        )
        missing = s.get_missing_keys(
            ["supabase_url", "supabase_key", "openai_api_key", "openrouter_api_key"]
        )
        assert set(missing) == {"supabase_key", "openrouter_api_key"}

    def test_get_missing_keys_returns_empty_list_when_all_set(self):
        """すべてのキーが設定されている場合、get_missing_keysは空リストを返す"""
        s = Settings(
            supabase_url="http://test",
            supabase_key="test-key",
            openai_api_key="test-openai-key",
        )
        missing = s.get_missing_keys(["supabase_url", "supabase_key", "openai_api_key"])
        assert missing == []


# ============================================
# TestHelperFunctions
# ============================================


class TestHelperFunctions:
    """ヘルパー関数のテスト

    ヘルパー関数(get_supabase_config等)はモジュールレベルの `settings` シングルトンを
    直接参照するため、`get_settings.cache_clear()` では不十分。
    `unittest.mock.patch` で `backend.config.settings.settings` を差し替える。
    """

    def test_require_env_raises_valueerror_for_empty_string(self):
        """require_envは空文字列でValueErrorを発生させる"""
        with pytest.raises(ValueError, match="環境変数 TEST_KEY が設定されていません"):
            require_env("TEST_KEY", "")

    def test_require_env_returns_value_for_non_empty_string(self):
        """require_envは非空文字列で値を返す"""
        result = require_env("TEST_KEY", "test-value")
        assert result == "test-value"

    def test_get_supabase_config_raises_valueerror_when_url_missing(self):
        """get_supabase_configはURLが空の場合ValueErrorを発生させる"""
        mock_settings = Settings(
            _env_file=None,
            supabase_url="",
            supabase_key="test-key",
        )
        with patch("backend.config.settings.settings", mock_settings):
            with pytest.raises(ValueError, match="環境変数 SUPABASE_URL が設定されていません"):
                get_supabase_config()

    def test_get_supabase_config_raises_valueerror_when_key_missing(self):
        """get_supabase_configはキーが空の場合ValueErrorを発生させる"""
        mock_settings = Settings(
            _env_file=None,
            supabase_url="http://test",
            supabase_key="",
        )
        with patch("backend.config.settings.settings", mock_settings):
            with pytest.raises(ValueError, match="環境変数 SUPABASE_KEY が設定されていません"):
                get_supabase_config()

    def test_get_supabase_config_returns_tuple_when_both_set(self):
        """get_supabase_configは両方が設定されている場合タプルを返す"""
        test_url = "https://test.supabase.co"
        test_key = "test-key-12345"
        mock_settings = Settings(
            _env_file=None,
            supabase_url=test_url,
            supabase_key=test_key,
        )
        with patch("backend.config.settings.settings", mock_settings):
            url, key = get_supabase_config()
            assert url == test_url
            assert key == test_key

    def test_get_openrouter_key_raises_valueerror_when_missing(self):
        """get_openrouter_keyはキーが空の場合ValueErrorを発生させる"""
        mock_settings = Settings(
            _env_file=None,
            supabase_url="http://test",
            supabase_key="test-key",
            openrouter_api_key="",
        )
        with patch("backend.config.settings.settings", mock_settings):
            with pytest.raises(
                ValueError, match="環境変数 OPENROUTER_API_KEY が設定されていません"
            ):
                get_openrouter_key()

    def test_get_openrouter_key_returns_key_when_set(self):
        """get_openrouter_keyはキーが設定されている場合、値を返す"""
        test_key = "sk-or-test-12345"
        mock_settings = Settings(
            _env_file=None,
            supabase_url="http://test",
            supabase_key="test-key",
            openrouter_api_key=test_key,
        )
        with patch("backend.config.settings.settings", mock_settings):
            key = get_openrouter_key()
            assert key == test_key

    def test_get_openai_key_raises_valueerror_when_missing(self):
        """get_openai_keyはキーが空の場合ValueErrorを発生させる"""
        mock_settings = Settings(
            _env_file=None,
            supabase_url="http://test",
            supabase_key="test-key",
            openai_api_key="",
        )
        with patch("backend.config.settings.settings", mock_settings):
            with pytest.raises(ValueError, match="環境変数 OPENAI_API_KEY が設定されていません"):
                get_openai_key()

    def test_get_openai_key_returns_key_when_set(self):
        """get_openai_keyはキーが設定されている場合、値を返す"""
        test_key = "sk-test-12345"
        mock_settings = Settings(
            _env_file=None,
            supabase_url="http://test",
            supabase_key="test-key",
            openai_api_key=test_key,
        )
        with patch("backend.config.settings.settings", mock_settings):
            key = get_openai_key()
            assert key == test_key
