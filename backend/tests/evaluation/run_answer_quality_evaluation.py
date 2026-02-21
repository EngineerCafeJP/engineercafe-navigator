"""
エンドツーエンド回答品質評価スクリプト

各エージェント（business_info, facility, event）が正しくルーティングされた上で、
回答内容に期待されるキーワードが含まれるかを検証する。
ルーティングだけでなく「中身の正しさ」まで一気通貫でテストする。

実行方法:
    cd backend
    export $(cat .env.local | grep -v '^#' | xargs)
    python tests/evaluation/run_answer_quality_evaluation.py
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

# プロジェクトルート（backend）をパスに追加
backend_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_root))
parent_root = backend_root.parent
sys.path.insert(0, str(parent_root))


async def evaluate_answer_quality(max_cases: int = None) -> Dict[str, Any]:
    """
    MainWorkflow経由でE2E回答品質を評価

    ゴールデンデータセット(answer_quality.json)のテストケースを
    MainWorkflowに流し、ルーティング正確性 + 回答キーワード含有率を測定する。
    """
    from backend.workflows.main_workflow import MainWorkflow
    from tests.fixtures.dataset_loader import DatasetLoader

    workflow = MainWorkflow()

    # answer_quality.json からテストケースを読み込み
    aq_cases = DatasetLoader.load_answer_quality_cases()
    if not aq_cases:
        print("answer_quality.json にテストケースがありません")
        return {"error": "no test cases"}

    cases_to_test = aq_cases[:max_cases] if max_cases else aq_cases
    total = len(cases_to_test)

    print(f"\n{'='*60}")
    print("エンドツーエンド 回答品質評価")
    print(f"テストケース数: {total}")
    print(f"{'='*60}\n")

    results = []

    for i, case in enumerate(cases_to_test, 1):
        print(f"[{i}/{total}] {case.id}: {case.question[:50]}...")

        try:
            state = {
                "query": case.question,
                "session_id": f"eval-aq-{case.id}",
                "language": case.language,
                "messages": [],
                "routing": {},
                "answer": None,
                "emotion": None,
                "metadata": {},
                "context": {},
            }

            result = await workflow.graph.ainvoke(state)

            # ルーティング結果
            routed_agent = result.get("routing", {}).get("agent", "unknown")
            answer = result.get("answer", "")
            emotion = result.get("emotion", "")

            # キーワード検証

            # expected_answer に基づくキーワード検証
            if case.expected_answer:
                # expected_answer自体を直接チェックするのではなく、
                # answer_quality.json の expected_keywords フィールドを使う
                pass

            # 回答にキーワードが含まれるか（answer_quality.json のexpected_keywordsを使用）
            # DatasetLoaderのAnswerQualityCaseにはexpected_keywordsがないため、
            # JSON直接読み込みで取得
            json_data = DatasetLoader._load_json("answer_quality.json")
            json_case = next(
                (c for c in json_data.get("test_cases", []) if c["id"] == case.id),
                {},
            )
            expected_keywords = json_case.get("expected_keywords", [])
            expected_agent_json = json_case.get("expected_agent", "")

            keyword_hits = {}
            for kw in expected_keywords:
                keyword_hits[kw] = kw in (answer or "")

            keywords_found = sum(1 for v in keyword_hits.values() if v)
            keywords_total = len(keyword_hits)
            keyword_rate = keywords_found / keywords_total if keywords_total > 0 else 1.0

            routing_match = routed_agent == expected_agent_json

            status_icon = ""
            if routing_match and keyword_rate == 1.0:
                status_icon = "PASS"
            elif routing_match and keyword_rate > 0:
                status_icon = "PARTIAL"
            else:
                status_icon = "FAIL"

            print(
                f"  ルーティング: {routed_agent} (期待: {expected_agent_json}) {'OK' if routing_match else 'NG'}"
            )
            print(f"  キーワード: {keywords_found}/{keywords_total} ({keyword_rate:.0%})")
            if keyword_hits:
                for kw, found in keyword_hits.items():
                    mark = "+" if found else "-"
                    print(f"    [{mark}] {kw}")
            print(f"  感情: {emotion}")
            print(f"  判定: {status_icon}")
            print()

            results.append(
                {
                    "id": case.id,
                    "question": case.question,
                    "routed_agent": routed_agent,
                    "expected_agent": expected_agent_json,
                    "routing_correct": routing_match,
                    "answer_preview": (answer or "")[:200],
                    "emotion": emotion,
                    "expected_keywords": expected_keywords,
                    "keyword_hits": keyword_hits,
                    "keyword_rate": keyword_rate,
                    "status": status_icon,
                }
            )

        except Exception as e:
            print(f"  ERROR: {e}")
            results.append(
                {
                    "id": case.id,
                    "question": case.question,
                    "status": "ERROR",
                    "error": str(e),
                }
            )

    # サマリー
    total_cases = len(results)
    routing_ok = sum(1 for r in results if r.get("routing_correct"))
    pass_count = sum(1 for r in results if r.get("status") == "PASS")
    partial_count = sum(1 for r in results if r.get("status") == "PARTIAL")
    fail_count = sum(1 for r in results if r.get("status") in ("FAIL", "ERROR"))

    avg_keyword_rate = (
        sum(r.get("keyword_rate", 0) for r in results if "keyword_rate" in r) / total_cases
        if total_cases > 0
        else 0
    )

    print(f"\n{'='*60}")
    print("回答品質評価サマリー")
    print(f"{'='*60}")
    print(f"テストケース総数 : {total_cases}")
    print(f"ルーティング正解 : {routing_ok}/{total_cases} ({routing_ok/total_cases:.0%})")
    print(f"PASS (完全一致)  : {pass_count}")
    print(f"PARTIAL (部分)   : {partial_count}")
    print(f"FAIL/ERROR       : {fail_count}")
    print(f"平均キーワード率 : {avg_keyword_rate:.0%}")
    print(f"{'='*60}\n")

    # エージェント別の回答品質
    agent_quality: Dict[str, Dict] = {}
    for r in results:
        agent = r.get("expected_agent", "unknown")
        if agent not in agent_quality:
            agent_quality[agent] = {"total": 0, "pass": 0, "keyword_rates": []}
        agent_quality[agent]["total"] += 1
        if r.get("status") == "PASS":
            agent_quality[agent]["pass"] += 1
        if "keyword_rate" in r:
            agent_quality[agent]["keyword_rates"].append(r["keyword_rate"])

    print(f"{'エージェント':<20} {'PASS率':<12} {'平均KW率':<12}")
    print(f"{'─'*44}")
    for agent, stats in sorted(agent_quality.items()):
        pass_rate = stats["pass"] / stats["total"] if stats["total"] > 0 else 0
        avg_kw = (
            sum(stats["keyword_rates"]) / len(stats["keyword_rates"])
            if stats["keyword_rates"]
            else 0
        )
        print(f"{agent:<20} {pass_rate:.0%}          {avg_kw:.0%}")

    report = {
        "timestamp": datetime.now().isoformat(),
        "total": total_cases,
        "routing_accuracy": routing_ok / total_cases if total_cases > 0 else 0,
        "pass_count": pass_count,
        "partial_count": partial_count,
        "fail_count": fail_count,
        "avg_keyword_rate": avg_keyword_rate,
        "agent_quality": {
            agent: {
                "total": s["total"],
                "pass": s["pass"],
                "avg_keyword_rate": (
                    sum(s["keyword_rates"]) / len(s["keyword_rates"]) if s["keyword_rates"] else 0
                ),
            }
            for agent, s in agent_quality.items()
        },
        "details": results,
    }

    # レポート保存
    reports_dir = Path(__file__).parent / "reports"
    reports_dir.mkdir(exist_ok=True)
    report_file = reports_dir / f"answer_quality_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"レポート保存: {report_file}")

    return report


async def main():
    """メイン実行"""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("エラー: OPENROUTER_API_KEY が設定されていません")
        print("export $(cat .env.local | grep -v '^#' | xargs) を実行してください")
        return

    max_cases = int(os.getenv("EVAL_MAX_CASES", "6"))
    await evaluate_answer_quality(max_cases=max_cases)


if __name__ == "__main__":
    asyncio.run(main())
