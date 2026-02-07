"""
設定モジュール

アプリケーション全体で使用する環境変数・設定を一元管理します。
"""

from backend.config.settings import (
    Settings,
    settings,
    get_settings,
    require_env,
    get_supabase_config,
    get_openrouter_key,
    get_openai_key,
    get_gemini_key,
)

__all__ = [
    "Settings",
    "settings",
    "get_settings",
    "require_env",
    "get_supabase_config",
    "get_openrouter_key",
    "get_openai_key",
    "get_gemini_key",
]
