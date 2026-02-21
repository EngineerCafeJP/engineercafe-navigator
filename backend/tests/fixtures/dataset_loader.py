"""
データセットローダー

ゴールデンデータセットの読み込みとフィルタリング機能を提供します。
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from tests.utils.evaluators.routing_accuracy import RoutingTestCase


@dataclass
class AnswerQualityCase:
    """回答品質テストケース"""

    id: str
    question: str
    language: str
    category: str = ""
    expected_answer: str = ""
    context: Optional[str] = None
    quality_expectations: Optional[Dict[str, float]] = None


@dataclass
class GroundTruthCase:
    """RAGAS評価用Ground Truthテストケース"""

    id: str
    question: str
    answer: str
    contexts: List[str] = field(default_factory=list)
    ground_truth: str = ""
    language: str = "ja"
    category: str = ""


class DatasetLoader:
    """
    ゴールデンデータセットローダー

    テストデータセットの読み込み、フィルタリング、変換を行います。
    """

    _datasets_dir: Path = Path(__file__).parent / "golden_datasets"

    @classmethod
    def load_routing_test_cases(
        cls,
        language: Optional[str] = None,
        tags: Optional[List[str]] = None,
        agents: Optional[List[str]] = None,
    ) -> List[RoutingTestCase]:
        """
        ルーティングテストケースを読み込み

        Args:
            language: フィルタする言語コード（None で全言語）
            tags: フィルタするタグのリスト（AND条件）
            agents: フィルタするエージェント名のリスト

        Returns:
            List[RoutingTestCase]: テストケースのリスト
        """
        data = cls._load_json("routing_test_cases.json")
        test_cases = data.get("test_cases", [])

        result = []
        for case in test_cases:
            if language and case.get("language") != language:
                continue

            if tags:
                case_tags = set(case.get("tags", []))
                if not all(tag in case_tags for tag in tags):
                    continue

            if agents and case.get("expected_agent") not in agents:
                continue

            result.append(
                RoutingTestCase(
                    id=case["id"],
                    query=case["query"],
                    expected_agent=case["expected_agent"],
                    expected_category=case.get("expected_category"),
                    language=case.get("language", "ja"),
                    tags=case.get("tags", []),
                    metadata=case.get("metadata", {}),
                )
            )

        return result

    @classmethod
    def load_answer_quality_cases(
        cls,
        language: Optional[str] = None,
        category: Optional[str] = None,
    ) -> List[AnswerQualityCase]:
        """
        回答品質テストケースを読み込み

        Args:
            language: フィルタする言語コード（None で全言語）
            category: フィルタするカテゴリ

        Returns:
            List[AnswerQualityCase]: テストケースのリスト
        """
        data = cls._load_json("answer_quality.json")
        test_cases = data.get("test_cases", [])

        result = []
        for case in test_cases:
            if language and case.get("language") != language:
                continue

            if category and case.get("category") != category:
                continue

            result.append(
                AnswerQualityCase(
                    id=case["id"],
                    question=case["question"],
                    language=case.get("language", "ja"),
                    category=case.get("category", ""),
                    expected_answer=case.get("expected_answer", ""),
                    context=case.get("context"),
                    quality_expectations=case.get("quality_expectations"),
                )
            )

        return result

    @classmethod
    def load_ground_truth_cases(
        cls,
        language: Optional[str] = None,
        category: Optional[str] = None,
    ) -> List[GroundTruthCase]:
        """
        Ground Truthテストケースを読み込み

        Args:
            language: フィルタする言語コード（None で全言語）
            category: フィルタするカテゴリ

        Returns:
            List[GroundTruthCase]: テストケースのリスト
        """
        data = cls._load_json("ground_truth.json")
        test_cases = data.get("test_cases", [])

        result = []
        for case in test_cases:
            if language and case.get("language") != language:
                continue

            if category and case.get("category") != category:
                continue

            result.append(
                GroundTruthCase(
                    id=case["id"],
                    question=case["question"],
                    answer=case["answer"],
                    contexts=case.get("contexts", []),
                    ground_truth=case.get("ground_truth", ""),
                    language=case.get("language", "ja"),
                    category=case.get("category", ""),
                )
            )

        return result

    @classmethod
    def load_multilingual_cases(
        cls,
        languages: Optional[List[str]] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        多言語テストケースを言語別にグループ化して読み込み

        Args:
            languages: 対象言語のリスト（None で全言語）

        Returns:
            Dict[str, List[Dict]]: 言語コードをキーとしたテストケースの辞書
        """
        all_languages = languages or ["ja", "en", "zh", "ko"]
        result: Dict[str, List[Dict[str, Any]]] = {}

        routing_data = cls._load_json("routing_test_cases.json")
        routing_cases = routing_data.get("test_cases", [])

        answer_data = cls._load_json("answer_quality.json")
        answer_cases = answer_data.get("test_cases", [])

        for lang in all_languages:
            result[lang] = []

            for case in routing_cases:
                if case.get("language") == lang:
                    result[lang].append(
                        {
                            "type": "routing",
                            "id": case["id"],
                            "query": case["query"],
                            "expected_agent": case["expected_agent"],
                            "tags": case.get("tags", []),
                        }
                    )

            for case in answer_cases:
                if case.get("language") == lang:
                    result[lang].append(
                        {
                            "type": "answer_quality",
                            "id": case["id"],
                            "question": case["question"],
                            "expected_answer": case.get("expected_answer", ""),
                            "category": case.get("category"),
                        }
                    )

        return result

    @classmethod
    def load_fast_path_cases(cls) -> List[RoutingTestCase]:
        """
        Fast-pathテストケースのみを読み込み

        Returns:
            List[RoutingTestCase]: Fast-pathタグを持つテストケース
        """
        return cls.load_routing_test_cases(tags=["fast-path"])

    @classmethod
    def load_memory_cases(cls) -> List[RoutingTestCase]:
        """
        メモリ関連テストケースを読み込み

        Returns:
            List[RoutingTestCase]: memoryタグを持つテストケース
        """
        return cls.load_routing_test_cases(tags=["memory"])

    @classmethod
    def get_dataset_info(cls) -> Dict[str, Any]:
        """
        データセット情報を取得

        Returns:
            Dict[str, Any]: データセットのメタ情報
        """
        routing_data = cls._load_json("routing_test_cases.json")
        answer_data = cls._load_json("answer_quality.json")

        routing_cases = routing_data.get("test_cases", [])
        answer_cases = answer_data.get("test_cases", [])

        languages = set()
        agents = set()
        tags = set()
        categories = set()

        for case in routing_cases:
            languages.add(case.get("language", "ja"))
            agents.add(case.get("expected_agent", ""))
            for tag in case.get("tags", []):
                tags.add(tag)
            if case.get("expected_category"):
                categories.add(case["expected_category"])

        for case in answer_cases:
            languages.add(case.get("language", "ja"))
            if case.get("category"):
                categories.add(case["category"])

        return {
            "routing_test_cases": {
                "total": len(routing_cases),
                "version": routing_data.get("version", "unknown"),
            },
            "answer_quality_cases": {
                "total": len(answer_cases),
                "version": answer_data.get("version", "unknown"),
            },
            "languages": sorted(list(languages)),
            "agents": sorted(list(agents)),
            "tags": sorted(list(tags)),
            "categories": sorted(list(categories)),
        }

    @classmethod
    def _load_json(cls, filename: str) -> Dict[str, Any]:
        """JSONファイルを読み込み"""
        filepath = cls._datasets_dir / filename
        if not filepath.exists():
            return {}

        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)


def load_routing_test_cases(
    language: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> List[RoutingTestCase]:
    """
    ルーティングテストケースを読み込み（便利関数）

    Args:
        language: フィルタする言語コード
        tags: フィルタするタグのリスト

    Returns:
        List[RoutingTestCase]: テストケースのリスト
    """
    return DatasetLoader.load_routing_test_cases(language=language, tags=tags)


def load_answer_quality_cases(
    language: Optional[str] = None,
    category: Optional[str] = None,
) -> List[AnswerQualityCase]:
    """
    回答品質テストケースを読み込み（便利関数）

    Args:
        language: フィルタする言語コード
        category: フィルタするカテゴリ

    Returns:
        List[AnswerQualityCase]: テストケースのリスト
    """
    return DatasetLoader.load_answer_quality_cases(language=language, category=category)


def load_ground_truth_cases(
    language: Optional[str] = None,
    category: Optional[str] = None,
) -> List[GroundTruthCase]:
    """
    Ground Truthテストケースを読み込み（便利関数）

    Args:
        language: フィルタする言語コード
        category: フィルタするカテゴリ

    Returns:
        List[GroundTruthCase]: テストケースのリスト
    """
    return DatasetLoader.load_ground_truth_cases(language=language, category=category)


def load_multilingual_cases(
    languages: Optional[List[str]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    多言語テストケースを読み込み（便利関数）

    Args:
        languages: 対象言語のリスト

    Returns:
        Dict[str, List[Dict]]: 言語コードをキーとしたテストケースの辞書
    """
    return DatasetLoader.load_multilingual_cases(languages=languages)
