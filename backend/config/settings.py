"""
アプリケーション設定
環境変数から設定を読み込む
"""

try:
    from pydantic_settings import BaseSettings
except ImportError:
    # pydantic-settingsがインストールされていない場合のフォールバック
    # Pydantic v2ではBaseSettingsがpydantic_settingsに移動
    try:
        from pydantic import BaseSettings
    except ImportError:
        # 完全なフォールバック
        from typing import List, Optional
        class BaseSettings:
            class Config:
                env_file = ".env"
                env_file_encoding = "utf-8"
                case_sensitive = False

from typing import List, Optional


class Settings(BaseSettings):
    """アプリケーション設定"""
    
    # Environment
    environment: str = "development"
    debug: bool = True
    log_level: str = "INFO"
    
    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:3001"]
    
    # AI API Keys
    openai_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    
    # Database
    supabase_url: Optional[str] = None
    supabase_key: Optional[str] = None
    supabase_service_role_key: Optional[str] = None
    postgres_connection_string: Optional[str] = None
    
    # Memory & RAG
    memory_ttl: int = 180  # 3分
    rag_max_results: int = 5
    rag_similarity_threshold: float = 0.7
    
    # OCR
    tesseract_cmd: Optional[str] = None
    google_vision_api_key: Optional[str] = None
    
    # LangSmith
    langchain_tracing_v2: bool = False
    langchain_endpoint: Optional[str] = None
    langchain_api_key: Optional[str] = None
    langchain_project: str = "engineer-cafe-navigator"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """設定インスタンスを取得（シングルトン）"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings

