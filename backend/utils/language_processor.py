"""
LanguageProcessor - 言語検出ユーティリティ

ユーザーの質問から言語を検出し、適切な言語で応答するためのユーティリティ。
「Hello」→英語、「こんにちは」→日本語

参考:
- docs/migration/agents/language-classifier/SPEC.md

TODO (専門エンジニア - Chie):
1. LLMを使用した高精度言語検出
2. エラーハンドリングの強化
"""

import logging
import re
from dataclasses import dataclass
from typing import Literal, Optional, TypedDict

from backend.utils.language_types import SupportedLanguage

# TODO: 実装時に必要なインポート
# from llm.openrouter import OpenRouterProvider
# from llm.models import get_model_config

logger = logging.getLogger(__name__)

# =============================================================================
# 型定義
# =============================================================================

LanguageCode = Literal["ja", "en", "zh", "ko", "unknown"]


class LanguageDetectionResult(TypedDict):
    """言語検出結果"""

    detected: SupportedLanguage
    confidence: float
    is_mixed: bool
    languages: dict


# =============================================================================
# 共通定数
# =============================================================================

# 文字種検出用の正規表現パターン（事前コンパイル）
HIRAGANA_PATTERN = re.compile(r"[\u3040-\u309f]")
KATAKANA_PATTERN = re.compile(r"[\u30a0-\u30ff]")
CJK_PATTERN = re.compile(r"[\u4e00-\u9faf]")  # 漢字
HANGUL_PATTERN = re.compile(r"[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]")
LATIN_PATTERN = re.compile(r"[a-zA-Z]")

# 各言語のキーワード
JAPANESE_KEYWORDS = ["は", "が", "を", "に", "で", "の", "か", "です", "ます", "だ", "である"]
ENGLISH_KEYWORDS = [
    "what",
    "where",
    "when",
    "how",
    "why",
    "is",
    "are",
    "was",
    "were",
    "the",
    "a",
    "an",
    "engineer",
    "cafe",
    "about",
    "tell",
    "me",
    "please",
    "hours",
    "open",
    "close",
    "price",
    "location",
    "wifi",
    "facility",
]
CHINESE_KEYWORDS = [
    # zh-only function words / particles (rare or absent in Japanese)
    "是",
    "我",
    "她",
    "们",
    "吗",
    "呢",
    "吧",
    "这",
    # Pronouns and common Chinese-only greetings
    "你",
    "您",
    "请",
    "谢",
    # Chinese-only question words
    "什么",
    "怎么",
    "为什么",
    "哪",
    "几",
    # Chinese-only content words
    "没",
    "今天",
    "明天",
    "现在",
    # Simplified-Chinese-specific characters (Unicode-distinct from Japanese kanji)
    "时",  # vs Japanese 時
    "间",  # vs Japanese 間
    "个",  # vs Japanese 個
    "对",  # vs Japanese 対
    "开",  # vs Japanese 開
    "关",  # vs Japanese 関
    "说",  # vs Japanese 説
    "爱",  # vs Japanese 愛
    # Simplified-Chinese-only domain compounds
    "密码",  # vs Japanese パスワード
    "营业",  # vs Japanese 営業
]
KOREAN_KEYWORDS = ["은", "는", "이", "가", "을", "를", "에서", "입니다", "합니다", "있습니다"]

# 言語コードと言語名のマッピング
LANGUAGE_NAMES = {"ja": "日本語", "en": "英語", "zh": "中国語", "ko": "韓国語", "unknown": "不明"}


# =============================================================================
# テキスト解析の中間結果
# =============================================================================


@dataclass
class _TextAnalysis:
    """テキストの文字種・キーワード解析結果"""

    has_japanese_chars: bool  # ひらがな or カタカナ
    has_cjk: bool  # CJK漢字
    has_hangul: bool
    has_latin: bool
    ja_keyword_count: int
    en_keyword_count: int
    zh_keyword_count: int
    ko_keyword_count: int


# =============================================================================
# LanguageProcessor クラス
# =============================================================================


class LanguageProcessor:
    """
    言語検出ユーティリティ

    ユーザー入力テキストの言語（日本語/英語/中国語/韓国語）を検出し、
    応答言語を決定するユーティリティモジュール。
    Router Agentから呼び出され、多言語対応の基盤となるコンポーネント。
    """

    def __init__(self, default_language: LanguageCode = "ja", debug_mode: bool = False):
        """
        Args:
            default_language: デフォルト言語（検出失敗時に使用）
            debug_mode: デバッグログを出力するか
        """
        self.default_language = default_language
        self.debug_mode = debug_mode
        # TODO: OpenRouterProvider等の初期化

    def _analyze_text(self, text: str) -> _TextAnalysis:
        """テキストの文字種・キーワードを解析する（共通処理）"""
        normalized = text.lower()
        return _TextAnalysis(
            has_japanese_chars=(
                bool(HIRAGANA_PATTERN.search(text)) or bool(KATAKANA_PATTERN.search(text))
            ),
            has_cjk=bool(CJK_PATTERN.search(text)),
            has_hangul=bool(HANGUL_PATTERN.search(text)),
            has_latin=bool(LATIN_PATTERN.search(text)),
            ja_keyword_count=sum(1 for kw in JAPANESE_KEYWORDS if kw in text),
            en_keyword_count=sum(1 for kw in ENGLISH_KEYWORDS if kw in normalized),
            zh_keyword_count=sum(1 for kw in CHINESE_KEYWORDS if kw in text),
            ko_keyword_count=sum(1 for kw in KOREAN_KEYWORDS if kw in text),
        )

    def _build_result(
        self,
        language: SupportedLanguage,
        confidence: float,
        is_mixed: bool = False,
        secondary: SupportedLanguage | None = None,
    ) -> LanguageDetectionResult:
        """
        LanguageDetectionResult を構築する（共通処理）

        Args:
            language: 検出された主言語
            confidence: 信頼度スコア（0.0-1.0）
            is_mixed: 混合言語かどうか
            secondary: 副言語（混合言語の場合）

        Returns:
            LanguageDetectionResult: 構築された検出結果
        """
        return {
            "detected": language,
            "confidence": confidence,
            "is_mixed": is_mixed,
            "languages": (
                {"primary": language, "secondary": secondary}
                if is_mixed and secondary
                else {"primary": language}
            ),
        }

    def detect_language(self, query: str) -> LanguageDetectionResult:
        """
        クエリの言語を検出（メインAPI）

        信頼度スコア・混合言語判定付きの詳細な検出結果を返す。

        Args:
            query: 検出対象のクエリ

        Returns:
            LanguageDetectionResult: 検出結果

        Mastra（TS）版と同等の思想で言語検出を行う。
        日本語・英語・中国語・韓国語を同列に扱い、
        primary / secondary を決定する。
        """
        if self.debug_mode:
            logger.debug("言語検出開始: %s", query[:50])

        a = self._analyze_text(query)

        # ---------------------------------------------------------------------
        # 1. 各言語のスコア計算（共通ロジック）
        # ---------------------------------------------------------------------
        scores = {
            "ja": (
                (2 if a.has_japanese_chars else 0)
                + a.ja_keyword_count
                + (1 if a.has_cjk and a.ja_keyword_count > 0 else 0)
            ),
            "en": a.en_keyword_count + (1 if a.has_latin else 0),
            "zh": (
                (2 if (a.has_cjk and a.zh_keyword_count > 0) else 0)
                + a.zh_keyword_count
                - (1 if a.has_japanese_chars else 0)
            ),
            "ko": (2 if a.has_hangul else 0) + a.ko_keyword_count,
        }

        # ---------------------------------------------------------------------
        # 2. primary / secondary 言語の決定
        # ---------------------------------------------------------------------
        sorted_langs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        primary, primary_score = sorted_langs[0]
        secondary, secondary_score = sorted_langs[1]

        # スコアがすべて 0 の場合はフォールバック
        if primary_score == 0:
            # default_language は "unknown" を含む可能性があるため、明示的に "ja" を使用
            default: SupportedLanguage = (  # type: ignore
                "ja" if self.default_language == "unknown" else self.default_language
            )
            return self._build_result(
                language=default,
                confidence=0.5,
                is_mixed=False,
            )

        # ---------------------------------------------------------------------
        # 3. 混合言語判定（TS版の isMixed 相当）
        # ---------------------------------------------------------------------
        is_mixed = secondary_score > 0 and primary_score - secondary_score <= 2

        # ---------------------------------------------------------------------
        # 4. 信頼度計算（TS版の思想を踏襲）
        # ---------------------------------------------------------------------
        if primary_score >= 3:
            confidence = 0.9
        elif primary_score == 2:
            confidence = 0.7
        else:
            confidence = 0.6

        # ---------------------------------------------------------------------
        # 5. 結果構築（_build_result を使用）
        # ---------------------------------------------------------------------
        # primary と secondary は scores の keys なので SupportedLanguage のいずれか
        primary_lang: SupportedLanguage = primary  # type: ignore
        secondary_lang: SupportedLanguage | None = secondary if is_mixed else None  # type: ignore
        return self._build_result(
            language=primary_lang,
            confidence=confidence,
            is_mixed=is_mixed,
            secondary=secondary_lang,
        )

    async def detect(self, query: str, use_llm: bool = False) -> LanguageCode:
        """
        言語検出（非同期版、LLM対応）

        detect_language() を内部で使用し、LanguageCode のみを返す。
        use_llm=True の場合、低信頼度時にLLMベースの検出を試行する。

        Args:
            query: 検出対象のクエリ
            use_llm: LLMを使用するかどうか

        Returns:
            検出された言語コード
        """
        try:
            result = self.detect_language(query)

            if not use_llm or result["confidence"] >= 0.7:
                return result["detected"]

            # LLMによる高精度検出を試行
            llm_result = await self._detect_by_llm(query)
            if llm_result:
                return llm_result

            return result["detected"]

        except Exception as e:
            logger.exception("言語検出エラー: %s", e)
            return self.default_language

    async def _detect_by_llm(self, query: str) -> Optional[LanguageCode]:
        """
        LLMを使用した高精度言語検出（内部メソッド）

        TODO:
        - OpenRouter APIを使用
        - プロンプト: "Detect the language of the following text: {query}"
        - レスポンスから言語コードを抽出
        """
        logger.debug("LLMベース検出（未実装）: %s...", query[:50])
        # TODO: 実装
        return None

    def determine_response_language(
        self,
        query_language: LanguageDetectionResult,
        force_language: SupportedLanguage | None = None,
    ) -> SupportedLanguage:
        """
        応答言語を決定

        Args:
            query_language: クエリの言語検出結果
            force_language: 強制指定言語（オプショナル）

        Returns:
            SupportedLanguage: 応答言語
        """
        if force_language:
            return force_language
        return query_language["detected"]

    def get_language_name(self, language_code: LanguageCode) -> str:
        """言語コードから言語名（日本語表記）を取得"""
        return LANGUAGE_NAMES.get(language_code, "不明")
