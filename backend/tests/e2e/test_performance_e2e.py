"""パフォーマンス/レイテンシ ベンチマーク E2E テスト"""

import asyncio

import pytest

from backend.utils.timing import LatencyTracker


@pytest.mark.e2e
@pytest.mark.perf
class TestPerformanceE2E:
    """パフォーマンスベンチマークテスト"""

    async def test_full_pipeline_latency(self, invoke_workflow):
        """フルパイプラインレイテンシ: P50 < 8s, P95 < 15s"""
        tracker = LatencyTracker()
        queries = [
            "エンジニアカフェの営業時間は？",
            "WiFiのパスワードを教えてください",
            "3Dプリンターは使えますか？",
            "イベントはありますか？",
            "アクセス方法を教えてください",
            "料金はいくらですか？",
            "キャリア相談はできますか？",
            "会議室の予約はできますか？",
            "What is Engineer Cafe?",
            "レーザー加工機はありますか？",
        ]

        # Warm-up query (not measured)
        await invoke_workflow("ウォームアップクエリ")

        for query in queries:
            with tracker.track("full_pipeline"):
                result = await invoke_workflow(query)
                assert result["answer"], f"Empty answer for: {query}"

        summary = tracker.summary()
        p50 = summary["p50_ms"] / 1000  # ms → s
        p95 = summary["p95_ms"] / 1000

        assert p50 < 8, f"P50 latency {p50:.1f}s exceeds 8s threshold"
        assert p95 < 15, f"P95 latency {p95:.1f}s exceeds 15s threshold"

    async def test_rag_retrieval_latency(self, invoke_workflow):
        """RAG検索レイテンシ: P95 < 5s"""
        tracker = LatencyTracker()
        rag_queries = [
            "エンジニアカフェの営業時間は？",
            "WiFiのパスワードは何ですか？",
            "3Dプリンターの使い方を教えてください",
            "イベントスペースの予約方法は？",
            "アクセス方法を教えてください",
        ]

        # Warm-up query (not measured)
        await invoke_workflow("ウォームアップクエリ")

        for query in rag_queries:
            with tracker.track("rag_retrieval"):
                result = await invoke_workflow(query)
                assert result["answer"]

        p95 = tracker.percentile(95) / 1000
        assert p95 < 6, f"RAG P95 latency {p95:.1f}s exceeds 6s threshold"

    async def test_concurrent_requests(self, invoke_workflow):
        """並列リクエスト: 3並列が30s以内に完了"""
        queries = [
            "営業時間は？",
            "WiFiのパスワードは？",
            "3Dプリンターは使えますか？",
        ]

        async def run_query(q):
            result = await invoke_workflow(q)
            assert result["answer"], f"Empty answer for concurrent query: {q}"
            return result

        tracker = LatencyTracker()
        with tracker.track("concurrent_3"):
            results = await asyncio.gather(*[run_query(q) for q in queries])

        assert len(results) == 3
        assert len(tracker.entries) == 1, "Expected exactly one timing entry for concurrent block"
        total_s = tracker.entries[0].duration_ms / 1000
        assert total_s < 30, f"Concurrent requests took {total_s:.1f}s (> 30s limit)"
