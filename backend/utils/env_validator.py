"""
起動時の環境変数バリデーション

Pydantic Settingsを活用して、必須環境変数が設定されていることを検証する。
development環境: 警告のみ
production環境: 起動失敗（ValueError）
"""

import logging

from backend.config.settings import get_settings

logger = logging.getLogger(__name__)

# Required env vars for each tier
REQUIRED_CORE = ["openrouter_api_key"]
REQUIRED_STORAGE = ["supabase_url", "supabase_key", "supabase_db_uri"]
REQUIRED_PRODUCTION = REQUIRED_CORE + REQUIRED_STORAGE


def validate_startup() -> dict[str, list[str]]:
    """
    起動時の環境変数バリデーション

    Returns:
        dict with "missing" and "warnings" keys

    Raises:
        ValueError: production環境で必須環境変数が不足している場合
    """
    settings = get_settings()
    result: dict[str, list[str]] = {"missing": [], "warnings": []}

    if settings.is_production:
        missing = settings.get_missing_keys(REQUIRED_PRODUCTION)
        if missing:
            msg = f"Production環境で必須環境変数が未設定: {', '.join(missing)}"
            logger.error(msg)
            raise ValueError(msg)
        logger.info("環境変数バリデーション OK (production)")
    else:
        # development / test: warn only
        missing_core = settings.get_missing_keys(REQUIRED_CORE)
        missing_storage = settings.get_missing_keys(REQUIRED_STORAGE)

        if missing_core:
            result["warnings"].append(
                f"コア環境変数が未設定（一部機能が動作しません）: {', '.join(missing_core)}"
            )
            for key in missing_core:
                logger.warning("環境変数未設定: %s", key)

        if missing_storage:
            result["warnings"].append(
                f"ストレージ環境変数が未設定（永続化が無効）: {', '.join(missing_storage)}"
            )
            for key in missing_storage:
                logger.warning("環境変数未設定: %s", key)

        result["missing"] = missing_core + missing_storage

        if not result["missing"]:
            logger.info("環境変数バリデーション OK (%s)", settings.environment)

    return result
