"""
LanguageProcessor - 言語検出と応答言語決定

TypeScript版から移植:
frontend/src/lib/language-processor.ts
"""

import re
from dataclasses import dataclass
from typing import Literal

SupportedLanguage = Literal["ja", "en"]


@dataclass
class LanguageDetectionResult:
    """言語検出結果"""

    detected: SupportedLanguage
    confidence: float


class LanguageProcessor:
    """
    言語検出処理を担当するクラス

    日本語と英語の検出を行い、応答言語を決定します。
    """

    # 日本語文字パターン（ひらがな、カタカナ、漢字）
    JAPANESE_PATTERN = re.compile(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]")

    def detect_language(self, query: str) -> LanguageDetectionResult:
        """
        クエリの言語を検出

        Args:
            query: ユーザーからの入力テキスト

        Returns:
            LanguageDetectionResult: 検出された言語と信頼度
        """
        # 日本語文字が含まれているかチェック
        has_japanese = bool(self.JAPANESE_PATTERN.search(query))

        if has_japanese:
            return LanguageDetectionResult(detected="ja", confidence=0.95)

        # デフォルトは英語
        return LanguageDetectionResult(detected="en", confidence=0.8)

    def determine_response_language(
        self, language_result: LanguageDetectionResult
    ) -> SupportedLanguage:
        """
        応答言語を決定

        Args:
            language_result: 言語検出結果

        Returns:
            SupportedLanguage: 応答に使用する言語
        """
        return language_result.detected
