"""
環境変数を一元管理する設定モジュール

Pydantic BaseSettingsを使用して、環境変数の検証と型安全なアクセスを提供。
.envファイルからの自動読み込みもサポート。

使用例:
    from backend.config.settings import settings

    # API キーへのアクセス
    openrouter_key = settings.openrouter_api_key

    # Supabase設定
    db_uri = settings.supabase_db_uri
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    アプリケーション設定

    環境変数から自動的に値を読み込み、型検証を行う。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ============================================
    # 環境設定
    # ============================================
    environment: str = Field(
        default="development", description="実行環境 (development, staging, production)"
    )
    debug: bool = Field(default=False, description="デバッグモード")
    app_url: str = Field(default="https://engineer-cafe.jp", description="アプリケーションURL")

    # ============================================
    # Supabase
    # ============================================
    supabase_url: str = Field(default="", description="Supabase API URL")
    supabase_key: str = Field(default="", description="Supabase API Key (anon)")
    supabase_db_uri: str = Field(default="", description="Supabase PostgreSQL接続URI")

    # ============================================
    # OpenRouter (LLM)
    # ============================================
    openrouter_api_key: str = Field(default="", description="OpenRouter API Key")

    # ============================================
    # OpenAI
    # ============================================
    openai_api_key: str = Field(default="", description="OpenAI API Key")

    # ============================================
    # Google
    # ============================================
    # Google Cloud (音声用)
    google_cloud_credentials: str = Field(
        default="", description="Google Cloud credentials path/JSON"
    )
    google_application_credentials: str = Field(
        default="", description="Google Cloud credentials path (代替)"
    )
    google_cloud_project_id: str = Field(default="", description="Google Cloud プロジェクトID")

    # Google Calendar
    google_calendar_ical_url: str = Field(default="", description="Google Calendar iCal URL")

    # ============================================
    # 外部サービス
    # ============================================
    langsmith_api_key: str = Field(default="", description="LangSmith API Key")
    langsmith_project: str = Field(
        default="engineer-cafe-navigator-production",
        description="LangSmith project name for production tracing",
    )
    connpass_api_key: str = Field(default="", description="Connpass API Key")

    # ============================================
    # プロパティ（派生値）
    # ============================================

    @property
    def google_credentials(self) -> str:
        """Google Cloud credentials (どちらかの環境変数)"""
        return self.google_cloud_credentials or self.google_application_credentials

    @property
    def is_production(self) -> bool:
        """本番環境かどうか"""
        return self.environment == "production"

    @property
    def is_test(self) -> bool:
        """テスト環境かどうか"""
        return self.environment == "test"

    # ============================================
    # バリデーション
    # ============================================

    def validate_required_keys(self, keys: list[str]) -> dict[str, bool]:
        """
        指定されたキーが設定されているか検証

        Args:
            keys: 検証するキー名のリスト

        Returns:
            各キーの設定状況
        """
        result = {}
        for key in keys:
            value = getattr(self, key, "")
            result[key] = bool(value)
        return result

    def get_missing_keys(self, required_keys: list[str]) -> list[str]:
        """
        設定されていない必須キーのリストを取得

        Args:
            required_keys: 必須キー名のリスト

        Returns:
            未設定のキー名リスト
        """
        missing = []
        for key in required_keys:
            value = getattr(self, key, "")
            if not value:
                missing.append(key)
        return missing


@lru_cache()
def get_settings() -> Settings:
    """
    設定インスタンスを取得（キャッシュ付き）

    Returns:
        Settings インスタンス
    """
    return Settings()


# シングルトンインスタンス
settings = get_settings()


# ============================================
# ヘルパー関数
# ============================================


def require_env(key: str, value: str) -> str:
    """
    環境変数が設定されていることを要求

    Args:
        key: 環境変数名
        value: 環境変数の値

    Returns:
        値

    Raises:
        ValueError: 環境変数が設定されていない場合
    """
    if not value:
        raise ValueError(f"環境変数 {key} が設定されていません")
    return value


def get_supabase_config() -> tuple[str, str]:
    """
    Supabase設定を取得

    Returns:
        (url, key) のタプル

    Raises:
        ValueError: 必須設定が不足している場合
    """
    url = require_env("SUPABASE_URL", settings.supabase_url)
    key = require_env("SUPABASE_KEY", settings.supabase_key)
    return url, key


def get_openrouter_key() -> str:
    """
    OpenRouter API Keyを取得

    Returns:
        API Key

    Raises:
        ValueError: キーが設定されていない場合
    """
    return require_env("OPENROUTER_API_KEY", settings.openrouter_api_key)


def get_openai_key() -> str:
    """
    OpenAI API Keyを取得

    Returns:
        API Key

    Raises:
        ValueError: キーが設定されていない場合
    """
    return require_env("OPENAI_API_KEY", settings.openai_api_key)
