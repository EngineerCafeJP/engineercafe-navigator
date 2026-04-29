"""
LLM-as-Judge評価器

LLMを使用して回答の品質を評価します。
意味的類似度、回答品質（accuracy, relevance, completeness, tone）を評価可能。
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, List

try:
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, SystemMessage

    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    ChatOpenAI = None
    HumanMessage = None
    SystemMessage = None


class QualityDimension(str, Enum):
    """回答品質の評価軸"""

    ACCURACY = "accuracy"  # 正確性
    RELEVANCE = "relevance"  # 関連性
    COMPLETENESS = "completeness"  # 完全性
    TONE = "tone"  # トーン/自然さ


@dataclass
class JudgeResult:
    """LLM Judge評価結果"""

    dimension: str
    score: float  # 0.0 - 1.0
    passed: bool
    reasoning: str
    threshold: float = 0.7
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SemanticSimilarityResult:
    """意味的類似度評価結果"""

    similarity_score: float  # 0.0 - 1.0
    is_similar: bool
    reasoning: str
    expected: str
    actual: str


class LLMJudgeEvaluator:
    """
    LLM-as-Judge評価器

    OpenAIのモデルを使用して回答品質を評価します。
    """

    def __init__(
        self,
        model_name: str = "gpt-5.4-mini",
        temperature: float = 0.0,
        thresholds: Optional[Dict[QualityDimension, float]] = None,
    ):
        """
        初期化

        Args:
            model_name: 使用するモデル名
            temperature: 生成時の温度パラメータ
            thresholds: 各評価軸の閾値
        """
        self.model_name = model_name
        self.temperature = temperature
        self.thresholds = thresholds or {
            QualityDimension.ACCURACY: 0.7,
            QualityDimension.RELEVANCE: 0.7,
            QualityDimension.COMPLETENESS: 0.6,
            QualityDimension.TONE: 0.7,
        }
        self._llm: Optional[ChatOpenAI] = None
        self._initialize_llm()

    def _initialize_llm(self) -> None:
        """LLMクライアントを初期化

        Priority:
            1. OPENAI_API_KEY → ChatOpenAI (直接)
            2. OPENROUTER_API_KEY → ChatOpenAI (OpenRouter経由)
        """
        if not LANGCHAIN_AVAILABLE:
            return

        api_key = os.getenv("OPENAI_API_KEY")
        base_url = None
        model_name = self.model_name

        if not api_key:
            api_key = os.getenv("OPENROUTER_API_KEY")
            if api_key:
                base_url = "https://openrouter.ai/api/v1"
                # OpenRouter requires provider-prefixed model names
                _openrouter_model_map = {
                    "gpt-5.4-mini": "openai/gpt-5.4-mini",
                    "gpt-5.4": "openai/gpt-5.4",
                    "gpt-4": "openai/gpt-4",
                }
                model_name = _openrouter_model_map.get(model_name, model_name)

        if api_key:
            try:
                kwargs = {
                    "model": model_name,
                    "temperature": self.temperature,
                    "api_key": api_key,
                }
                if base_url:
                    kwargs["openai_api_base"] = base_url
                self._llm = ChatOpenAI(**kwargs)
            except Exception:
                self._llm = None

    @property
    def is_available(self) -> bool:
        """LLMが利用可能かどうか"""
        return self._llm is not None

    async def evaluate_semantic_similarity(
        self,
        expected: str,
        actual: str,
        threshold: float = 0.7,
    ) -> SemanticSimilarityResult:
        """
        意味的類似度を評価

        Args:
            expected: 期待される回答
            actual: 実際の回答
            threshold: 類似度の閾値

        Returns:
            SemanticSimilarityResult: 評価結果
        """
        if not self.is_available:
            return SemanticSimilarityResult(
                similarity_score=0.0,
                is_similar=False,
                reasoning="LLM not available",
                expected=expected,
                actual=actual,
            )

        prompt = f"""あなたは意味的類似度を評価する専門家です。
以下の2つのテキストの意味的な類似度を評価してください。

【期待される回答】
{expected}

【実際の回答】
{actual}

以下の形式でJSONとして回答してください:
{{
    "similarity_score": 0.0から1.0の数値,
    "reasoning": "評価理由の説明"
}}

評価基準:
- 1.0: 完全に同じ意味
- 0.8-0.9: ほぼ同じ意味で、細部のみ異なる
- 0.6-0.7: 主要な意味は同じだが、いくつかの違いがある
- 0.4-0.5: 部分的に意味が重複
- 0.2-0.3: わずかな関連性のみ
- 0.0-0.1: 全く異なる意味
"""

        try:
            response = await self._llm.ainvoke([HumanMessage(content=prompt)])
            result = self._parse_json_response(response.content)

            score = float(result.get("similarity_score", 0.0))
            reasoning = result.get("reasoning", "")

            return SemanticSimilarityResult(
                similarity_score=score,
                is_similar=score >= threshold,
                reasoning=reasoning,
                expected=expected,
                actual=actual,
            )
        except Exception as e:
            return SemanticSimilarityResult(
                similarity_score=0.0,
                is_similar=False,
                reasoning=f"Evaluation error: {str(e)}",
                expected=expected,
                actual=actual,
            )

    async def evaluate_answer_quality(
        self,
        question: str,
        answer: str,
        language: str = "ja",
        context: Optional[str] = None,
        dimensions: Optional[List[QualityDimension]] = None,
    ) -> List[JudgeResult]:
        """
        回答品質を評価

        Args:
            question: 質問
            answer: 回答
            language: 言語コード（ja, en, zh, ko）
            context: コンテキスト情報
            dimensions: 評価する軸のリスト

        Returns:
            List[JudgeResult]: 各軸の評価結果
        """
        if dimensions is None:
            dimensions = list(QualityDimension)

        results = []
        for dimension in dimensions:
            result = await self._evaluate_dimension(
                question=question,
                answer=answer,
                dimension=dimension,
                language=language,
                context=context,
            )
            results.append(result)

        return results

    async def _evaluate_dimension(
        self,
        question: str,
        answer: str,
        dimension: QualityDimension,
        language: str,
        context: Optional[str] = None,
    ) -> JudgeResult:
        """
        単一の評価軸で評価

        Args:
            question: 質問
            answer: 回答
            dimension: 評価軸
            language: 言語コード
            context: コンテキスト情報

        Returns:
            JudgeResult: 評価結果
        """
        if not self.is_available:
            return JudgeResult(
                dimension=dimension.value,
                score=0.0,
                passed=False,
                reasoning="LLM not available",
                threshold=self.thresholds.get(dimension, 0.7),
            )

        criteria_map = {
            QualityDimension.ACCURACY: self._get_accuracy_criteria(language),
            QualityDimension.RELEVANCE: self._get_relevance_criteria(language),
            QualityDimension.COMPLETENESS: self._get_completeness_criteria(language),
            QualityDimension.TONE: self._get_tone_criteria(language),
        }

        criteria = criteria_map.get(dimension, "")
        context_section = f"\n【コンテキスト】\n{context}" if context else ""

        prompt = f"""あなたは回答品質を評価する専門家です。
以下の質問と回答について、{dimension.value}の観点で評価してください。

【質問】
{question}
{context_section}

【回答】
{answer}

【評価基準】
{criteria}

以下の形式でJSONとして回答してください:
{{
    "score": 0.0から1.0の数値,
    "reasoning": "評価理由の説明（日本語）"
}}
"""

        threshold = self.thresholds.get(dimension, 0.7)

        try:
            response = await self._llm.ainvoke([HumanMessage(content=prompt)])
            result = self._parse_json_response(response.content)

            score = float(result.get("score", 0.0))
            reasoning = result.get("reasoning", "")

            return JudgeResult(
                dimension=dimension.value,
                score=score,
                passed=score >= threshold,
                reasoning=reasoning,
                threshold=threshold,
            )
        except Exception as e:
            return JudgeResult(
                dimension=dimension.value,
                score=0.0,
                passed=False,
                reasoning=f"Evaluation error: {str(e)}",
                threshold=threshold,
            )

    def _get_accuracy_criteria(self, language: str) -> str:
        """正確性の評価基準を取得"""
        if language == "ja":
            return """
- 1.0: 事実として完全に正確
- 0.8-0.9: ほぼ正確だが、微細な誤りあり
- 0.6-0.7: 主要な情報は正確だが、一部不正確
- 0.4-0.5: 正確な情報と不正確な情報が混在
- 0.2-0.3: 大部分が不正確
- 0.0-0.1: 完全に不正確または虚偽
"""
        return """
- 1.0: Completely accurate
- 0.8-0.9: Mostly accurate with minor errors
- 0.6-0.7: Main information is accurate with some inaccuracies
- 0.4-0.5: Mix of accurate and inaccurate information
- 0.2-0.3: Mostly inaccurate
- 0.0-0.1: Completely inaccurate or false
"""

    def _get_relevance_criteria(self, language: str) -> str:
        """関連性の評価基準を取得"""
        if language == "ja":
            return """
- 1.0: 質問に完全に関連した回答
- 0.8-0.9: 高い関連性があり、質問に直接答えている
- 0.6-0.7: 関連性はあるが、やや脱線している
- 0.4-0.5: 部分的に関連
- 0.2-0.3: 関連性が低い
- 0.0-0.1: 質問と無関係
"""
        return """
- 1.0: Completely relevant to the question
- 0.8-0.9: Highly relevant, directly answers the question
- 0.6-0.7: Relevant but somewhat off-topic
- 0.4-0.5: Partially relevant
- 0.2-0.3: Low relevance
- 0.0-0.1: Unrelated to the question
"""

    def _get_completeness_criteria(self, language: str) -> str:
        """完全性の評価基準を取得"""
        if language == "ja":
            return """
- 1.0: 質問に対して必要な情報を全て網羅
- 0.8-0.9: ほぼ完全だが、わずかな追加情報があれば理想的
- 0.6-0.7: 主要な情報はカバーしているが、一部欠落
- 0.4-0.5: 半分程度の情報のみ
- 0.2-0.3: 重要な情報が大幅に欠落
- 0.0-0.1: ほとんど情報がない
"""
        return """
- 1.0: Covers all necessary information
- 0.8-0.9: Nearly complete with minor additions ideal
- 0.6-0.7: Covers main information with some gaps
- 0.4-0.5: Only about half the information
- 0.2-0.3: Significant missing information
- 0.0-0.1: Almost no information
"""

    def _get_tone_criteria(self, language: str) -> str:
        """トーン/自然さの評価基準を取得"""
        if language == "ja":
            return """
- 1.0: 自然で適切なトーン、読みやすい
- 0.8-0.9: 概ね自然だが、わずかに不自然な部分あり
- 0.6-0.7: トーンは適切だが、やや硬いまたは不自然
- 0.4-0.5: トーンに問題があり、読みにくい
- 0.2-0.3: 不適切なトーンまたは非常に不自然
- 0.0-0.1: 完全に不適切または理解困難
"""
        return """
- 1.0: Natural and appropriate tone, easy to read
- 0.8-0.9: Mostly natural with slight awkwardness
- 0.6-0.7: Appropriate tone but somewhat stiff or unnatural
- 0.4-0.5: Tone issues, difficult to read
- 0.2-0.3: Inappropriate tone or very unnatural
- 0.0-0.1: Completely inappropriate or incomprehensible
"""

    def _parse_json_response(self, content: str) -> Dict[str, Any]:
        """LLMレスポンスからJSONをパース"""
        import json
        import re

        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        return {}

    async def batch_evaluate(
        self,
        test_cases: List[Dict[str, Any]],
        dimensions: Optional[List[QualityDimension]] = None,
    ) -> List[Dict[str, Any]]:
        """
        バッチ評価を実行

        Args:
            test_cases: テストケースのリスト
                各ケースは{"question": str, "answer": str, "language": str}を含む
            dimensions: 評価する軸のリスト

        Returns:
            List[Dict[str, Any]]: 各テストケースの評価結果
        """
        results = []

        for case in test_cases:
            question = case.get("question", "")
            answer = case.get("answer", "")
            language = case.get("language", "ja")
            context = case.get("context")

            judge_results = await self.evaluate_answer_quality(
                question=question,
                answer=answer,
                language=language,
                context=context,
                dimensions=dimensions,
            )

            results.append(
                {
                    "test_case": case,
                    "results": [
                        {
                            "dimension": r.dimension,
                            "score": r.score,
                            "passed": r.passed,
                            "reasoning": r.reasoning,
                        }
                        for r in judge_results
                    ],
                    "overall_passed": all(r.passed for r in judge_results),
                    "average_score": (
                        sum(r.score for r in judge_results) / len(judge_results)
                        if judge_results
                        else 0.0
                    ),
                }
            )

        return results


def create_llm_judge(
    model_name: str = "gpt-5.4-mini",
    thresholds: Optional[Dict[QualityDimension, float]] = None,
) -> LLMJudgeEvaluator:
    """
    LLM Judge評価器を作成

    Args:
        model_name: 使用するモデル名
        thresholds: 各評価軸の閾値

    Returns:
        LLMJudgeEvaluator: 評価器インスタンス
    """
    return LLMJudgeEvaluator(model_name=model_name, thresholds=thresholds)
