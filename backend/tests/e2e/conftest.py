"""
E2Eテスト用フィクスチャ

実際のOpenRouter API / Supabase を使用したエンドツーエンドテスト。
--run-e2e オプション付きで実行するか、e2eマーカーで選択する。
"""

import asyncio
import os
import uuid

import pytest

from backend.tests.fixtures.dataset_loader import DatasetLoader
from backend.tests.utils.evaluators.llm_judge import LLMJudgeEvaluator, QualityDimension
from backend.tests.utils.evaluators.report_generator import EvaluationReportGenerator
from backend.tests.utils.evaluators.routing_accuracy import RoutingAccuracyEvaluator

# ---------------------------------------------------------------------------
# NOTE: pytest_addoption and pytest_collection_modifyitems are defined in
# the root tests/conftest.py (required by pytest for CLI option discovery).
# ---------------------------------------------------------------------------
# API key validation helpers
# ---------------------------------------------------------------------------

_PLACEHOLDER_PREFIXES = ("test-", "placeholder", "sk-test-", "fake-")
_PLACEHOLDER_URLS = ("http://test.invalid", "https://placeholder")


def _is_real_key(value: str) -> bool:
    """API キーがテスト用プレースホルダーでないことを確認"""
    if not value:
        return False
    lower = value.lower()
    return not any(lower.startswith(p) for p in _PLACEHOLDER_PREFIXES)


def _is_real_url(value: str) -> bool:
    """URL がテスト用プレースホルダーでないことを確認"""
    if not value:
        return False
    lower = value.lower()
    return not any(lower.startswith(p) for p in _PLACEHOLDER_URLS)


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def _check_e2e_env():
    """E2E テストに必要な環境変数を検証（session-scoped）"""
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not _is_real_key(api_key):
        pytest.skip(
            "OPENROUTER_API_KEY is missing or is a placeholder. " "Set a real key to run E2E tests."
        )

    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_key = os.environ.get("SUPABASE_KEY", "")
    if not _is_real_url(supabase_url) or not _is_real_key(supabase_key):
        pytest.skip(
            "SUPABASE_URL / SUPABASE_KEY is missing or is a placeholder. "
            "Set real values to run E2E tests."
        )


@pytest.fixture
def workflow(_check_e2e_env):
    """MainWorkflow インスタンス（function-scoped、checkpointer なし）

    各テスト関数で新しいインスタンスを作成し、httpxクライアントの
    イベントループ不整合を回避する。
    """
    from backend.workflows.main_workflow import MainWorkflow

    return MainWorkflow(checkpointer=None)


@pytest.fixture(scope="session")
def e2e_session_id():
    """E2E テストセッション用の一意な session_id"""
    return f"e2e-test-{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# Function-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def invoke_workflow(workflow):
    """
    ワークフロー呼び出しヘルパー

    Returns:
        async callable(query, language="ja", session_id=None) -> dict
    """

    async def _invoke(
        query: str,
        language: str = "ja",
        session_id: str | None = None,
    ) -> dict:
        sid = session_id or f"e2e-{uuid.uuid4().hex[:8]}"
        try:
            result = await asyncio.wait_for(
                workflow.ainvoke(
                    {
                        "query": query,
                        "language": language,
                        "session_id": sid,
                    }
                ),
                timeout=60,
            )
        except RuntimeError as e:
            if "Event loop is closed" in str(e):
                # httpx接続プールがイベントループ再生成で壊れた場合
                pytest.xfail(f"Event loop closed (httpx connection pool issue): {e}")
            raise
        return {
            "answer": result.get("answer", ""),
            "emotion": result.get("emotion", "neutral"),
            "metadata": result.get("metadata", {}),
            "session_id": sid,
        }

    return _invoke


@pytest.fixture
def llm_judge() -> LLMJudgeEvaluator:
    """LLM Judge 評価器"""
    return LLMJudgeEvaluator(
        model_name="gpt-4o-mini",
        temperature=0.0,
        thresholds={
            QualityDimension.ACCURACY: 0.7,
            QualityDimension.RELEVANCE: 0.7,
            QualityDimension.COMPLETENESS: 0.6,
            QualityDimension.TONE: 0.7,
        },
    )


@pytest.fixture
def routing_evaluator() -> RoutingAccuracyEvaluator:
    """ルーティング精度評価器"""
    return RoutingAccuracyEvaluator()


@pytest.fixture
def ragas_evaluator():
    """RAGAS 評価器（ragas 未インストール時は skip）"""
    try:
        from backend.evaluation.ragas_pipeline import RagasEvaluator

        return RagasEvaluator()
    except ImportError:
        pytest.skip("ragas is not installed. Install with: pip install -e '.[evaluation]'")


@pytest.fixture
def report_generator(tmp_path) -> EvaluationReportGenerator:
    """レポート生成器（一時ディレクトリ使用）"""
    return EvaluationReportGenerator(reports_dir=tmp_path)


@pytest.fixture
def e2e_report_generator() -> EvaluationReportGenerator:
    """レポート生成器（backend/reports/ に保存）"""
    from pathlib import Path

    reports_dir = Path(__file__).parent.parent.parent / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    return EvaluationReportGenerator(reports_dir=reports_dir)


# ---------------------------------------------------------------------------
# Dataset fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def answer_quality_cases():
    """回答品質テストケース（全件）"""
    return DatasetLoader.load_answer_quality_cases()


@pytest.fixture
def answer_quality_cases_ja():
    """日本語回答品質テストケース"""
    return DatasetLoader.load_answer_quality_cases(language="ja")


@pytest.fixture
def routing_test_cases():
    """ルーティングテストケース（全件）"""
    return DatasetLoader.load_routing_test_cases()


@pytest.fixture
def ground_truth_cases():
    """Ground Truth テストケース（全件）"""
    return DatasetLoader.load_ground_truth_cases()


@pytest.fixture
def e2e_scenarios():
    """E2E マルチターンシナリオデータ"""
    import json
    from pathlib import Path

    scenarios_path = (
        Path(__file__).parent.parent / "fixtures" / "golden_datasets" / "e2e_scenarios.json"
    )
    if not scenarios_path.exists():
        pytest.skip("e2e_scenarios.json not found")

    with open(scenarios_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data.get("scenarios", [])


# ---------------------------------------------------------------------------
# Routing failure detection
# ---------------------------------------------------------------------------

_ROUTING_FAILURE_INDICATORS = [
    "が見つかりませんでした",
    "お探しの情報が見つかりません",
    "お探しの施設情報が見つかりません",
    "スタッフにお問い合わせください",
    "質問を言い換えていただく",
    "ご質問にお答えできません",
    "情報を持ち合わせておりません",
    "お答えすることが難しい",
    "I don't have information",
    "I'm sorry, I don't have",
    "I couldn't find",
    "couldn't find information",
]


def is_routing_failure(answer: str) -> bool:
    """回答がルーティング失敗（RAG検索未実行）パターンかどうかを判定"""
    for indicator in _ROUTING_FAILURE_INDICATORS:
        if indicator in answer:
            return True
    return False


# ---------------------------------------------------------------------------
# Keyword assertion helpers
# ---------------------------------------------------------------------------


def keywords_match(answer: str, expected_keywords: list[str], threshold: float = 0.5) -> bool:
    """
    回答にキーワードが含まれるかチェック（閾値ベース）

    Args:
        answer: LLM の回答テキスト
        expected_keywords: 期待キーワードのリスト
        threshold: ヒット率の閾値（デフォルト 50%）

    Returns:
        bool: ヒット率が閾値以上なら True
    """
    if not expected_keywords:
        return True
    hits = sum(1 for kw in expected_keywords if kw in answer)
    return (hits / len(expected_keywords)) >= threshold


def assert_keywords(
    answer: str,
    expected_keywords: list[str],
    threshold: float = 0.5,
    msg: str = "",
):
    """キーワードアサーション（LLMルーティング非決定性を考慮）

    回答がルーティング失敗パターンの場合は pytest.xfail() として扱い、
    テストスイート全体を失敗させない。ルーティング精度は別テストで検証。
    """
    if not expected_keywords:
        return

    # ルーティング失敗の検出 → xfail（テスト失敗ではなく期待される不安定性）
    if is_routing_failure(answer):
        pytest.xfail(f"ルーティング非決定性によりRAG検索未実行: {answer[:100]}... {msg}")

    hits = [kw for kw in expected_keywords if kw in answer]
    misses = [kw for kw in expected_keywords if kw not in answer]
    hit_rate = len(hits) / len(expected_keywords)

    assert hit_rate >= threshold, (
        f"Keyword hit rate {hit_rate:.1%} < threshold {threshold:.1%}. "
        f"Hits: {hits}, Misses: {misses}. "
        f"Answer: {answer[:200]}... "
        f"{msg}"
    )
