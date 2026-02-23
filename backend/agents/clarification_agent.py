"""
ClarificationAgent骨組み（専門エンジニア向け）

曖昧な質問を検出し、明確化のための選択肢を生成するエージェント。
「カフェはどこ？」→「Engineer Cafe本郷ですか？秋葉原ですか？」

参考:
- docs/migration/agents/clarification-agent/README.md

TODO (専門エンジニア - Chie):
1. 曖昧さ検出ロジック実装
2. OpenRouter APIを使用した選択肢生成
3. 候補抽出アルゴリズム実装
4. ユーザーフレンドリーな質問文の生成
5. 感情タグの適切な設定
6. エラーハンドリングとフォールバック
"""

import logging
from typing import Dict, Any, List, Optional, Literal, TypedDict

from backend.utils.emotion_tagger import add_emotion_tag

from backend.llm.openrouter import OpenRouterProvider
from backend.llm.models import get_model_config
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

# 型定義
SupportedLanguage = Literal["ja", "en"]

ClarificationCategory = Literal[
    "cafe-clarification-needed",
    "meeting-room-clarification-needed",
    "general-clarification-needed",
]


class ClarificationResult(TypedDict):
    """Clarification Agentの出力結果"""

    response: str  # 感情タグ付きテキスト
    emotion: Literal["surprised"]
    metadata: dict  # agent名, category, confidence など


class ClarificationAgent:
    """
    ClarificationAgent骨組み（専門エンジニア向け）

    このクラスは骨組みのみを提供します。完全実装は専門エンジニア（Chie）が担当。
    """

    # 共通メタデータ定数
    _AGENT_NAME = "ClarificationAgent"
    _DEFAULT_SOURCES = ["clarification_system"]

    # 曖昧性検出キーワード
    _AMBIGUITY_KEYWORDS = {
        "cafe": {
            "triggers": ["カフェ", "cafe", "喫茶"],
            "specifics": ["エンジニアカフェ", "サイノ", "saino", "engineer cafe", "コワーキング"],
        },
        "meeting-room": {
            "triggers": ["会議室", "meeting room", "ミーティングルーム"],
            "specifics": ["2階", "二階", "2F", "地下", "B1", "有料", "無料", "MTG"],
        },
        "event": {
            "triggers": ["イベント", "event"],
            "specifics": ["勉強会", "セミナー", "ハッカソン", "ミートアップ", "workshop", "meetup"],
        },
    }

    # 曖昧性解消の選択肢
    _CLARIFICATION_OPTIONS = {
        "cafe": [
            {"label": "エンジニアカフェ（コワーキングスペース）", "value": "engineer-cafe"},
            {"label": "サイノカフェ（カフェ＆バー）", "value": "saino"},
        ],
        "meeting-room": [
            {"label": "有料会議室（2階）", "value": "paid-meeting-room"},
            {"label": "地下MTGスペース（無料）", "value": "free-meeting-space"},
        ],
        "event": [
            {"label": "勉強会・セミナー", "value": "study-seminar"},
            {"label": "ハッカソン・もくもく会", "value": "hackathon"},
        ],
    }

    def __init__(self):
        """Initialize ClarificationAgent.

        Sets up OpenRouterProvider and model configuration for clarification processing.
        """
        logger.info("ClarificationAgent初期化")
        self.llm = OpenRouterProvider()
        self.model_config = get_model_config("clarification")

    def _create_result(
        self,
        message: str,
        category: ClarificationCategory,
        confidence: float = 0.9,
    ) -> ClarificationResult:
        """
        ClarificationResultを生成するヘルパーメソッド

        Args:
            message: 応答メッセージ
            category: 曖昧性のカテゴリ
            confidence: 信頼度スコア（デフォルト：0.9）

        Returns:
            ClarificationResult: 感情タグ付きの応答とメタデータ
        """
        tagged_message = add_emotion_tag(message, "surprised")
        return {
            "response": tagged_message,
            "emotion": "surprised",
            "metadata": {
                "agent": self._AGENT_NAME,
                "confidence": confidence,
                "category": category,
                "sources": self._DEFAULT_SOURCES,
            },
        }

    async def handle_clarification(
        self,
        query: str,
        category: ClarificationCategory,
        language: SupportedLanguage,
    ) -> ClarificationResult:
        """
        曖昧性解消の処理

        OrchestratorAgentからcategoryを受け取り、固定メッセージで曖昧性を解消します。
        LLMを使用せず、高速で一貫性のある応答を提供します。

        Args:
            query: ユーザーからの入力テキスト（現在は使用されないが、将来の拡張用）
            category: 曖昧性の種類（OrchestratorAgentが判定済み）
            language: 応答言語

        Returns:
            ClarificationResult: 感情タグ付きの応答とメタデータ
        """
        logger.info(
            "ClarificationAgent.handle_clarification: query=%s, category=%s, language=%s",
            query,
            category,
            language,
        )

        # カフェの曖昧性解消
        if category == "cafe-clarification-needed":
            if language == "en":
                clarification_message = (
                    "I'd be happy to help!"
                    " Are you asking about:\n"
                    "1. **Engineer Cafe** (coworking space)"
                    " - Open 9:00-22:00,"
                    " free WiFi & power outlets\n"
                    "2. **Saino Cafe** (attached cafe & bar)"
                    " - Weekdays 12:00-20:00,"
                    " lunch & drink menu\n\n"
                    "Please let me know which one"
                    " you're interested in!"
                )
            else:
                clarification_message = (
                    "お手伝いさせていただきます！"
                    "どちらについてお聞きでしょうか：\n"
                    "1. **エンジニアカフェ**"
                    "（コワーキングスペース）"
                    "- 9:00-22:00、WiFi・電源完備、無料利用可\n"
                    "2. **サイノカフェ**"
                    "（併設のカフェ＆バー）"
                    "- 平日12:00-20:00、"
                    "ランチ・ドリンクメニューあり\n\n"
                    "お聞かせください！"
                )

            return self._create_result(clarification_message, "cafe-clarification-needed")

        # 会議室の曖昧性解消
        if category == "meeting-room-clarification-needed":
            if language == "en":
                clarification_message = (
                    "I'd be happy to help!"
                    " We have two types of"
                    " meeting spaces:\n"
                    "1. **Paid Meeting Rooms (2F)**"
                    " - Managed by Fukuoka City"
                    " (Red Brick Cultural Hall"
                    " reception, right side of 1F)."
                    " Advance booking required\n"
                    "2. **Basement Meeting Spaces (B1)**"
                    " - Free, reservation priority"
                    " (2h blocks). Book by the day"
                    " before; walk-in OK if available"
                    "\n\n"
                    "Which one would you like"
                    " to know about?"
                )
            else:
                clarification_message = (
                    "お手伝いさせていただきます！"
                    "会議スペースは2種類ございます：\n"
                    "1. **有料会議室（2階）** - "
                    "福岡市の施設です。"
                    "1F右手奥の赤煉瓦文化館受付で"
                    "お手続きください"
                    "（エンジニアカフェとは別管理）\n"
                    "2. **地下MTGスペース（地下1階）**"
                    " - 無料・予約優先（2時間区切り）。"
                    "前日までに予約可、"
                    "空いていれば予約なしでも利用OK"
                    "\n\n"
                    "どちらについてお知りになりたいですか？"
                )

            return self._create_result(clarification_message, "meeting-room-clarification-needed")

        # デフォルトの曖昧性解消
        if language == "en":
            default_message = (
                "I'd be happy to help!"
                " Could you please provide more details"
                " about what you'd like to know?"
            )
        else:
            default_message = (
                "お手伝いさせていただきます！" "もう少し詳しくお聞かせいただけますか？"
            )

        return self._create_result(default_message, "general-clarification-needed", confidence=0.7)

    async def detect_ambiguity(self, query: str, context: Optional[Dict[str, Any]] = None) -> bool:
        """Detect ambiguity in user query using keyword-based detection.

        Args:
            query: User's question to analyze.
            context: Context information. If already clarified
                in previous conversation, returns False.

        Returns:
            True if the question is ambiguous, False if it is clear.
        """
        logger.info("曖昧さ検出: %s", query)
        lower_query = query.lower()

        # コンテキストで既に特定済みの場合はスキップ
        if context and context.get("already_clarified"):
            return False

        for category, keywords in self._AMBIGUITY_KEYWORDS.items():
            # トリガーキーワードが含まれている
            has_trigger = any(kw.lower() in lower_query for kw in keywords["triggers"])
            if not has_trigger:
                continue

            # 具体的なキーワードが含まれていない → 曖昧
            has_specific = any(kw.lower() in lower_query for kw in keywords["specifics"])
            if not has_specific:
                logger.info("曖昧性検出: category=%s, query=%s", category, query)
                return True

        return False

    async def generate_clarification_options(
        self, query: str, context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, str]]:
        """Detect ambiguity category and return corresponding options.

        Args:
            query: User's question to analyze.
            context: Context information.

        Returns:
            List of clarification options. Each option is a dict with 'label' and 'value' keys.
        """
        logger.info("選択肢生成: %s", query)
        lower_query = query.lower()

        for category, keywords in self._AMBIGUITY_KEYWORDS.items():
            has_trigger = any(kw.lower() in lower_query for kw in keywords["triggers"])
            if has_trigger:
                options = self._CLARIFICATION_OPTIONS.get(category, [])
                if options:
                    logger.info("選択肢生成完了: category=%s, options=%d", category, len(options))
                    return list(options)  # Return a copy

        return []

    async def format_clarification_question(
        self, original_query: str, options: List[Dict[str, str]]
    ) -> str:
        """Generate natural clarification question using LLM (with fallback).

        Args:
            original_query: Original user query.
            options: List of clarification options.

        Returns:
            Formatted clarification question.
        """
        logger.info("質問文フォーマット: %s", original_query)

        if not options:
            return "申し訳ありません。もう少し詳しく教えていただけますか？"

        # テンプレートフォールバック用
        options_text = "\n".join(f"{i+1}. {opt['label']}" for i, opt in enumerate(options))
        fallback_question = (
            f"「{original_query}」について、以下のどちらについてお聞きですか？\n{options_text}"
        )

        try:
            prompt = (
                f"ユーザーが「{original_query}」と質問しました。\n"
                f"以下の選択肢から選んでもらう質問文を、自然な日本語で生成してください。\n"
                f"選択肢:\n{options_text}\n\n"
                f"注意: 質問文のみを出力してください。余計な説明は不要です。"
            )

            messages = [
                SystemMessage(
                    content="あなたはエンジニアカフェの受付AIアシスタントです。丁寧で親しみやすい質問文を生成してください。"
                ),
                HumanMessage(content=prompt),
            ]

            response: str = await self.llm.generate(
                messages=messages,
                config=self.model_config,
            )

            if response and len(response.strip()) > 0:
                return response.strip()

        except Exception as e:
            logger.warning("LLM質問文生成失敗、フォールバック使用: %s", e)

        return fallback_question

    async def process(self, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Main entry point for clarification processing.

        Pipeline: detect_ambiguity → generate_options → format_question

        Args:
            query: User's question to process.
            context: Context information.

        Returns:
            Clarification result dict with keys:
                - needs_clarification (bool): Whether clarification is needed.
                - clarification_question (str): Formatted question to ask user.
                - options (List[Dict[str, str]]): List of clarification options.
                - emotion (str): Emotion tag for response.
        """
        logger.info("ClarificationAgent処理開始: %s", query)

        try:
            # 1. 曖昧さ検出
            needs_clarification = await self.detect_ambiguity(query, context)

            if not needs_clarification:
                return {
                    "needs_clarification": False,
                    "clarification_question": "",
                    "options": [],
                    "emotion": "neutral",
                }

            # 2. 選択肢生成
            options = await self.generate_clarification_options(query, context)

            # 3. 質問文フォーマット
            clarification_question = await self.format_clarification_question(query, options)

            return {
                "needs_clarification": True,
                "clarification_question": clarification_question,
                "options": options,
                "emotion": "surprised",
            }

        except Exception as e:
            logger.exception("ClarificationAgent処理エラー: %s", e)
            return {
                "needs_clarification": False,
                "clarification_question": "",
                "options": [],
                "emotion": "confused",
                "error": str(e),
            }
