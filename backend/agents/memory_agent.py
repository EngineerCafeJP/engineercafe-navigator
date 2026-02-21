"""
MemoryAgent - DEPRECATED

このモジュールは GeneralKnowledgeAgent に統合されました。
次のスプリントで削除予定です。
新しいコードでは GeneralKnowledgeAgent.answer_query(query_type="memory") を使用してください。

旧説明:
会話履歴・記憶に関する質問に回答するエージェント。
「さっき何を聞いた？」「前に話したことを覚えてる？」といった質問を処理。

参考:
- docs/migration/agents/memory-agent/README.md
- frontend/src/lib/simplified-memory.ts
"""

import logging
import warnings
from typing import Dict, Any, Optional

from langchain_core.messages import HumanMessage

from backend.config.prompts.memory_prompts import build_memory_prompt
from backend.llm import get_llm_provider, get_model_config, OpenRouterProvider
from backend.utils.memory_interface import MemorySystemInterface

logger = logging.getLogger(__name__)


class MemoryAgent:
    """
    MemoryAgent - 会話履歴・記憶に関する質問に回答するエージェント

    「さっき何を聞いた？」「前に話したことを覚えてる？」といった質問を処理。
    """

    def __init__(self, memory_system: Optional[MemorySystemInterface] = None):
        """
        初期化

        Args:
            memory_system: メモリシステムのインスタンス（オプショナル）
                          Noneの場合、メモリ機能なしで動作
        """
        warnings.warn(
            "MemoryAgent is deprecated. Use GeneralKnowledgeAgent with query_type='memory' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.memory_system = memory_system
        self.provider: Optional[OpenRouterProvider] = None
        self.config = get_model_config("qa_response")

        # OpenRouterProviderは遅延初期化（API呼び出し時に初期化）
        try:
            self.provider = get_llm_provider()
        except ValueError as e:
            logger.warning("OpenRouter provider not available: %s", e)

        memory_status = "enabled" if memory_system else "disabled"
        logger.info(
            "MemoryAgent initialized with memory_system: %s",
            memory_status,
        )

    async def process_memory_query(
        self, query: str, session_id: str, language: str = "ja"
    ) -> Dict[str, Any]:
        """
        メモリ関連のクエリを処理

        Args:
            query: ユーザーのクエリ
            session_id: セッションID
            language: 言語設定（"ja" or "en"）

        Returns:
            {
                "answer": str,  # 回答テキスト
                "emotion": str,  # 感情タグ
                "metadata": Dict  # その他のメタデータ
            }
        """
        logger.info("Processing memory query: '%s...', session: %s", query[:50], session_id)

        # 1. メモリシステムの可用性チェック
        if not self.memory_system:
            return self._handle_no_memory_system(language)

        try:
            # 2. 質問タイプの判定
            query_type = self.detect_memory_query_type(query)
            logger.info("Detected query type: %s", query_type)

            # 3. 会話履歴の取得
            context = await self.memory_system.get_context(
                query, session_id, {"language": language, "inherit_context": True}
            )

            # 4. 履歴がない場合のフォールバック
            if not context.get("recent_messages"):
                return self._no_history_response(language)

            # 5. プロンプト構築
            prompt = self.build_memory_prompt(query, context, query_type, language)

            # 6. OpenRouter APIで回答生成
            answer = await self.generate_response(prompt, language)

            # 7. 感情タグの決定
            emotion = self._determine_emotion(context, query_type)

            return {
                "answer": answer,
                "emotion": emotion,
                "metadata": {
                    "agent": "MemoryAgent",
                    "status": "success",
                    "query_type": query_type,
                    "message_count": len(context.get("recent_messages", [])),
                    "inherited_request_type": context.get("inherited_request_type"),
                },
            }

        except Exception as e:
            logger.error("Error processing memory query: %s", e)
            return {
                "answer": (
                    "メモリの処理中にエラーが発生しました。"
                    if language == "ja"
                    else "An error occurred while processing memory."
                ),
                "emotion": "surprised",
                "metadata": {
                    "agent": "MemoryAgent",
                    "status": "error",
                    "error": str(e),
                },
            }

    def detect_memory_query_type(self, query: str) -> str:
        """
        メモリ関連質問のタイプを判定

        Args:
            query: ユーザーのクエリ

        Returns:
            質問タイプ
            - "question_history": 質問履歴への質問
            - "answer_history": 回答履歴への質問
            - "other_option": 「もう一つの方」系の質問
            - "general_memory": その他のメモリ関連質問
        """
        lower_query = query.lower()

        # 質問履歴への質問
        question_keywords = [
            "何を聞いた",
            "何聞いた",
            "質問した",
            "さっき聞いた",
            "前に聞いた",
            "what did i ask",
            "what i asked",
            "my question",
            "previous question",
        ]
        if any(keyword in lower_query for keyword in question_keywords):
            return "question_history"

        # 回答履歴への質問
        answer_keywords = [
            "答え",
            "回答",
            "何て言った",
            "何と言った",
            "教えてくれた",
            "answer",
            "response",
            "what did you say",
            "you told me",
            "your answer",
        ]
        if any(keyword in lower_query for keyword in answer_keywords):
            return "answer_history"

        # もう一つの方系の質問
        other_keywords = [
            "もう一つの方",
            "もう一つ",
            "もうひとつ",
            "他の方",
            "別の方",
            "the other one",
            "the other",
            "another one",
            "alternative",
        ]
        if any(keyword in lower_query for keyword in other_keywords):
            return "other_option"

        return "general_memory"

    def build_memory_prompt(
        self,
        query: str,
        context: Dict[str, Any],
        query_type: str,
        language: str = "ja",
    ) -> str:
        """メモリコンテキストからプロンプトを構築（外部テンプレートに委譲）"""
        return build_memory_prompt(query, context, query_type, language)

    async def generate_response(self, prompt: str, language: str = "ja") -> str:
        """
        OpenRouter APIで回答を生成

        Args:
            prompt: 構築されたプロンプト
            language: 言語設定

        Returns:
            生成された回答
        """
        if not self.provider:
            logger.warning("OpenRouter provider not available")
            return (
                "回答を生成できませんでした。"
                if language == "ja"
                else "Could not generate a response."
            )

        try:
            messages = [HumanMessage(content=prompt)]
            response = await self.provider.generate(messages, self.config)
            return response

        except Exception as e:
            logger.error("Error generating response: %s", e)
            return (
                "回答の生成中にエラーが発生しました。"
                if language == "ja"
                else "An error occurred while generating the response."
            )

    def _determine_emotion(self, context: Dict[str, Any], query_type: str) -> str:
        """
        適切な感情タグを決定

        Args:
            context: メモリコンテキスト
            query_type: 質問タイプ

        Returns:
            感情タグ（relaxed, sad, happy, surprised, neutral）

        ルール:
        - 履歴あり: relaxed
        - 履歴なし: sad
        - もう一つ系: happy
        - 文脈不明: surprised
        """
        if not context.get("recent_messages"):
            return "sad"  # 履歴なし

        if query_type == "other_option":
            return "happy"  # 補足情報提供

        if query_type in ["question_history", "answer_history"]:
            return "relaxed"  # 落ち着いて回答

        return "neutral"

    def _handle_no_memory_system(self, language: str) -> Dict[str, Any]:
        """
        メモリシステムが利用できない場合の処理

        Args:
            language: 言語設定

        Returns:
            エラーメッセージを含む応答
        """
        if language == "en":
            message = "Memory system is not available at the moment. Please try again later."
        else:
            message = "メモリシステムが利用できません。しばらくしてからもう一度お試しください。"

        logger.warning("Memory system is not available")

        return {
            "answer": message,
            "emotion": "sad",
            "metadata": {
                "agent": "MemoryAgent",
                "status": "memory_unavailable",
                "error": "no_memory_system",
            },
        }

    def _no_history_response(self, language: str) -> Dict[str, Any]:
        """
        会話履歴がない場合の応答

        Args:
            language: 言語設定

        Returns:
            履歴なしメッセージを含む応答
        """
        if language == "en":
            message = "I don't have any conversation history yet. Let's start chatting!"
        else:
            message = "まだ会話履歴がありません。何か質問してみてください！"

        return {
            "answer": message,
            "emotion": "sad",
            "metadata": {
                "agent": "MemoryAgent",
                "status": "no_history",
                "query_type": "memory",
            },
        }

    async def close(self) -> None:
        """
        リソースのクリーンアップ
        """
        if self.provider:
            await self.provider.close()
            logger.info("MemoryAgent resources cleaned up")
