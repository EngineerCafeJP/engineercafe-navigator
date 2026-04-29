"""
評価テスト用フィクスチャ
"""

import pytest
from typing import List, Dict, Any

from backend.tests.utils.evaluators.llm_judge import LLMJudgeEvaluator, QualityDimension
from backend.tests.utils.evaluators.routing_accuracy import (
    RoutingAccuracyEvaluator,
    RoutingTestCase,
)
from backend.tests.utils.evaluators.report_generator import EvaluationReportGenerator
from backend.tests.fixtures.dataset_loader import DatasetLoader


def pytest_configure(config):
    """pytest設定"""
    config.addinivalue_line("markers", "run_llm: mark test as requiring LLM API")
    config.addinivalue_line(
        "markers",
        "ragas: RAGAS evaluation tests (require OPENAI_API_KEY or OPENROUTER_API_KEY)",
    )


def pytest_collection_modifyitems(config, items):
    """LLMテストのスキップ処理"""
    if not config.getoption("--run-llm", default=False):
        skip_llm = pytest.mark.skip(reason="need --run-llm option to run")
        for item in items:
            if "run_llm" in item.keywords:
                item.add_marker(skip_llm)


def pytest_addoption(parser):
    """コマンドラインオプション追加"""
    parser.addoption(
        "--run-llm",
        action="store_true",
        default=False,
        help="run tests that require LLM API",
    )


@pytest.fixture
def llm_judge_evaluator() -> LLMJudgeEvaluator:
    """LLM Judge評価器フィクスチャ"""
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
    """ルーティング評価器フィクスチャ"""
    return RoutingAccuracyEvaluator()


@pytest.fixture
def report_generator(tmp_path) -> EvaluationReportGenerator:
    """レポート生成器フィクスチャ（一時ディレクトリ使用）"""
    return EvaluationReportGenerator(reports_dir=tmp_path)


@pytest.fixture
def routing_test_cases_ja() -> List[RoutingTestCase]:
    """日本語ルーティングテストケース"""
    return DatasetLoader.load_routing_test_cases(language="ja")


@pytest.fixture
def routing_test_cases_all() -> List[RoutingTestCase]:
    """全言語ルーティングテストケース"""
    return DatasetLoader.load_routing_test_cases()


@pytest.fixture
def fast_path_test_cases() -> List[RoutingTestCase]:
    """Fast-pathテストケース"""
    return DatasetLoader.load_fast_path_cases()


@pytest.fixture
def memory_test_cases() -> List[RoutingTestCase]:
    """メモリ関連テストケース"""
    return DatasetLoader.load_memory_cases()


@pytest.fixture
def sample_routing_results() -> List[Dict[str, Any]]:
    """サンプルルーティング結果"""
    return [
        {"agent": "facility", "category": "facility-info", "confidence": 0.95},
        {"agent": "general_knowledge", "category": "memory", "confidence": 0.88},
        {"agent": "facility", "category": "facility-info", "confidence": 0.92},
        {"agent": "event", "category": "event-info", "confidence": 0.85},
        {"agent": "facility", "category": "facility-info", "confidence": 0.90},
    ]


@pytest.fixture
def mock_router_func():
    """モックルーティング関数"""

    async def router(query: str, language: str) -> Dict[str, Any]:
        keyword_map = {
            "wi-fi": ("facility", "facility-info"),
            "wifi": ("facility", "facility-info"),
            "パスワード": ("facility", "facility-info"),
            "トイレ": ("facility", "facility-info"),
            "イベント": ("event", "event-info"),
            "勉強会": ("event", "event-info"),
            "起業": ("business_info", "business"),
            "スタートアップ": ("business_info", "business"),
            "さっき": ("general_knowledge", "memory"),
            "覚えて": ("general_knowledge", "memory"),
            "前に": ("general_knowledge", "memory"),
        }

        query_lower = query.lower()
        for keyword, (agent, category) in keyword_map.items():
            if keyword.lower() in query_lower:
                return {
                    "agent": agent,
                    "category": category,
                    "confidence": 0.9,
                }

        return {
            "agent": "general",
            "category": "general",
            "confidence": 0.5,
        }

    return router
