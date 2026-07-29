"""受付フロー中の情報質問がバイパスされることの回帰テスト (#928)。

Bug: 受付セッション中に投げた情報質問が受付フローに消費され、
どのエージェントにも到達しないまま定型文が返る。

2026-07-25 の実地デモでは「赤レンガ文化会館について教えて」
「直近のエンジニアカフェで起きるイベントについて調べて」等が
4 ターン連続で飲まれた。

原因は 2 つ:
1. ``QueryClassifier`` が施設固有語を含まない質問を ``general`` に分類し、
   その ``general`` が除外カテゴリに入っていた
2. ``_looks_like_information_query`` が「調べて」「〜ますか」等の疑問形を
   マーカーに持っていなかった
"""

from __future__ import annotations

import pytest

from backend.workflows.main.routing import RoutingWorkflowMixin

# 受付フローが処理すべき発話。バイパスされてはいけない。
RECEPTION_UTTERANCES = [
    "こんにちは",
    "はじめまして",
    "初めて来ました",
    "見学に来ました",
    "会員登録したいです",
    "仕事をしに来ました",
    "勉強しに来ました",
    "作業しに来ました",
    "打ち合わせで来ました",
    "友達と来ました",
    "イベントに参加しに来ました",
    "登録はまだです",
    "名前は寺田です",
    "初回登録をお願いします",
    "はい",
    "うん、そう",
]

# 受付中でもエージェントへ回すべき情報質問。
INFORMATION_QUERIES = [
    "赤レンガ文化会館について教えて。",
    "直近のエンジニアカフェで起きるイベントについて調べて。",
    "会議室は使えますか。",
    "Wi-Fiのパスワードを教えて",
    "駐車場はありますか",
    "エンジニアカフェの営業時間は",
    "3Dプリンターって使えるの",
    "地下は何があるの",
    "休館日はいつ",
]


class TestLooksLikeInformationQuery:
    """疑問形の判定。受付発話への誤爆がないことが最重要。"""

    @pytest.mark.parametrize("utterance", RECEPTION_UTTERANCES)
    def test_reception_utterance_is_not_treated_as_information_query(self, utterance: str) -> None:
        """受付発話を情報質問と誤認しない（誤認すると受付フローが機能しなくなる）。"""
        assert RoutingWorkflowMixin._looks_like_information_query(utterance) is False

    @pytest.mark.parametrize("query", INFORMATION_QUERIES)
    def test_information_query_is_detected(self, query: str) -> None:
        assert RoutingWorkflowMixin._looks_like_information_query(query) is True

    def test_empty_query_is_not_an_information_query(self) -> None:
        assert RoutingWorkflowMixin._looks_like_information_query("   ") is False

    @pytest.mark.parametrize(
        "query",
        [
            "直近のイベントについて調べて",  # 「調べて」
            "会議室は使えますか",  # 「ますか」
            "3Dプリンターって使えるの",  # 「使える」
            "エンジニアカフェとは",  # 「とは」
            "地下には何があるの",  # 「何が」
        ],
    )
    def test_markers_added_for_issue_928(self, query: str) -> None:
        """#928 で追加したマーカーが効いていること。

        マーカーを削ると失敗する。
        """
        assert RoutingWorkflowMixin._looks_like_information_query(query) is True


class TestBypassExcludedCategories:
    """除外カテゴリの内容。"""

    def test_general_is_not_excluded(self) -> None:
        """``general`` を除外すると「赤レンガ文化会館について教えて」等が飲まれる (#928)。"""
        assert "general" not in RoutingWorkflowMixin._RECEPTION_BYPASS_EXCLUDED_CATEGORIES

    def test_conversational_categories_stay_excluded(self) -> None:
        """雑談・アシスタント紹介は受付フローに残す。"""
        excluded = RoutingWorkflowMixin._RECEPTION_BYPASS_EXCLUDED_CATEGORIES
        assert "daily_conversation" in excluded
        assert "assistant_profile" in excluded

    def test_eligible_stages(self) -> None:
        stages = RoutingWorkflowMixin._RECEPTION_BYPASS_ELIGIBLE_STAGES
        assert stages == frozenset({"greeting", "purpose_hearing", "routing"})
        assert "completed" not in stages


class TestClassifierCategories:
    """実際の QueryClassifier がどう分類するか（ルールベースのため外部依存なし）。"""

    @pytest.mark.asyncio
    async def test_red_brick_hall_classifies_as_general(self) -> None:
        """本 issue の起点となった質問。general に落ちることを固定する。

        general が除外カテゴリへ戻されたら、この分類のままでは再び飲まれる。
        """
        from backend.utils.query_classifier import QueryClassifier

        result = await QueryClassifier().classify_with_details("赤レンガ文化会館について教えて。")
        assert result.category == "general"
        assert result.category not in RoutingWorkflowMixin._RECEPTION_BYPASS_EXCLUDED_CATEGORIES
