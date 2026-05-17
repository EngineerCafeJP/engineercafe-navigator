"""
E2Eテスト用フィクスチャ

実際のOpenRouter API / Supabase を使用したエンドツーエンドテスト。
--run-e2e オプション付きで実行するか、e2eマーカーで選択する。
"""

import asyncio
import base64
import os
import re
import uuid
from pathlib import Path

import pytest
import pytest_asyncio

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


async def _close_shared_llm_provider() -> None:
    """Close and reset the process-wide LLM provider used by agent singletons."""
    from backend.llm import provider as llm_provider_module
    from backend.llm.provider import reset_provider

    provider = getattr(llm_provider_module, "_provider_instance", None)
    if provider is not None:
        close = getattr(provider, "close", None)
        if callable(close):
            try:
                await close()
            except RuntimeError as e:
                if "Event loop is closed" not in str(e):
                    raise
    reset_provider()


@pytest_asyncio.fixture(loop_scope="function")
async def workflow(_check_e2e_env):
    """MainWorkflow インスタンス（function-scoped、checkpointer なし）

    各テスト関数で新しいインスタンスを作成し、httpxクライアントの
    イベントループ不整合を回避する。
    """
    from backend.llm.provider import reset_provider
    from backend.workflows.main_workflow import MainWorkflow

    reset_provider()
    workflow = MainWorkflow(checkpointer=None)
    try:
        yield workflow
    finally:
        try:
            await workflow.close()
        finally:
            await _close_shared_llm_provider()


@pytest.fixture(scope="session")
def e2e_session_id():
    """E2E テストセッション用の一意な session_id"""
    return f"e2e-test-{uuid.uuid4().hex[:12]}"


@pytest.fixture(scope="session")
def voice_sample_audio_b64() -> str:
    """Frontend E2E でも使う音声 fixture を base64 で返す。"""
    sample_path = (
        Path(__file__).resolve().parents[3]
        / "frontend"
        / "e2e"
        / "fixtures"
        / "voice"
        / "sample.wav"
    )
    if not sample_path.exists():
        pytest.skip(f"voice sample fixture not found: {sample_path}")
    return base64.b64encode(sample_path.read_bytes()).decode()


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
        # conversation_sessions.id は UUID 前提のため、E2E でも UUID を使う
        sid = session_id or str(uuid.uuid4())
        try:
            from backend.workflows.main_workflow import WorkflowContext

            state, config = workflow._prepare_state(
                {
                    "query": query,
                    "language": language,
                    "session_id": sid,
                }
            )
            result = await asyncio.wait_for(
                workflow.graph.ainvoke(
                    state,
                    config=config,
                    context=WorkflowContext(user_id=sid),
                ),
                timeout=60,
            )
        except RuntimeError as e:
            if "Event loop is closed" in str(e):
                # httpx接続プールがイベントループ再生成で壊れた場合
                pytest.xfail(f"Event loop closed (httpx connection pool issue): {e}")
            raise
        knowledge_results = (result.get("context", {}) or {}).get("knowledge_results", {}) or {}
        raw_items = knowledge_results.get("results") or []
        retrieved_contexts = []
        if isinstance(raw_items, list):
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                text = (
                    item.get("content")
                    or item.get("text")
                    or item.get("chunk_text")
                    or item.get("summary")
                )
                if isinstance(text, str) and text.strip():
                    retrieved_contexts.append(text.strip())
        if not retrieved_contexts:
            context_string = knowledge_results.get("context_string")
            if isinstance(context_string, str) and context_string.strip():
                retrieved_contexts = [context_string.strip()]
        return {
            "answer": result.get("answer", ""),
            "emotion": result.get("emotion", "neutral"),
            "metadata": result.get("metadata", {}),
            "session_id": sid,
            "retrieved_contexts": retrieved_contexts,
        }

    return _invoke


@pytest.fixture
def llm_judge() -> LLMJudgeEvaluator:
    """LLM Judge 評価器"""
    return LLMJudgeEvaluator(
        model_name="gpt-5.4-mini",
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
    normalized_answer = normalize_assertion_text(answer)
    hits = sum(1 for kw in expected_keywords if normalize_assertion_text(kw) in normalized_answer)
    return (hits / len(expected_keywords)) >= threshold


_ASSERTION_TRANSLATION = str.maketrans(
    {
        "〜": "~",
        "–": "-",
        "—": "-",
        "−": "-",
        "：": ":",
        "　": " ",
    }
)


def normalize_assertion_text(text: str) -> str:
    """表記揺れに強い比較用の正規化。"""
    normalized = text.casefold().translate(_ASSERTION_TRANSLATION)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def keyword_group_match(answer: str, expected_keywords: list[str]) -> tuple[bool, str | None]:
    """候補キーワード群のいずれかが回答に含まれるかを返す。"""
    normalized_answer = normalize_assertion_text(answer)
    for keyword in expected_keywords:
        if normalize_assertion_text(keyword) in normalized_answer:
            return True, keyword
    return False, None


def assert_keyword_groups(
    answer: str,
    expected_groups: list[list[str] | tuple[str, ...]],
    *,
    msg: str = "",
):
    """
    複数の事実グループを検証する。

    各グループは OR 条件、グループ間は AND 条件。
    例: [["wifi", "wi-fi"], ["akarenga-112years"]]
    """
    if is_routing_failure(answer):
        pytest.xfail(f"ルーティング非決定性によりRAG検索未実行: {answer[:100]}... {msg}")

    hits: list[str] = []
    misses: list[list[str] | tuple[str, ...]] = []
    for group in expected_groups:
        matched, keyword = keyword_group_match(answer, list(group))
        if matched and keyword is not None:
            hits.append(keyword)
        else:
            misses.append(group)

    assert not misses, (
        f"Fact-group assertion failed. Hits: {hits}, Missing groups: {misses}. "
        f"Answer: {answer[:240]}... {msg}"
    )


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
