"""
LanguageProcessor - 言語検出ユーティリティ

ユーザーの質問から言語を検出し、適切な言語で応答するためのユーティリティ。
「Hello」→英語、「こんにちは」→日本語

参考:
- docs/migration/agents/language-classifier/SPEC.md

低信頼度の場合は、任意で LLM による言語判定へフォールバックできる。
"""

import logging
import os
import re
from dataclasses import dataclass
from typing import Literal, Optional, TypedDict

from backend.utils.language_types import SupportedLanguage

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

# Language detection design trade-offs (Bug #444):
#
# Engineer Cafe kiosk is in Japan; the primary language is Japanese. The
# language detector resolves CJK ambiguity by preferring ja for queries that
# could plausibly belong to either language. Specific trade-offs:
#
# 1. Pure Chinese place names without function words (e.g. "北京", "上海",
#    "菜单") fall through to ja default. Adding a length-based zh CJK bonus
#    would re-break Bug #444 (Japanese kanji-only queries like "時間",
#    "福岡" misclassified as zh and answered in Chinese).
#
# 2. Shared kanji compounds (e.g. "未来", "目的地", "友好") are inherently
#    ambiguous — they exist in both Japanese and Chinese with the same
#    meaning. The dict-insertion-order tie-breaker resolves these to ja for
#    the kiosk's primary user base.
#
# 3. Chinese queries containing function words (你, 我, 是, 的, 吗, 们, 这,
#    那, 时, 间, 个, 师, 业 etc.) or distinctive simplified characters are
#    correctly detected as zh. This covers all 7 RAGAS multilingual zh test
#    cases and Codex round 1-3 verification cases.
#
# Trade-off rationale: Japanese is the primary user base for the Fukuoka
# kiosk. Misclassifying a Japanese kanji query as Chinese (Bug #444) is
# the original critical bug. Misclassifying rare Chinese noun-only queries
# as Japanese is an acceptable secondary trade-off since (a) the kiosk
# expects mostly Japanese-speaking visitors and (b) Chinese visitors
# typically use sentences with function words rather than noun-only queries.
JAPANESE_KEYWORDS = [
    # Particles (Japanese-only hiragana — strongest signal)
    "は",
    "が",
    "を",
    "に",
    "で",
    "の",
    "か",
    "です",
    "ます",
    "だ",
    "である",
    # Japanese kanji compounds where embedded chars are ALSO in CHINESE_KEYWORDS.
    # These exist solely to break ties via dict insertion order — when both ja and
    # zh score equally, the "ja" key comes first in the scores dict, so ja wins.
    # Kanji-only Japanese queries containing 的/他/会/来/了/好 would otherwise
    # be misclassified as zh.
    "目的",  # contains 的
    "目的地",  # contains 的
    "他人",  # contains 他
    "会議",  # contains 会
    "会員",  # contains 会
    "会場",  # contains 会
    "未来",  # contains 来
    "将来",  # contains 来
    "来年",  # contains 来
    "終了",  # contains 了
    "完了",  # contains 了
    "良好",  # contains 好
    "友好",  # contains 好
    # Japanese-specific compounds (kanji unique to Japanese vs simplified Chinese).
    # These are kept because they include Japanese-only characters (営, 予, 受, 価, 場, 案, 申).
    "営業",
    "受付",
    "予約",
    "案内",
    "場所",
    "価格",
    "申込",
]
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
    # Function words / particles (simplified)
    "的",
    "是",
    "了",  # also breaks Japanese 終了/完了 → handled via JA_KW tie-breaker
    "在",
    "我",
    "他",  # also breaks Japanese 他人 → handled via JA_KW tie-breaker
    "她",
    "们",
    "吗",
    "呢",
    "吧",
    "会",  # also breaks Japanese 会議/会員/会場 → handled via JA_KW
    "这",
    "那",
    "好",  # also breaks Japanese 良好/友好 → handled via JA_KW
    "来",  # also breaks Japanese 未来/将来/来年 → handled via JA_KW
    # Pronouns and Chinese-only greetings
    "你",
    "您",
    "请",
    "谢",
    # Chinese-only question words (simplified)
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
    "可以",
    # Simplified-Chinese-DISTINCT characters (Unicode-distinct from Japanese kanji)
    "时",
    "间",
    "个",
    "对",
    "开",
    "关",
    "说",
    "爱",
    "师",
    "书",
    "现",
    "业",
    "钱",
    "议",
    "动",
    "务",
    "头",
    "区",
    "经",
    "网",
    "电",
    "视",
    # Chinese-only loanword / common-life characters
    "咖",
    "啡",
    "厕",
    # Traditional-Chinese function words / particles
    "這",
    "麼",
    "幾",
    "嗎",
    "沒",
    "點",
    "為",
    # Simplified-Chinese-only domain compounds
    "密码",
    "营业",
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
                (1 if (a.has_cjk and a.zh_keyword_count > 0) else 0)
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
        # Threshold widened from <=2 to <=3 to preserve is_mixed semantics
        # after Bug #444 Round 2 scoring change (larger JA_KEYWORDS + smaller zh CJK bonus).
        is_mixed = secondary_score > 0 and primary_score - secondary_score <= 3

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
        """Use the router LLM for low-confidence language detection."""
        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not api_key or api_key.lower().startswith(("test-", "placeholder", "fake-", "sk-test-")):
            logger.debug("LLM language detection skipped: OpenRouter key unavailable")
            return None

        provider = None
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            from backend.llm.models import MODEL_CONFIGS
            from backend.llm.provider import resolve_llm_provider

            provider = resolve_llm_provider(api_key=api_key)
            result = await provider.generate(
                [
                    SystemMessage(
                        content=(
                            "Detect the language of the user text. "
                            "Return exactly one code from: ja, en, zh, ko, unknown."
                        )
                    ),
                    HumanMessage(content=query[:1000]),
                ],
                MODEL_CONFIGS["router"],
            )
            normalized = result.strip().lower()
            aliases = {
                "japanese": "ja",
                "jp": "ja",
                "english": "en",
                "chinese": "zh",
                "zh-cn": "zh",
                "korean": "ko",
            }
            code = aliases.get(normalized, normalized[:2])
            if code in {"ja", "en", "zh", "ko", "unknown"}:
                return code  # type: ignore[return-value]
        except Exception as exc:
            logger.debug("LLM language detection failed: %s", exc)
        finally:
            if provider is not None:
                try:
                    await provider.close()
                except Exception:
                    pass
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
