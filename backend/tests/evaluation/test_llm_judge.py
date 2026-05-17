"""
LLM Judge評価器のテスト
"""

import pytest
from unittest.mock import patch

from backend.tests.utils.evaluators.llm_judge import (
    LLMJudgeEvaluator,
    JudgeResult,
    QualityDimension,
    SemanticSimilarityResult,
    create_llm_judge,
)


class TestLLMJudgeEvaluator:
    """LLMJudgeEvaluatorのテスト"""

    def test_initialization(self):
        """初期化テスト"""
        evaluator = LLMJudgeEvaluator()

        assert evaluator.model_name == "gpt-5.4-mini"
        assert evaluator.temperature == 0.0
        assert QualityDimension.ACCURACY in evaluator.thresholds
        assert QualityDimension.RELEVANCE in evaluator.thresholds
        assert QualityDimension.COMPLETENESS in evaluator.thresholds
        assert QualityDimension.TONE in evaluator.thresholds

    def test_custom_thresholds(self):
        """カスタム閾値テスト"""
        custom_thresholds = {
            QualityDimension.ACCURACY: 0.9,
            QualityDimension.RELEVANCE: 0.8,
        }
        evaluator = LLMJudgeEvaluator(thresholds=custom_thresholds)

        assert evaluator.thresholds[QualityDimension.ACCURACY] == 0.9
        assert evaluator.thresholds[QualityDimension.RELEVANCE] == 0.8

    def test_is_available_without_api_key(self):
        """APIキーなしでの利用可能性テスト"""
        with patch.dict("os.environ", {}, clear=True):
            _ = LLMJudgeEvaluator()
            # 環境変数がない場合はFalse（ただしテスト環境による）

    @pytest.mark.asyncio
    async def test_evaluate_semantic_similarity_without_llm(self):
        """LLMなしでの意味的類似度評価テスト"""
        evaluator = LLMJudgeEvaluator()
        evaluator._llm = None  # 強制的にLLMを無効化

        result = await evaluator.evaluate_semantic_similarity(
            expected="こんにちは",
            actual="こんにちは",
        )

        assert isinstance(result, SemanticSimilarityResult)
        assert result.is_similar is False
        assert "not available" in result.reasoning.lower()

    @pytest.mark.asyncio
    async def test_evaluate_answer_quality_without_llm(self):
        """LLMなしでの回答品質評価テスト"""
        evaluator = LLMJudgeEvaluator()
        evaluator._llm = None

        results = await evaluator.evaluate_answer_quality(
            question="Wi-Fiのパスワードは？",
            answer="パスワードはengineer2025です",
            language="ja",
        )

        assert len(results) == 4  # 全4軸
        for result in results:
            assert isinstance(result, JudgeResult)
            assert result.passed is False

    @pytest.mark.asyncio
    async def test_evaluate_specific_dimensions(self):
        """特定の評価軸のみ評価テスト"""
        evaluator = LLMJudgeEvaluator()
        evaluator._llm = None

        results = await evaluator.evaluate_answer_quality(
            question="Wi-Fiのパスワードは？",
            answer="パスワードはengineer2025です",
            language="ja",
            dimensions=[QualityDimension.ACCURACY, QualityDimension.RELEVANCE],
        )

        assert len(results) == 2
        dimensions = {r.dimension for r in results}
        assert "accuracy" in dimensions
        assert "relevance" in dimensions

    @pytest.mark.asyncio
    async def test_batch_evaluate(self):
        """バッチ評価テスト"""
        evaluator = LLMJudgeEvaluator()
        evaluator._llm = None

        test_cases = [
            {
                "question": "Wi-Fiのパスワードは？",
                "answer": "engineer2025です",
                "language": "ja",
            },
            {
                "question": "営業時間は？",
                "answer": "10時から21時です",
                "language": "ja",
            },
        ]

        results = await evaluator.batch_evaluate(test_cases)

        assert len(results) == 2
        for result in results:
            assert "test_case" in result
            assert "results" in result
            assert "overall_passed" in result
            assert "average_score" in result

    def test_parse_json_response(self):
        """JSONパース テスト"""
        evaluator = LLMJudgeEvaluator()

        # 正常なJSON
        content = '{"score": 0.85, "reasoning": "良い回答です"}'
        result = evaluator._parse_json_response(content)
        assert result["score"] == 0.85
        assert result["reasoning"] == "良い回答です"

        # マークダウンコードブロック内のJSON
        content = '```json\n{"score": 0.75}\n```'
        result = evaluator._parse_json_response(content)
        assert result["score"] == 0.75

        # 不正なJSON
        content = "これはJSONではありません"
        result = evaluator._parse_json_response(content)
        assert result == {}

    def test_get_criteria_japanese(self):
        """日本語評価基準取得テスト"""
        evaluator = LLMJudgeEvaluator()

        accuracy_criteria = evaluator._get_accuracy_criteria("ja")
        assert "正確" in accuracy_criteria

        relevance_criteria = evaluator._get_relevance_criteria("ja")
        assert "関連" in relevance_criteria

        completeness_criteria = evaluator._get_completeness_criteria("ja")
        assert "網羅" in completeness_criteria or "完全" in completeness_criteria

        tone_criteria = evaluator._get_tone_criteria("ja")
        assert "自然" in tone_criteria

    def test_get_criteria_english(self):
        """英語評価基準取得テスト"""
        evaluator = LLMJudgeEvaluator()

        accuracy_criteria = evaluator._get_accuracy_criteria("en")
        assert "accurate" in accuracy_criteria.lower()

        relevance_criteria = evaluator._get_relevance_criteria("en")
        assert "relevant" in relevance_criteria.lower()


class TestCreateLLMJudge:
    """create_llm_judge関数のテスト"""

    def test_create_default(self):
        """デフォルト設定で作成"""
        evaluator = create_llm_judge()
        assert isinstance(evaluator, LLMJudgeEvaluator)
        assert evaluator.model_name == "gpt-5.4-mini"

    def test_create_with_custom_model(self):
        """カスタムモデルで作成"""
        evaluator = create_llm_judge(model_name="gpt-5.4")
        assert evaluator.model_name == "gpt-5.4"

    def test_create_with_custom_thresholds(self):
        """カスタム閾値で作成"""
        thresholds = {QualityDimension.ACCURACY: 0.95}
        evaluator = create_llm_judge(thresholds=thresholds)
        assert evaluator.thresholds[QualityDimension.ACCURACY] == 0.95


@pytest.mark.run_llm
class TestLLMJudgeWithAPI:
    """LLM APIを使用したテスト（--run-llmオプション必要）"""

    @pytest.mark.asyncio
    async def test_evaluate_semantic_similarity_with_llm(self, llm_judge_evaluator):
        """意味的類似度評価（LLM使用）"""
        if not llm_judge_evaluator.is_available:
            pytest.skip("LLM not available")

        result = await llm_judge_evaluator.evaluate_semantic_similarity(
            expected="Wi-Fiのパスワードはengineer2025です",
            actual="WiFiのパスワードはengineer2025になります",
        )

        assert result.similarity_score > 0.7
        assert result.is_similar is True

    @pytest.mark.asyncio
    async def test_evaluate_answer_quality_with_llm(self, llm_judge_evaluator):
        """回答品質評価（LLM使用）"""
        if not llm_judge_evaluator.is_available:
            pytest.skip("LLM not available")

        results = await llm_judge_evaluator.evaluate_answer_quality(
            question="Wi-Fiのパスワードを教えてください",
            answer="Wi-Fiのパスワードは「engineer2025」です。接続に問題がある場合はスタッフにお声がけください。",
            language="ja",
        )

        assert len(results) == 4
        accuracy_result = next(r for r in results if r.dimension == "accuracy")
        assert accuracy_result.score > 0.5


class TestLLMJudgeOpenRouterFallback:
    """OpenRouter フォールバックのテスト"""

    def test_openrouter_fallback_initializes_llm(self):
        """OPENROUTER_API_KEY のみでも LLM が初期化される"""
        env = {"OPENROUTER_API_KEY": "sk-or-test-key"}
        with patch.dict("os.environ", env, clear=True):
            with patch("backend.tests.utils.evaluators.llm_judge.ChatOpenAI") as mock_chat:
                mock_chat.return_value = "mock_llm"
                LLMJudgeEvaluator()
                mock_chat.assert_called_once()
                call_kwargs = mock_chat.call_args[1]
                assert call_kwargs["api_key"] == "sk-or-test-key"
                assert call_kwargs["openai_api_base"] == "https://openrouter.ai/api/v1"
                assert call_kwargs["model"] == "openai/gpt-5.4-mini"

    def test_openrouter_model_name_mapping(self):
        """OpenRouter 使用時にモデル名がプロバイダープレフィックス付きに変換される"""
        env = {"OPENROUTER_API_KEY": "sk-or-test-key"}
        with patch.dict("os.environ", env, clear=True):
            with patch("backend.tests.utils.evaluators.llm_judge.ChatOpenAI") as mock_chat:
                mock_chat.return_value = "mock_llm"
                LLMJudgeEvaluator(model_name="gpt-5.4")
                call_kwargs = mock_chat.call_args[1]
                assert call_kwargs["model"] == "openai/gpt-5.4"

    def test_openai_key_takes_priority(self):
        """OPENAI_API_KEY と OPENROUTER_API_KEY の両方がある場合は OPENAI が優先"""
        env = {
            "OPENAI_API_KEY": "sk-openai-test",
            "OPENROUTER_API_KEY": "sk-or-test",
        }
        with patch.dict("os.environ", env, clear=True):
            with patch("backend.tests.utils.evaluators.llm_judge.ChatOpenAI") as mock_chat:
                mock_chat.return_value = "mock_llm"
                LLMJudgeEvaluator()
                call_kwargs = mock_chat.call_args[1]
                assert call_kwargs["api_key"] == "sk-openai-test"
                assert "openai_api_base" not in call_kwargs

    def test_placeholder_openai_key_falls_back_to_openrouter(self):
        """pytest default OPENAI_API_KEY must not shadow a real OpenRouter key."""
        env = {
            "OPENAI_API_KEY": "test-openai-key",
            "OPENROUTER_API_KEY": "sk-or-test",
        }
        with patch.dict("os.environ", env, clear=True):
            with patch("backend.tests.utils.evaluators.llm_judge.ChatOpenAI") as mock_chat:
                mock_chat.return_value = "mock_llm"
                LLMJudgeEvaluator()
                call_kwargs = mock_chat.call_args[1]
                assert call_kwargs["api_key"] == "sk-or-test"
                assert call_kwargs["openai_api_base"] == "https://openrouter.ai/api/v1"
                assert call_kwargs["model"] == "openai/gpt-5.4-mini"

    def test_placeholder_keys_disable_llm(self):
        """Unit-test placeholders should not create a live judge client."""
        env = {
            "OPENAI_API_KEY": "test-openai-key",
            "OPENROUTER_API_KEY": "test-openrouter-key",
        }
        with patch.dict("os.environ", env, clear=True):
            evaluator = LLMJudgeEvaluator()
            assert evaluator.is_available is False

    def test_no_keys_no_llm(self):
        """API キーが未設定の場合は LLM なし"""
        with patch.dict("os.environ", {}, clear=True):
            evaluator = LLMJudgeEvaluator()
            assert evaluator.is_available is False


class TestJudgeResult:
    """JudgeResultのテスト"""

    def test_judge_result_creation(self):
        """JudgeResult作成テスト"""
        result = JudgeResult(
            dimension="accuracy",
            score=0.85,
            passed=True,
            reasoning="正確な回答です",
            threshold=0.7,
        )

        assert result.dimension == "accuracy"
        assert result.score == 0.85
        assert result.passed is True
        assert result.threshold == 0.7

    def test_judge_result_with_metadata(self):
        """メタデータ付きJudgeResult"""
        result = JudgeResult(
            dimension="relevance",
            score=0.6,
            passed=False,
            reasoning="関連性が低い",
            threshold=0.7,
            metadata={"test_id": "test-001"},
        )

        assert result.metadata["test_id"] == "test-001"


class TestSemanticSimilarityResult:
    """SemanticSimilarityResultのテスト"""

    def test_result_creation(self):
        """結果作成テスト"""
        result = SemanticSimilarityResult(
            similarity_score=0.85,
            is_similar=True,
            reasoning="意味が同じです",
            expected="こんにちは",
            actual="こんにちは！",
        )

        assert result.similarity_score == 0.85
        assert result.is_similar is True
        assert result.expected == "こんにちは"
        assert result.actual == "こんにちは！"
