from __future__ import annotations

import logging
import re
from datetime import timedelta
from typing import Any, Dict, List, Literal

from backend.utils.language_types import (
    DEFAULT_ERROR_RESPONSE,
    LANGUAGE_INSTRUCTION,
    SupportedLanguage,
)
from backend.utils.query_classifier import QueryClassifier

logger = logging.getLogger(__name__)

EmotionType = Literal["helpful", "apologetic", "neutral", "happy", "sad", "relaxed", "surprised"]


class GeneralKnowledgeResponseMixin:
    def _should_use_web_search_adaptive(self, query: str, context_signals=None) -> bool:
        """適応的Web検索判定

        context_signals が None の場合は静的判定にフォールバック。
        RAGキャッシュスコア高い + 具体性高い → Web検索不要
        RAGキャッシュスコア低い + 会話浅い → Web検索推奨
        """
        # Alpha strict mode: context quality alone must not enable web search.
        # Only explicit current-info markers may do so.
        return self._should_use_web_search(query)

    def _should_use_web_search(self, query: str) -> bool:
        """Web検索が必要かどうか判定"""
        from backend.agents import general_knowledge_agent as agent_module

        return agent_module.TavilySearchTool.should_use_web_search(query)

    def _resolve_general_mode(self, query: str, query_type: str) -> str:
        if query_type in {
            "assistant_profile",
            "daily_conversation",
            "general_light",
            "current_info",
            "deep_reasoning",
        }:
            return query_type
        lower_query = query.lower()
        if self._is_deep_reasoning_query(lower_query):
            return "deep_reasoning"
        if self._is_current_info_query(lower_query):
            return "current_info"
        if self._is_daily_conversation_query(lower_query):
            return "daily_conversation"
        return "general_light"

    @staticmethod
    def _is_current_info_query(lower_query: str) -> bool:
        if GeneralKnowledgeResponseMixin._is_date_only_query(lower_query):
            return False

        markers = (
            "最新",
            "現在",
            "ニュース",
            "天気",
            "気温",
            "雨",
            "検索",
            "動向",
            "トレンド",
            "latest",
            "current",
            "news",
            "weather",
            "temperature",
            "rain",
            "search",
            "trend",
            "updates",
        )
        return any(marker in lower_query for marker in markers)

    @staticmethod
    def _compact_query(query: str) -> str:
        return re.sub(r"[\s　]+", "", query.lower()).strip("!?？。、.,")

    @staticmethod
    def _is_date_only_query(query: str) -> bool:
        return QueryClassifier._is_date_only_query(query)

    @staticmethod
    def _is_current_time_query(query: str) -> bool:
        classifier = QueryClassifier()
        normalized = classifier._normalize_query(query)
        if QueryClassifier._is_date_only_query(normalized):
            return False
        return classifier._is_current_time_query(normalized)

    def _current_date_response(self, query: str, language: SupportedLanguage) -> Dict[str, Any]:
        compact = self._compact_query(query)
        from backend.agents import general_knowledge_agent as agent_module

        now = agent_module.get_now_jst()

        if any(
            marker in compact
            for marker in (
                "今週",
                "thisweek",
                "本周",
                "这周",
                "這周",
                "这个星期",
                "這個星期",
                "이번주",
                "금주",
            )
        ):
            start = now.date() - timedelta(days=now.weekday())
            end = start + timedelta(days=6)
            if language == "en":
                answer = (
                    f"[helpful]This week is {start.strftime('%B %-d, %Y')} "
                    f"through {end.strftime('%B %-d, %Y')} in Japan time."
                )
            elif language == "zh":
                answer = (
                    f"[helpful]本周是日本时间{start.year}年{start.month}月{start.day}日"
                    f"到{end.month}月{end.day}日。"
                )
            elif language == "ko":
                answer = (
                    f"[helpful]이번 주는 일본 시간 기준 {start.year}년 {start.month}월 "
                    f"{start.day}일부터 {end.month}월 {end.day}일까지입니다."
                )
            else:
                answer = (
                    f"[helpful]今週は{start.month}月{start.day}日から"
                    f"{end.month}月{end.day}日までです。"
                )
        else:
            offset = 0
            label_ja = "今日"
            label_en = "Today"
            label_zh = "今天"
            label_ko = "오늘"
            if "明日" in compact or "tomorrow" in compact or "明天" in compact or "내일" in compact:
                offset = 1
                label_ja = "明日"
                label_en = "Tomorrow"
                label_zh = "明天"
                label_ko = "내일"
            elif (
                "昨日" in compact
                or "yesterday" in compact
                or "昨天" in compact
                or "어제" in compact
            ):
                offset = -1
                label_ja = "昨日"
                label_en = "Yesterday"
                label_zh = "昨天"
                label_ko = "어제"

            target = now + timedelta(days=offset)
            weekdays_ja = ("月", "火", "水", "木", "金", "土", "日")
            weekdays_zh = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")
            weekdays_ko = ("월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일")
            if language == "en":
                answer = (
                    f"[helpful]{label_en} is {target.strftime('%A, %B %-d, %Y')} " "in Japan time."
                )
            elif language == "zh":
                answer = (
                    f"[helpful]{label_zh}是日本时间{target.year}年{target.month}月"
                    f"{target.day}日（{weekdays_zh[target.weekday()]}）。"
                )
            elif language == "ko":
                label_ko_with_particle = {
                    "오늘": "오늘은",
                    "내일": "내일은",
                    "어제": "어제는",
                }.get(label_ko, f"{label_ko}은")
                answer = (
                    f"[helpful]{label_ko_with_particle} 일본 시간 기준 "
                    f"{target.year}년 {target.month}월 "
                    f"{target.day}일({weekdays_ko[target.weekday()]})입니다."
                )
            else:
                answer = (
                    f"[helpful]{label_ja}は{target.year}年{target.month}月{target.day}日"
                    f"（{weekdays_ja[target.weekday()]}曜日）です。"
                )

        return {
            "answer": answer,
            "emotion": "helpful",
            "metadata": {
                "agent": self.name,
                "status": "success",
                "category": "general_knowledge",
                "request_type": "current-time",
                "route": "general_knowledge",
                "query_type": "current-time",
                "sources": ["system_clock"],
                "web_search_used": False,
                "rag_used": False,
                "provider_called": False,
                "timezone": "Asia/Tokyo",
            },
        }

    def _current_time_response(self, query: str, language: SupportedLanguage) -> Dict[str, Any]:
        from backend.agents import general_knowledge_agent as agent_module

        now = agent_module.get_now_jst()
        weekdays_ja = ("月", "火", "水", "木", "金", "土", "日")
        weekdays_zh = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")
        weekdays_ko = ("월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일")

        if language == "en":
            answer = (
                f"[helpful]The current Japan Standard Time is "
                f"{now.strftime('%H:%M')} on {now.strftime('%A, %B %-d, %Y')}."
            )
        elif language == "zh":
            answer = (
                f"[helpful]现在的日本标准时间是{now.year}年{now.month}月{now.day}日"
                f"（{weekdays_zh[now.weekday()]}）{now.hour}点{now.minute:02d}分。"
            )
        elif language == "ko":
            answer = (
                f"[helpful]현재 일본 표준시는 {now.year}년 {now.month}월 {now.day}일"
                f"({weekdays_ko[now.weekday()]}) {now.hour}시 {now.minute:02d}분입니다."
            )
        else:
            answer = (
                f"[helpful]今の日本標準時は{now.year}年{now.month}月{now.day}日"
                f"（{weekdays_ja[now.weekday()]}曜日）{now.hour}時{now.minute:02d}分です。"
            )

        return {
            "answer": answer,
            "emotion": "helpful",
            "metadata": {
                "agent": self.name,
                "status": "success",
                "category": "general_knowledge",
                "request_type": "current-time",
                "route": "general_knowledge",
                "query_type": "current-time",
                "sources": ["system_clock"],
                "web_search_used": False,
                "rag_used": False,
                "provider_called": False,
                "timezone": "Asia/Tokyo",
                "current_time_jst": now.isoformat(),
            },
        }

    @staticmethod
    def _is_deep_reasoning_query(lower_query: str) -> bool:
        markers = (
            "弁証法",
            "複雑推論",
            "比較分析",
            "多面的に分析",
            "深く考察",
            "詳細に考察",
            "dialectical",
            "complex reasoning",
            "comparative analysis",
            "analyze in depth",
            "deep reasoning",
        )
        return any(marker in lower_query for marker in markers)

    @staticmethod
    def _is_daily_conversation_query(lower_query: str) -> bool:
        markers = (
            "雑談",
            "おしゃべり",
            "少し話",
            "ちょっと話",
            "話し相手",
            "元気",
            "疲れた",
            "ひま",
            "暇",
            "ありがとう",
            "サンキュー",
            "small talk",
            "chat with me",
            "talk with me",
            "talk to me",
            "how are you",
            "i am tired",
            "i'm tired",
            "thanks",
            "thank you",
        )
        return any(marker in lower_query for marker in markers)

    @staticmethod
    def _normalize_current_info_query(query: str) -> str:
        lower_query = query.lower()
        asks_weather = any(
            marker in lower_query for marker in ("天気", "気温", "雨", "weather", "temperature")
        )
        has_location = any(
            marker in lower_query for marker in ("福岡", "fukuoka", "天神", "tenjin")
        )
        if asks_weather and not has_location:
            return f"福岡市 天神 {query}"
        return query

    # Hardcoded multilingual self-introduction. Must NEVER reference any LLM
    # provider (Google/OpenAI/etc). See issue #615 — web_search previously
    # leaked "I am trained by Google..." into identity replies.
    _ASSISTANT_PROFILE_MESSAGES: Dict[str, str] = {
        "ja": (
            "私はエンナビです。福岡市のエンジニアカフェの受付キオスクとして、"
            "施設利用、イベント、会員証、Wi-Fi、スライド案内に加えて、"
            "受付でよくある日常的な質問にもお答えします。"
            "「Wi-Fiを教えて」「イベントに参加したい」「施設を使いたい」のように聞いてください。"
        ),
        "en": (
            "I am EnNavi, the reception kiosk for Engineer Cafe in "
            "Fukuoka. I can help with facilities, events, membership check-in, Wi-Fi, "
            "slide guidance, and everyday questions visitors commonly ask at reception."
        ),
        "ko": (
            "저는 엔나비입니다. 후쿠오카의 엔지니어 카페 안내 키오스크로서, "
            "시설 이용, 이벤트, 회원증, Wi-Fi, 슬라이드 안내와 함께 접수처에서 자주 받는 "
            "일상적인 질문에도 답해 드립니다."
        ),
        "zh": (
            "我是 EnNavi，福冈工程师咖啡馆的前台导览终端。我可以为您介绍"
            "设施使用、活动信息、会员证、Wi-Fi、幻灯片导览，以及前台常见的日常问题。"
        ),
    }

    @classmethod
    def assistant_profile_message(cls, language: str) -> str:
        """Return the deterministic assistant self-introduction without constructing an agent."""
        return cls._ASSISTANT_PROFILE_MESSAGES.get(language, cls._ASSISTANT_PROFILE_MESSAGES["ja"])

    def _assistant_profile_response(self, language: SupportedLanguage) -> Dict[str, Any]:
        """Return the hardcoded self-introduction; never calls any LLM/web_search.

        Args:
            language: Visitor language (ja/en/ko/zh). Falls back to ja when unknown.

        Returns:
            Response dict with metadata.web_search_used=False and provider_called=False.
        """
        message = self.assistant_profile_message(language)
        logger.info(
            "Identity fast-path response served (language=%s, no LLM, no web_search)",
            language,
        )
        return {
            "answer": message,
            "emotion": "helpful",
            "metadata": {
                "agent": self.name,
                "status": "success",
                "category": "general_knowledge",
                "request_type": "assistant_profile",
                "route": "general_knowledge",
                "query_type": "assistant_profile",
                "sources": [],
                "web_search_used": False,
                "rag_used": False,
                "provider_called": False,
            },
        }

    def _daily_conversation_response(
        self, query: str, language: SupportedLanguage
    ) -> Dict[str, Any]:
        lower_query = query.lower()
        if any(
            marker in lower_query for marker in ("ありがとう", "サンキュー", "thanks", "thank you")
        ):
            message = (
                "どういたしまして。ほかにも気になることがあれば、気軽に聞いてください。"
                if language == "ja"
                else "You're welcome. Feel free to ask me anything else."
            )
        elif any(marker in lower_query for marker in ("疲れた", "i am tired", "i'm tired")):
            message = (
                "少し休憩しましょう。エンジニアカフェでは、落ち着いて作業したり一息ついたりできます。"
                if language == "ja"
                else "Take a short break. Engineer Cafe is a good place to settle in and recharge."
            )
        elif any(marker in lower_query for marker in ("元気", "how are you")):
            message = (
                "元気です。今日は受付として、施設案内でも雑談でもすぐお手伝いできます。"
                if language == "ja"
                else "I'm doing well. I can help with reception guidance or a quick casual chat."
            )
        else:
            message = (
                "もちろんです。短くお話ししましょう。施設のことでも、今日の過ごし方でも気軽に聞いてください。"
                if language == "ja"
                else (
                    "Of course. We can keep it light. Ask me about the facility "
                    "or anything practical for your visit."
                )
            )
        return {
            "answer": message,
            "emotion": "relaxed",
            "metadata": {
                "agent": self.name,
                "status": "success",
                "category": "general_knowledge",
                "request_type": "daily_conversation",
                "route": "general_knowledge",
                "query_type": "daily_conversation",
                "sources": [],
                "web_search_used": False,
                "rag_used": False,
                "provider_called": False,
            },
        }

    def _current_info_unavailable_response(self, language: SupportedLanguage) -> Dict[str, Any]:
        message = (
            "最新情報を確認できませんでした。少し時間をおいてもう一度聞いてください。"
            if language == "ja"
            else (
                "I couldn't confirm the latest information right now. "
                "Please ask again in a moment."
            )
        )
        return {
            "answer": message,
            "emotion": "apologetic",
            "metadata": {
                "agent": self.name,
                "status": "current_info_unavailable",
                "category": "general_knowledge",
                "request_type": "current_info",
                "route": "general_knowledge",
                "query_type": "current_info",
                "sources": [],
                "web_search_used": False,
                "rag_used": False,
            },
        }

    def _build_general_prompt(
        self,
        query: str,
        context: str,
        sources: List[str],
        language: SupportedLanguage,
        *,
        mode: str = "general_light",
    ) -> str:
        """プロンプトを構築"""
        source_info = " and ".join(sources) if sources else "available information"
        if not context:
            context = (
                "No trusted local or current external context was found. "
                "Answer from stable general knowledge only. Do not claim to have searched."
            )

        oral_instruction_ja = (
            "回答は口語（話し言葉）で返してください。"
            "Markdownの見出し・箇条書き・太字・表などは使わないでください。"
            "音声で読み上げた時に自然に聞こえるような文章にしてください。"
        )
        oral_instruction_en = (
            "Respond in natural spoken language. "
            "Do NOT use Markdown formatting such as "
            "headers, bullet points, bold, or tables. "
            "Write as if speaking aloud to someone."
        )

        # Multilingual: append language instruction for zh/ko
        lang_suffix = LANGUAGE_INSTRUCTION.get(language, "")
        scope_instruction_ja = (
            "あなた自身の正体を聞かれていない限り、モデル名や提供会社名を自分の正体として述べないでください。"
            "回答は受付での会話として短く自然にしてください。"
        )
        scope_instruction_en = (
            "Do not describe your model provider as your identity unless explicitly asked. "
            "Keep the answer short and natural for a reception conversation."
        )
        if mode == "current_info":
            scope_instruction_ja += (
                " 最新情報として扱う場合は、確認できた範囲で断定しすぎず答えてください。"
            )
            scope_instruction_en += (
                " For current information, answer only within what the provided context supports."
            )
        else:
            scope_instruction_ja += " 最新情報や検索結果を確認したとは言わないでください。"
            scope_instruction_en += " Do not say you checked current information or search results."

        if language == "en":
            header = (
                "Answer the following question using"
                f" the provided information from {source_info}."
            )
            prompt = f"""{header}

    IMPORTANT: Start your response with an emotion tag.
    Available emotions: [happy], [sad], [relaxed], [surprised], [helpful], [apologetic]

    Use [relaxed] for informational responses about general topics
    Use [happy] when sharing exciting tech news or positive information
    Use [surprised] for unexpected or innovative topics
    Use [helpful] for answering practical questions
    Use [apologetic] when unable to find complete information

    Question: {query}

    Information:
    {context}

    Provide a comprehensive but concise answer.
    If the information is from web search, mention that it's current information.
    Be helpful and informative.
    {scope_instruction_en}
    {oral_instruction_en}"""
            if lang_suffix:
                prompt += f"\n{lang_suffix}"
            return prompt
        else:
            prompt = f"""{source_info}から提供された情報を使用して、次の質問に答えてください。

    重要: 回答の最初に感情タグを付けてください。
    利用可能な感情: [happy], [sad], [relaxed], [surprised], [helpful], [apologetic]

    一般的なトピックの情報提供には[relaxed]を使用
    エキサイティングな技術ニュースやポジティブな情報には[happy]を使用
    予想外のトピックや革新的な内容には[surprised]を使用
    実用的な質問への回答には[helpful]を使用
    完全な情報が見つからない場合は[apologetic]を使用

    質問: {query}

    情報:
    {context}

    包括的だが簡潔な回答を提供してください。情報がウェブ検索からのものである場合は、それが最新の情報であることを述べてください。役立つ情報を提供してください。
    {scope_instruction_ja}
    {oral_instruction_ja}"""
            if lang_suffix:
                prompt += f"\n{lang_suffix}"
            return prompt

    def _calculate_confidence(self, sources: List[str]) -> float:
        """信頼度を計算"""
        has_kb = any(source.startswith("knowledge_base") for source in sources)
        has_web = "web_search" in sources

        if has_kb and has_web:
            return 0.9
        elif has_kb:
            return 0.8
        elif has_web:
            return 0.6
        else:
            return 0.3

    def _extract_emotion(self, text: str) -> EmotionType:
        """テキストから感情タグを抽出"""
        if "[sad]" in text:
            return "sad"
        elif "[happy]" in text:
            return "happy"
        elif "[relaxed]" in text:
            return "relaxed"
        elif "[surprised]" in text:
            return "surprised"
        elif "[apologetic]" in text:
            return "apologetic"
        else:
            return "neutral"

    def _handle_error(self, language: SupportedLanguage) -> Dict[str, Any]:
        """エラー時の処理"""
        message = DEFAULT_ERROR_RESPONSE.get(language, DEFAULT_ERROR_RESPONSE["ja"])

        logger.warning("GeneralKnowledgeAgent エラー")

        return {
            "answer": message,
            "emotion": "apologetic",
            "metadata": {
                "agent": self.name,
                "status": "error",
                "error": "internal_error",
            },
        }
