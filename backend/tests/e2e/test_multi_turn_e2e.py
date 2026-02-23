"""マルチターンE2Eテスト - 会話フロー・メモリ参照"""

import pytest

from backend.tests.e2e.conftest import assert_keywords


@pytest.mark.e2e
class TestMultiTurnE2E:
    async def test_first_visit_flow(self, invoke_workflow, e2e_session_id):
        """初回訪問フロー: EC紹介→営業時間→WiFi"""
        sid = f"{e2e_session_id}-visit"

        # Turn 1: EC紹介
        r1 = await invoke_workflow("エンジニアカフェって何ですか？", session_id=sid)
        assert r1["answer"]
        assert_keywords(r1["answer"], ["コワーキング", "無料"], threshold=0.5)

        # Turn 2: 営業時間
        r2 = await invoke_workflow("営業時間は何時までですか？", session_id=sid)
        assert r2["answer"]

        # Turn 3: WiFi
        r3 = await invoke_workflow("WiFiは使えますか？", session_id=sid)
        assert r3["answer"]

    async def test_makers_space_flow(self, invoke_workflow, e2e_session_id):
        """MAKER'sスペースフロー: 3Dプリンタ→フィラメント→レーザー"""
        sid = f"{e2e_session_id}-makers"

        r1 = await invoke_workflow("3Dプリンターを使いたいのですが", session_id=sid)
        assert r1["answer"]
        assert_keywords(r1["answer"], ["予約", "講習", "3D"], threshold=0.3)

        r2 = await invoke_workflow("フィラメントの料金は？", session_id=sid)
        assert r2["answer"]

        r3 = await invoke_workflow("レーザー加工機も使えますか？", session_id=sid)
        assert r3["answer"]

    @pytest.mark.xfail(
        strict=False,
        reason="メモリ参照はSupabaseチェックポインター永続化に依存（CI環境では不安定）",
    )
    async def test_memory_reference(self, invoke_workflow, e2e_session_id):
        """メモリ参照テスト"""
        sid = f"{e2e_session_id}-memory"

        await invoke_workflow("WiFiのパスワードを教えてください", session_id=sid)
        r2 = await invoke_workflow("さっき何を聞いたっけ？", session_id=sid)
        assert r2["answer"]
        # メモリが機能していれば WiFi に関する言及がある
        assert any(
            kw in r2["answer"].lower() for kw in ["wifi", "wi-fi", "パスワード"]
        ), f"メモリ参照が機能していない: {r2['answer'][:100]}"

    async def test_scenario_from_dataset(self, invoke_workflow, e2e_scenarios, e2e_session_id):
        """e2e_scenarios.json の最初のシナリオを実行"""
        if not e2e_scenarios:
            pytest.skip("No scenarios available")

        scenario = e2e_scenarios[0]
        sid = f"{e2e_session_id}-scn-{scenario['id']}"

        for turn in scenario["turns"]:
            result = await invoke_workflow(
                turn["query"],
                language=turn.get("language", "ja"),
                session_id=sid,
            )
            assert result["answer"], f"Turn {turn['turn']}: 回答が空です"
