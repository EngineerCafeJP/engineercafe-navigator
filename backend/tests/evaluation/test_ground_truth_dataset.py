"""
Ground Truthデータセットのバリデーションテスト
"""

import json
from pathlib import Path

import pytest

from backend.tests.fixtures.dataset_loader import DatasetLoader, GroundTruthCase

GROUND_TRUTH_PATH = (
    Path(__file__).parent.parent / "fixtures" / "golden_datasets" / "ground_truth.json"
)

REQUIRED_FIELDS = {"id", "question", "answer", "contexts", "ground_truth", "language", "category"}

REQUIRED_CATEGORIES = {
    "general",
    "hours",
    "pricing",
    "facility-info",
    "access",
    "consultation",
    "community",
    "event",
    "saino-cafe",
    "policy",
    "food_drink",
    "parking",
    "bicycle",
    "smoking",
    "toilet",
    "building",
}


@pytest.fixture
def raw_data():
    """JSON生データを読み込み"""
    with open(GROUND_TRUTH_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def all_cases():
    """全Ground Truthケースを読み込み"""
    return DatasetLoader.load_ground_truth_cases()


class TestGroundTruthDatasetStructure:
    """データセット構造のバリデーション"""

    def test_file_exists(self):
        """ファイルが存在すること"""
        assert GROUND_TRUTH_PATH.exists(), f"Ground truth file not found: {GROUND_TRUTH_PATH}"

    def test_valid_json(self, raw_data):
        """有効なJSONであること"""
        assert "version" in raw_data
        assert "test_cases" in raw_data
        assert isinstance(raw_data["test_cases"], list)

    def test_all_entries_have_required_fields(self, raw_data):
        """全エントリが必須フィールドを持つこと"""
        for case in raw_data["test_cases"]:
            missing = REQUIRED_FIELDS - set(case.keys())
            assert not missing, f"Entry {case.get('id', '?')} missing fields: {missing}"

    def test_contexts_is_nonempty_list(self, raw_data):
        """contextsが空でないリストであること"""
        for case in raw_data["test_cases"]:
            assert isinstance(case["contexts"], list), f"Entry {case['id']}: contexts is not a list"
            assert len(case["contexts"]) > 0, f"Entry {case['id']}: contexts is empty"

    def test_no_duplicate_ids(self, raw_data):
        """IDに重複がないこと"""
        ids = [case["id"] for case in raw_data["test_cases"]]
        assert len(ids) == len(set(ids)), f"Duplicate IDs found: {len(ids) - len(set(ids))}"

    def test_minimum_entry_count(self, raw_data):
        """最低60エントリ存在すること"""
        count = len(raw_data["test_cases"])
        assert count >= 60, f"Expected >= 60 entries, got {count}"


class TestGroundTruthDatasetCoverage:
    """カテゴリ・言語カバレッジのバリデーション"""

    def test_all_required_categories_covered(self, raw_data):
        """必要な全カテゴリが網羅されていること"""
        found_categories = {case["category"] for case in raw_data["test_cases"]}
        missing = REQUIRED_CATEGORIES - found_categories
        assert not missing, f"Missing categories: {missing}"

    def test_each_category_has_at_least_two_entries(self, raw_data):
        """各カテゴリに最低2エントリ存在すること"""
        category_counts: dict[str, int] = {}
        for case in raw_data["test_cases"]:
            cat = case["category"]
            category_counts[cat] = category_counts.get(cat, 0) + 1

        for cat in REQUIRED_CATEGORIES:
            count = category_counts.get(cat, 0)
            assert count >= 2, f"Category '{cat}' has only {count} entries (need >= 2)"

    def test_has_japanese_entries(self, raw_data):
        """日本語エントリが存在すること"""
        ja_count = sum(1 for c in raw_data["test_cases"] if c["language"] == "ja")
        assert ja_count > 0, "No Japanese entries found"

    def test_has_english_entries(self, raw_data):
        """英語エントリが存在すること"""
        en_count = sum(1 for c in raw_data["test_cases"] if c["language"] == "en")
        assert en_count > 0, "No English entries found"

    def test_has_chinese_entries(self, raw_data):
        """中国語エントリが存在すること"""
        zh_count = sum(1 for c in raw_data["test_cases"] if c["language"] == "zh")
        assert zh_count >= 10, f"Expected >= 10 Chinese entries, got {zh_count}"

    def test_has_korean_entries(self, raw_data):
        """韓国語エントリが存在すること"""
        ko_count = sum(1 for c in raw_data["test_cases"] if c["language"] == "ko")
        assert ko_count >= 10, f"Expected >= 10 Korean entries, got {ko_count}"

    def test_multilingual_extension_ids_exist(self, raw_data):
        """#382 の多言語拡張エントリが存在すること"""
        ids = {case["id"] for case in raw_data["test_cases"]}

        expected_en = {f"gt-{idx:03d}" for idx in range(88, 98)}
        expected_zh = {f"gt-{idx:03d}" for idx in range(98, 108)}
        expected_ko = {f"gt-{idx:03d}" for idx in range(108, 118)}

        assert expected_en <= ids
        assert expected_zh <= ids
        assert expected_ko <= ids

    def test_diagnostic_references_keep_registration_and_connpass_details(self, raw_data):
        """Live diagnostic references should not be terser than the canonical answer."""
        cases = {case["id"]: case for case in raw_data["test_cases"]}

        expected_terms = {
            "gt-090": ["5 to 10 minutes", "web form", "online pre-registration"],
            "gt-092": ["https://engineercafe.connpass.com/", "sign-up"],
            "gt-100": ["5到10分钟", "网页表单", "不能在线预先登记"],
            "gt-102": ["https://engineercafe.connpass.com/", "报名"],
            "gt-110": ["5분에서 10분", "웹 폼", "온라인 사전 등록"],
            "gt-112": ["https://engineercafe.connpass.com/", "참가 신청"],
        }

        for case_id, terms in expected_terms.items():
            ground_truth = cases[case_id]["ground_truth"]
            for term in terms:
                assert term in ground_truth, f"{case_id} ground_truth missing {term!r}"


class TestDatasetLoaderGroundTruth:
    """DatasetLoader.load_ground_truth_cases()のテスト"""

    def test_load_all(self, all_cases):
        """全件読み込みが成功すること"""
        assert len(all_cases) >= 60

    def test_returns_ground_truth_case_instances(self, all_cases):
        """GroundTruthCaseインスタンスを返すこと"""
        for case in all_cases:
            assert isinstance(case, GroundTruthCase)

    def test_language_filter_ja(self):
        """日本語フィルタが動作すること"""
        ja_cases = DatasetLoader.load_ground_truth_cases(language="ja")
        assert all(c.language == "ja" for c in ja_cases)
        assert len(ja_cases) > 0

    def test_language_filter_en(self):
        """英語フィルタが動作すること"""
        en_cases = DatasetLoader.load_ground_truth_cases(language="en")
        assert all(c.language == "en" for c in en_cases)
        assert len(en_cases) > 0

    def test_language_filter_zh(self):
        """中国語フィルタが動作すること"""
        zh_cases = DatasetLoader.load_ground_truth_cases(language="zh")
        assert all(c.language == "zh" for c in zh_cases)
        assert len(zh_cases) >= 10

    def test_language_filter_ko(self):
        """韓国語フィルタが動作すること"""
        ko_cases = DatasetLoader.load_ground_truth_cases(language="ko")
        assert all(c.language == "ko" for c in ko_cases)
        assert len(ko_cases) >= 10

    def test_category_filter(self):
        """カテゴリフィルタが動作すること"""
        facility_cases = DatasetLoader.load_ground_truth_cases(category="facility-info")
        assert all(c.category == "facility-info" for c in facility_cases)
        assert len(facility_cases) > 0

    def test_combined_filter(self):
        """言語+カテゴリの複合フィルタが動作すること"""
        filtered = DatasetLoader.load_ground_truth_cases(language="ja", category="general")
        assert all(c.language == "ja" and c.category == "general" for c in filtered)

    def test_nonexistent_language_returns_empty(self):
        """存在しない言語でフィルタすると空リストを返すこと"""
        cases = DatasetLoader.load_ground_truth_cases(language="xx")
        assert cases == []
