"""
SlideAgent - スライドナレーターエージェント
スライドプレゼンテーションのナレーションと質問応答を担当
"""

import json
import logging
import os
from typing import Dict, Optional, Literal

from langchain_core.messages import HumanMessage

from backend.llm import get_llm_provider, get_model_config

logger = logging.getLogger(__name__)


SlideAction = Literal["narrate", "next", "previous", "goto", "question"]


class SlideAgent:
    """スライドナレーターエージェント"""

    def __init__(self):
        """初期化

        マルチセッション対応: session_id ベースの状態管理を実装
        """
        self.llm_provider = get_llm_provider()
        self.narration_data: Dict = {}
        self._slide_positions: Dict[str, int] = {}  # session_idベースの状態管理
        self.total_slides = 0

    def _get_current_slide(self, session_id: str = "default") -> int:
        """セッションIDに基づく現在のスライド番号を取得"""
        return self._slide_positions.get(session_id, 1)

    def _set_current_slide(self, session_id: str, slide_number: int) -> None:
        """セッションIDに基づく現在のスライド番号を設定"""
        self._slide_positions[session_id] = slide_number

    @property
    def current_slide(self) -> int:
        """後方互換: デフォルトセッションの現在スライド番号"""
        return self._get_current_slide("default")

    @current_slide.setter
    def current_slide(self, value: int) -> None:
        """後方互換: デフォルトセッションのスライド番号を設定"""
        self._set_current_slide("default", value)

    def load_narration(self, language: str = "ja") -> bool:
        """
        ナレーションJSONを読み込み

        Args:
            language: 言語（ja or en）

        Returns:
            読み込み成功: True, 失敗: False
        """
        try:
            # このファイル（slide_agent.py）からの相対パスで narration ディレクトリを探す
            # backend/agents/slide_agent.py -> backend/slides/narration/
            current_dir = os.path.dirname(os.path.abspath(__file__))
            backend_dir = os.path.dirname(current_dir)  # backend/

            narration_paths = [
                # backend/slides/narration/ (絶対パス)
                os.path.join(backend_dir, "slides", "narration", f"engineer-cafe-{language}.json"),
                # frontend/src/slides/narration/ (プロジェクトルートからの相対パス)
                os.path.join(
                    os.path.dirname(backend_dir),
                    "frontend",
                    "src",
                    "slides",
                    "narration",
                    f"engineer-cafe-{language}.json",
                ),
            ]

            for narration_path in narration_paths:
                if os.path.exists(narration_path):
                    with open(narration_path, "r", encoding="utf-8") as f:
                        self.narration_data = json.load(f)
                        self.total_slides = len(self.narration_data.get("slides", []))
                        logger.info(
                            f"Loaded narration from {narration_path}, total slides: {self.total_slides}"
                        )
                        return True

            logger.warning(f"Narration file not found for language: {language}")
            logger.debug(f"Searched paths: {narration_paths}")
            return False

        except Exception as e:
            logger.error(f"Error loading narration: {e}")
            return False

    async def handle_slide_action(
        self,
        action: SlideAction,
        query: Optional[str] = None,
        target_slide: Optional[int] = None,
        language: str = "ja",
        session_id: str = "default",
    ) -> Dict:
        """
        スライドアクションを処理

        Args:
            action: アクション（narrate, next, previous, goto, question）
            query: 質問（actionがquestionの場合）
            target_slide: 移動先スライド番号（actionがgotoの場合）
            language: 言語
            session_id: セッションID（マルチセッション対応）

        Returns:
            結果辞書 {answer, emotion, metadata, slideNumber}
        """
        # ナレーションデータが読み込まれていない場合は読み込む
        if not self.narration_data:
            self.load_narration(language)

        if action == "next":
            return self._handle_next_slide(language, session_id)
        elif action == "previous":
            return self._handle_previous_slide(language, session_id)
        elif action == "goto":
            return self._handle_goto_slide(target_slide or 1, language, session_id)
        elif action == "question":
            return await self._handle_slide_question(query or "", language, session_id)
        else:  # "narrate"
            current = self._get_current_slide(session_id)
            return self._handle_narrate_slide(current, language, session_id)

    def _handle_next_slide(self, language: str, session_id: str = "default") -> Dict:
        """次のスライドへ移動"""
        current = self._get_current_slide(session_id)
        if current >= self.total_slides:
            # 最後のスライド
            text = "これが最後のスライドです。" if language == "ja" else "This is the last slide."
            return {
                "answer": text,
                "emotion": "neutral",
                "metadata": {
                    "agent": "SlideAgent",
                    "action": "next",
                    "slideNumber": current,
                },
                "slideNumber": current,
            }

        self._set_current_slide(session_id, current + 1)
        return self._handle_narrate_slide(current + 1, language, session_id)

    def _handle_previous_slide(self, language: str, session_id: str = "default") -> Dict:
        """前のスライドへ移動"""
        current = self._get_current_slide(session_id)
        if current <= 1:
            # 最初のスライド
            text = "これが最初のスライドです。" if language == "ja" else "This is the first slide."
            return {
                "answer": text,
                "emotion": "neutral",
                "metadata": {
                    "agent": "SlideAgent",
                    "action": "previous",
                    "slideNumber": current,
                },
                "slideNumber": current,
            }

        self._set_current_slide(session_id, current - 1)
        return self._handle_narrate_slide(current - 1, language, session_id)

    def _handle_goto_slide(self, target_slide: int, language: str, session_id: str = "default") -> Dict:
        """指定スライドへ移動"""
        if target_slide < 1 or target_slide > self.total_slides:
            current = self._get_current_slide(session_id)
            text = (
                f"スライド番号は1から{self.total_slides}の間で指定してください。"
                if language == "ja"
                else f"Please specify a slide number between 1 and {self.total_slides}."
            )
            return {
                "answer": text,
                "emotion": "neutral",
                "metadata": {
                    "agent": "SlideAgent",
                    "action": "goto",
                    "slideNumber": current,
                },
                "slideNumber": current,
            }

        self._set_current_slide(session_id, target_slide)
        return self._handle_narrate_slide(target_slide, language, session_id)

    def _handle_narrate_slide(self, slide_number: int, language: str, session_id: str = "default") -> Dict:
        """スライドナレーションを取得"""
        slides = self.narration_data.get("slides", [])

        if slide_number < 1 or slide_number > len(slides):
            text = "スライドが見つかりません。" if language == "ja" else "Slide not found."
            return {
                "answer": text,
                "emotion": "neutral",
                "metadata": {
                    "agent": "SlideAgent",
                    "action": "narrate",
                    "slideNumber": slide_number,
                },
                "slideNumber": slide_number,
            }

        # スライドデータ取得（0-indexedなのでslide_number - 1）
        slide_data = slides[slide_number - 1]
        narration = slide_data.get("narration", {})
        auto_narration = narration.get("auto", "")

        # キャラクターアクションと感情を決定
        character_action = self._determine_character_action(slide_data)
        emotion = self._extract_emotion_from_slide_content(auto_narration)

        return {
            "answer": auto_narration,
            "emotion": emotion,
            "metadata": {
                "agent": "SlideAgent",
                "action": "narrate",
                "slideNumber": slide_number,
                "characterAction": character_action,
            },
            "slideNumber": slide_number,
        }

    async def _handle_slide_question(self, question: str, language: str, session_id: str = "default") -> Dict:
        """スライドに関する質問に回答"""
        slides = self.narration_data.get("slides", [])
        current = self._get_current_slide(session_id)

        if not slides or current < 1 or current > len(slides):
            text = (
                "現在のスライド情報が利用できません。"
                if language == "ja"
                else "Current slide information is not available."
            )
            return {
                "answer": text,
                "emotion": "neutral",
                "metadata": {
                    "agent": "SlideAgent",
                    "action": "question",
                    "slideNumber": current,
                },
                "slideNumber": current,
            }

        # 現在のスライドデータ
        slide_data = slides[current - 1]
        narration = slide_data.get("narration", {})
        on_demand = narration.get("onDemand", {})

        # onDemandに質問キーワードがあるか確認
        for keyword, answer in on_demand.items():
            if keyword.lower() in question.lower():
                return {
                    "answer": answer,
                    "emotion": "helpful",
                    "metadata": {
                        "agent": "SlideAgent",
                        "action": "question",
                        "slideNumber": current,
                    },
                    "slideNumber": current,
                }

        # キーワードマッチしない場合はLLMで回答生成
        try:
            auto_narration = narration.get("auto", "")
            prompt = self._build_question_prompt(question, auto_narration, on_demand, language)

            response_text = await self.llm_provider.generate(
                messages=[HumanMessage(content=prompt)],
                config=get_model_config("qa_response"),
            )

            return {
                "answer": response_text,
                "emotion": "helpful",
                "metadata": {
                    "agent": "SlideAgent",
                    "action": "question",
                    "slideNumber": current,
                },
                "slideNumber": current,
            }

        except Exception as e:
            logger.error(f"LLM error: {e}")
            text = (
                "申し訳ございません。回答を生成できませんでした。"
                if language == "ja"
                else "I'm sorry, I couldn't generate an answer."
            )
            return {
                "answer": text,
                "emotion": "apologetic",
                "metadata": {
                    "agent": "SlideAgent",
                    "action": "question",
                    "slideNumber": current,
                },
                "slideNumber": current,
            }

    def _build_question_prompt(
        self, question: str, auto_narration: str, on_demand: Dict, language: str
    ) -> str:
        """質問応答用のプロンプト構築"""
        on_demand_text = "\n".join([f"- {k}: {v}" for k, v in on_demand.items()])

        if language == "en":
            return f"""Based on the following slide content, answer the question.

Slide narration:
{auto_narration}

Available on-demand information:
{on_demand_text}

Question: {question}

Answer briefly and concisely (1-2 sentences)."""
        else:
            return f"""以下のスライド内容に基づいて質問に答えてください。

スライドナレーション:
{auto_narration}

オンデマンド情報:
{on_demand_text}

質問: {question}

簡潔に答えてください（1-2文）。"""

    def _determine_character_action(self, slide_data: Dict) -> str:
        """キャラクターアクションを決定"""
        narration = slide_data.get("narration", {})
        auto_narration = narration.get("auto", "").lower()

        if "welcome" in auto_narration or "ようこそ" in auto_narration:
            return "greeting"
        elif "service" in auto_narration or "サービス" in auto_narration:
            return "presenting"
        elif "price" in auto_narration or "料金" in auto_narration:
            return "explaining"
        elif "thank" in auto_narration or "ありがとう" in auto_narration:
            return "bowing"

        return "neutral"

    def _extract_emotion_from_slide_content(self, content: str) -> str:
        """スライド内容から感情を抽出"""
        content_lower = content.lower()

        if "welcome" in content_lower or "ようこそ" in content_lower:
            return "happy"
        elif "service" in content_lower or "サービス" in content_lower:
            return "confident"
        elif "thank" in content_lower or "ありがとう" in content_lower:
            return "grateful"

        return "neutral"
