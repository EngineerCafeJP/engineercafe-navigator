"""
Fast-path ルーティング精度テスト

ゴールデンデータセット(60ケース)に対して _try_fast_routing と
_is_memory_related_question を直接実行し、精度を定量的に測定する。
LLM呼び出し不要のため、高速かつ再現性100%。

改善履歴:
  - v1.0: rt-011 (飲食動詞) FAIL, rt-014 (会議室+階情報) FAIL → fast-path 25/38
  - v1.2: rt-011, rt-014 ともに PASS → fast-path 27/38
  - v1.3: キーワード拡張+FACILITY_EQUIPMENT fast-path追加 → fast-path 39/48
  - v1.4: バリアフリー/子連れ/撮影ケース追加+サブカテゴリ分割 → 45/54
  - v1.5: トイレ/フロア案内/会議室料金ケース追加+会議室料金複合ルール → 50/60
"""

import json
from pathlib import Path

import pytest

from backend.agents.orchestrator_agent import OrchestratorAgent

GOLDEN_DATASET_PATH = (
    Path(__file__).parent.parent / "fixtures" / "golden_datasets" / "routing_test_cases.json"
)


@pytest.fixture
def orchestrator():
    return OrchestratorAgent()


@pytest.fixture
def golden_cases():
    with open(GOLDEN_DATASET_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data["test_cases"]


class TestFastPathAccuracy:
    """fast-path + memory判定のみでの精度測定"""

    def _route_fast(self, orchestrator: OrchestratorAgent, query: str) -> dict | None:
        """fast-path か memory 判定で解決する場合の結果を返す"""
        # 1) fast-path
        result = orchestrator._try_fast_routing(query)
        if result:
            return result

        # 2) memory
        if orchestrator._is_memory_related_question(query):
            return {
                "agent": "memory_agent",
                "category": "memory",
                "request_type": "memory",
                "reasoning": "Memory keyword detected",
            }

        return None

    def test_all_golden_cases_fast_path_accuracy(self, orchestrator, golden_cases):
        """全60ケースに対するfast-path精度を算出"""
        fast_hit = 0
        fast_correct = 0
        fast_wrong = 0
        miss = 0
        details = {"correct": [], "wrong": [], "miss": []}

        for case in golden_cases:
            cid = case["id"]
            query = case["query"]
            expected_agent = case["expected_agent"]

            result = self._route_fast(orchestrator, query)

            if result is None:
                miss += 1
                details["miss"].append(cid)
            elif result["agent"] == expected_agent:
                fast_hit += 1
                fast_correct += 1
                details["correct"].append(cid)
            else:
                fast_hit += 1
                fast_wrong += 1
                details["wrong"].append(f"{cid}: expected={expected_agent}, got={result['agent']}")

        total = len(golden_cases)
        coverage = fast_hit / total  # fast-pathでカバーできた割合
        accuracy = fast_correct / total  # 全体正解率
        precision = fast_correct / fast_hit if fast_hit > 0 else 0  # fast-path正解率

        # レポート出力
        print(f"\n{'='*60}")
        print("Fast-Path ルーティング精度レポート")
        print(f"{'='*60}")
        print(f"テストケース総数 : {total}")
        print(f"fast-path ヒット : {fast_hit} ({coverage:.1%})")
        print(f"  正解            : {fast_correct}")
        print(f"  誤ルーティング  : {fast_wrong}")
        print(f"LLM fallback     : {miss}")
        print(f"{'─'*60}")
        print(f"全体正解率(accuracy)    : {accuracy:.1%}")
        print(f"fast-path精度(precision): {precision:.1%}")
        print(f"{'─'*60}")

        if details["wrong"]:
            print("誤ルーティング詳細:")
            for w in details["wrong"]:
                print(f"  {w}")

        if details["miss"]:
            print(f"LLM fallback ケース({len(details['miss'])}件):")
            for m in details["miss"]:
                print(f"  {m}")

        # 精度アサーション
        # v1.2: 27/38, v1.3: 39/48, v1.5: 50/60
        assert fast_correct >= 48, f"fast-path正解数 {fast_correct} < 48 (v1.5の期待値)"
        assert fast_wrong == 0, f"fast-pathで誤ルーティングが{fast_wrong}件: {details['wrong']}"
        assert precision == 1.0, f"fast-path精度(precision)が{precision:.1%} < 100%"

    def test_rt011_food_drink_verb_fixed(self, orchestrator):
        """rt-011: 飲食動詞が正しくfacilityにルーティングされる (改善ポイント)"""
        result = orchestrator._try_fast_routing("カフェでコーヒーは飲めますか？")
        assert result is not None, "rt-011 should be fast-pathed"
        assert result["agent"] == "facility"
        assert result["request_type"] == "food_drink"

    def test_rt014_meeting_room_floor_fixed(self, orchestrator):
        """rt-014: 会議室+階情報が正しくfacilityにルーティングされる (改善ポイント)"""
        result = orchestrator._try_fast_routing("2階の会議室を借りたいのですが")
        assert result is not None, "rt-014 should be fast-pathed"
        assert result["agent"] == "facility"
        assert result["request_type"] == "meeting_room"

    def test_memory_cases_detected(self, orchestrator, golden_cases):
        """日本語メモリケース(rt-002, rt-010, rt-015)がすべて検出される

        Note: rt-023 (English: "What did I ask before?") は "ask" vs "asked" の
        部分一致問題で未検出。英語メモリキーワード拡張は別Issue対応。
        """
        memory_cases_ja = [
            c
            for c in golden_cases
            if c["expected_agent"] == "memory_agent" and c["language"] == "ja"
        ]
        assert len(memory_cases_ja) >= 3, "ゴールデンデータに日本語メモリケースが不足"

        for case in memory_cases_ja:
            is_memory = orchestrator._is_memory_related_question(case["query"])
            assert is_memory, f"{case['id']}: '{case['query']}' がメモリ判定されない"

    def test_no_false_positives(self, orchestrator, golden_cases):
        """fast-path で誤ルーティング(false positive)がゼロ"""
        for case in golden_cases:
            result = self._route_fast(orchestrator, case["query"])
            if result is not None:
                assert result["agent"] == case["expected_agent"], (
                    f"{case['id']}: fast-path が {result['agent']} を返したが "
                    f"期待値は {case['expected_agent']}"
                )


class TestFastPathCoverage:
    """タグ別のfast-pathカバレッジ分析"""

    def _route_fast(self, orchestrator, query):
        result = orchestrator._try_fast_routing(query)
        if result:
            return result
        if orchestrator._is_memory_related_question(query):
            return {"agent": "memory_agent"}
        return None

    def test_fast_path_tagged_cases_coverage(self, orchestrator, golden_cases):
        """'fast-path'タグ付きケースのカバレッジ測定

        既知の未対応ケース（別Issue対応予定）:
          - rt-023: "What did I ask before?" - 英語 "ask" vs "asked" 部分一致
          - rt-027: "와이파이 비밀번호가 뭐예요?" - 韓国語WiFi未対応
          - rt-036: "お弁当を持ち込んで食べてもいいですか？" - "持ち込んで" vs "持ち込み" 活用形
        解決済み:
          - rt-003: "トイレはどこですか？" - TOILET_KEYWORDS追加で解決
          - rt-058: "会議室の料金を教えてください" - 会議室+料金複合ルールで解決
        """
        fp_cases = [c for c in golden_cases if "fast-path" in c.get("tags", [])]
        assert len(fp_cases) >= 25, f"fast-pathタグ付きケースが{len(fp_cases)}件しかない"

        resolved = 0
        failed = []
        for case in fp_cases:
            result = self._route_fast(orchestrator, case["query"])
            if result and result["agent"] == case["expected_agent"]:
                resolved += 1
            else:
                failed.append(case["id"])

        coverage = resolved / len(fp_cases)
        print(f"\nfast-pathタグ付きカバレッジ: {resolved}/{len(fp_cases)} ({coverage:.0%})")
        if failed:
            print(f"  未解決: {failed}")

        # v1.2: 11/16, v1.3: 18/22, v1.5: 28/32
        # 残りは別Issue（多言語対応, 活用形対応等）
        assert resolved >= 25, f"fast-pathタグ付き解決数 {resolved} < 25 (v1.5の期待値)"
        # 誤ルーティング(false positive)はゼロ
        for case in fp_cases:
            result = self._route_fast(orchestrator, case["query"])
            if result is not None:
                assert (
                    result["agent"] == case["expected_agent"]
                ), f"{case['id']}: 誤ルーティング {result['agent']} != {case['expected_agent']}"

    def test_coverage_by_agent(self, orchestrator, golden_cases):
        """エージェント別のfast-pathカバレッジ"""
        from collections import defaultdict

        agent_stats = defaultdict(lambda: {"total": 0, "covered": 0})

        for case in golden_cases:
            agent = case["expected_agent"]
            agent_stats[agent]["total"] += 1

            result = self._route_fast(orchestrator, case["query"])
            if result and result["agent"] == agent:
                agent_stats[agent]["covered"] += 1

        print(f"\n{'='*60}")
        print("エージェント別 fast-path カバレッジ")
        print(f"{'─'*60}")
        print(f"{'エージェント':<20} {'カバー':<8} {'合計':<8} {'率':<8}")
        print(f"{'─'*60}")

        for agent, stats in sorted(agent_stats.items()):
            rate = stats["covered"] / stats["total"] if stats["total"] > 0 else 0
            print(f"{agent:<20} {stats['covered']:<8} {stats['total']:<8} {rate:.0%}")

        # facility と memory_agent はカバレッジ高いはず
        assert agent_stats["facility"]["covered"] >= 25
        assert agent_stats["memory_agent"]["covered"] >= 3
