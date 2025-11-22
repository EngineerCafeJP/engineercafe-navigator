"""
言語処理ユーティリティ
言語検出と応答言語の決定
"""

import re
from typing import Optional

# 相対インポートまたは絶対インポートに統一
try:
    from models.types import SupportedLanguage
except ImportError:
    # フォールバック: 直接定義
    from typing import Literal
    SupportedLanguage = Literal["ja", "en"]


def detect_language(query: str) -> SupportedLanguage:
    """
    クエリの言語を検出
    
    Args:
        query: 検出対象のクエリ
        
    Returns:
        検出された言語（"ja" または "en"）
    """
    # 日本語の文字（ひらがな、カタカナ、漢字）が含まれているか
    japanese_pattern = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]')
    
    if japanese_pattern.search(query):
        return "ja"
    else:
        return "en"


def determine_response_language(
    detected_language: SupportedLanguage,
    user_preference: Optional[SupportedLanguage] = None
) -> SupportedLanguage:
    """
    応答言語を決定
    
    Args:
        detected_language: 検出された言語
        user_preference: ユーザーの言語設定（オプション）
        
    Returns:
        応答に使用する言語
    """
    if user_preference:
        return user_preference
    return detected_language

