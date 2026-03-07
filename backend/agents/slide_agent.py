"""
SlideAgent - スライドナレーターエージェント
スライドプレゼンテーションのナレーションと質問応答を担当
"""

import json
import os
from typing import Dict, Optional, Literal
from backend.llm import get_llm_provider, get_model_config

SlideAction = Literal["narrate", "next", "previous", "goto", "question"]


class SlideAgent:
    """スライドナレーターエージェント"""

    def __init__(self):
        """初期化"""
        self.llm_provider = get_llm_provider()
        self.narration_data: Dict = {}
        self.current_slide = 1
        self.total_slides = 0

    def load_narration(self, language: str = "ja") -> bool:
        """
        ナレーションJSONを読み込み

        Args:
            language: 言語（ja or en）

        Returns:
            読み込み成功: True, 失敗: False
        """
        try:
            # ナレーションファイルのパス
            # backend/slides/narration/ または frontend/src/slides/narration/
            narration_paths = [
                f"backend/slides/narration/engineer-cafe-{language}.json",
                f"frontend/src/slides/narration/engineer-cafe-{language}.json",
                f"../frontend/src/slides/narration/engineer-cafe-{language}.json",
            ]

            for narration_path in narration_paths:
                if os.path.exists(narration_path):
                    with open(narration_path, "r", encoding="utf-8") as f:
                        self.narration_data = json.load(f)
                        self.total_slides = len(self.narration_data.get("slides", []))
                        print(
                            f"[SlideAgent] Loaded narration from {narration_path}, total slides: {self.total_slides}"
                        )
                        return True

            print(f"[SlideAgent] Narration file not found for language: {language}")
            return False

        except Exception as e:
            print(f"[SlideAgent] Error loading narration: {e}")
            return False

    async def handle_slide_action(
        self,
        action: SlideAction,
        query: Optional[str] = None,
        target_slide: Optional[int] = None,
        language: str = "ja",
    ) -> Dict:
        """
        スライドアクションを処理

        Args:
            action: アクション（narrate, next, previous, goto, question）
            query: 質問（actionがquestionの場合）
            target_slide: 移動先スライド番号（actionがgotoの場合）
            language: 言語

        Returns:
            結果辞書 {answer, emotion, metadata, slideNumber}
        """
        # ナレーションデータが読み込まれていない場合は読み込む
        if not self.narration_data:
            self.load_narration(language)

        if action == "next":
            return self._handle_next_slide(language)
        elif action == "previous":
            return self._handle_previous_slide(language)
        elif action == "goto":
            return self._handle_goto_slide(target_slide or 1, language)
        elif action == "question":
            return await self._handle_slide_question(query or "", language)
        else:  # "narrate"
            return self._handle_narrate_slide(self.current_slide, language)

    def _handle_next_slide(self, language: str) -> Dict:
        """次のスライドへ移動"""
        if self.current_slide >= self.total_slides:
            # 最後のスライド
            text = "これが最後のスライドです。" if language == "ja" else "This is the last slide."
            return {
                "answer": text,
                "emotion": "neutral",
                "metadata": {
                    "agent": "SlideAgent",
                    "action": "next",
                    "slideNumber": self.current_slide,
                },
                "slideNumber": self.current_slide,
            }

        self.current_slide += 1
        return self._handle_narrate_slide(self.current_slide, language)

    def _handle_previous_slide(self, language: str) -> Dict:
        """前のスライドへ移動"""
        if self.current_slide <= 1:
            # 最初のスライド
            text = "これが最初のスライドです。" if language == "ja" else "This is the first slide."
            return {
                "answer": text,
                "emotion": "neutral",
                "metadata": {
                    "agent": "SlideAgent",
                    "action": "previous",
                    "slideNumber": self.current_slide,
                },
                "slideNumber": self.current_slide,
            }

        self.current_slide -= 1
        return self._handle_narrate_slide(self.current_slide, language)

    def _handle_goto_slide(self, target_slide: int, language: str) -> Dict:
        """指定スライドへ移動"""
        if target_slide < 1 or target_slide > self.total_slides:
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
                    "slideNumber": self.current_slide,
                },
                "slideNumber": self.current_slide,
            }

        self.current_slide = target_slide
        return self._handle_narrate_slide(self.current_slide, language)

    def _handle_narrate_slide(self, slide_number: int, language: str) -> Dict:
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

    async def _handle_slide_question(self, question: str, language: str) -> Dict:
        """スライドに関する質問に回答"""
        slides = self.narration_data.get("slides", [])

        if not slides or self.current_slide < 1 or self.current_slide > len(slides):
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
                    "slideNumber": self.current_slide,
                },
                "slideNumber": self.current_slide,
            }

        # 現在のスライドデータ
        slide_data = slides[self.current_slide - 1]
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
                        "slideNumber": self.current_slide,
                    },
                    "slideNumber": self.current_slide,
                }

        # キーワードマッチしない場合はLLMで回答生成
        try:
            auto_narration = narration.get("auto", "")
            prompt = self._build_question_prompt(question, auto_narration, on_demand, language)

            response_text = await self.llm_provider.generate(
                messages=[{"role": "user", "content": prompt}],
                config=get_model_config("qa_response"),
            )

            return {
                "answer": response_text,
                "emotion": "helpful",
                "metadata": {
                    "agent": "SlideAgent",
                    "action": "question",
                    "slideNumber": self.current_slide,
                },
                "slideNumber": self.current_slide,
            }

        except Exception as e:
            print(f"[SlideAgent] LLM error: {e}")
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
                    "slideNumber": self.current_slide,
                },
                "slideNumber": self.current_slide,
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
