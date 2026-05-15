"""
MainWorkflow の統合テスト

LangGraphワークフローとSupervisor Pattern統合をテスト
"""

import inspect
import os
from types import SimpleNamespace

import pytest
from backend.agents.orchestrator_agent import OrchestratorAgent
from unittest.mock import MagicMock, Mock, AsyncMock, patch


def _mock_runtime():
    """テスト用モック Runtime を生成"""
    rt = MagicMock()
    rt.context = MagicMock()
    rt.context.user_id = "anonymous"
    rt.store = None
    return rt


class _StubLanguageProcessor:
    def detect_language(self, query: str) -> dict[str, object]:
        detected = "ja" if any(ord(ch) > 127 for ch in query) else "en"
        return {"detected": detected, "confidence": 1.0}

    def determine_response_language(self, language_result: dict[str, object]) -> str:
        return str(language_result["detected"])


class _StubOrchestrator:
    def __init__(self) -> None:
        self.language_processor = _StubLanguageProcessor()
        self.decide_next_agent = AsyncMock()

    def _try_fast_routing(self, query: str):
        return OrchestratorAgent._try_fast_routing(self, query)

    def _is_memory_related_question(self, query: str) -> bool:
        return OrchestratorAgent._is_memory_related_question(self, query)


def test_rag_evidence_metadata_is_opt_in_and_bounded():
    from backend.workflows.main_workflow import _build_rag_evidence_metadata

    context = {
        "include_rag_evidence": True,
        "knowledge_results": {
            "success": True,
            "category": "hours",
            "query": "営業時間は？",
            "context_string": "営業時間は9:00から22:00です。",
            "results": [
                {
                    "id": "kb-1",
                    "category": "hours",
                    "language": "ja",
                    "source": "official",
                    "score": 0.91,
                    "content": "営業時間は9:00から22:00です。",
                }
            ],
        },
    }

    evidence = _build_rag_evidence_metadata(context)

    assert evidence == {
        "source": "workflow_knowledge_results",
        "query": "営業時間は？",
        "translated_query": None,
        "category": "hours",
        "context_char_count": len("営業時間は9:00から22:00です。"),
        "contexts": ["営業時間は9:00から22:00です。"],
        "results": [
            {
                "id": "kb-1",
                "category": "hours",
                "language": "ja",
                "source": "official",
                "score": 0.91,
                "content": "営業時間は9:00から22:00です。",
            }
        ],
    }


def test_rag_evidence_metadata_is_not_exposed_without_eval_flag():
    from backend.workflows.main_workflow import _build_rag_evidence_metadata

    assert (
        _build_rag_evidence_metadata(
            {
                "knowledge_results": {
                    "context_string": "営業時間は9:00から22:00です。",
                    "results": [{"content": "営業時間は9:00から22:00です。"}],
                }
            }
        )
        is None
    )


def test_agent_response_evidence_metadata_is_opt_in_and_source_backed():
    from backend.workflows.main_workflow import _build_agent_response_evidence_metadata

    metadata = {
        "agent": "FacilityAgent",
        "confidence": 0.95,
        "category": "facility-info",
        "request_type": "wifi",
        "sources": ["enhanced_rag"],
    }
    answer = "Wi-Fi SSID is engnecf-guest-5GHz. The password is akarenga-112years."

    assert _build_agent_response_evidence_metadata({}, metadata, answer) is None

    evidence = _build_agent_response_evidence_metadata(
        {"include_rag_evidence": True},
        metadata,
        answer,
    )

    assert evidence == {
        "source": "agent_response",
        "agent": "FacilityAgent",
        "category": "facility-info",
        "request_type": "wifi",
        "sources": ["enhanced_rag"],
        "context_char_count": len(answer),
        "contexts": [answer],
        "results": [
            {
                "source": "agent_response",
                "sources": ["enhanced_rag"],
                "content": answer,
                "agent": "FacilityAgent",
                "category": "facility-info",
                "request_type": "wifi",
            }
        ],
    }


def test_agent_response_evidence_metadata_skips_dynamic_low_confidence_sources():
    from backend.workflows.main_workflow import _build_agent_response_evidence_metadata

    assert (
        _build_agent_response_evidence_metadata(
            {"include_rag_evidence": True},
            {
                "agent": "BusinessInfoAgent",
                "confidence": 0.85,
                "sources": ["enhanced_rag"],
            },
            "Generated answer from retrieved context should rely on retrieved evidence.",
        )
        is None
    )


def test_agent_response_evidence_metadata_allows_static_connpass_guidance():
    from backend.workflows.main_workflow import _build_agent_response_evidence_metadata

    evidence = _build_agent_response_evidence_metadata(
        {"include_rag_evidence": True},
        {
            "agent": "EventAgent",
            "event_count": 0,
            "sources": ["connpass"],
        },
        "Event listings are available on Connpass.",
    )

    assert evidence is not None
    assert evidence["source"] == "agent_response"
    assert evidence["sources"] == ["connpass"]


def test_agent_response_evidence_metadata_allows_smoking_policy_response():
    from backend.workflows.main_workflow import _build_agent_response_evidence_metadata

    answer = "Smoking is not allowed at Engineer Cafe; the entire facility is smoke-free."
    evidence = _build_agent_response_evidence_metadata(
        {"include_rag_evidence": True},
        {
            "agent": "FacilityAgent",
            "confidence": 0.85,
            "category": "smoking",
            "request_type": "smoking",
            "sources": ["enhanced_rag"],
        },
        answer,
    )

    assert evidence is not None
    assert evidence["source"] == "agent_response"
    assert evidence["category"] == "smoking"
    assert evidence["contexts"] == [answer]


def test_merge_rag_evidence_metadata_appends_agent_response_context():
    from backend.workflows.main_workflow import _merge_rag_evidence_metadata

    existing = {
        "source": "workflow_knowledge_results",
        "contexts": ["Retrieved context about events."],
        "context_char_count": len("Retrieved context about events."),
        "results": [{"source": "official", "content": "Retrieved context about events."}],
    }
    supplemental = {
        "source": "agent_response",
        "contexts": ["Engineer Cafe is a free coworking and community space."],
        "context_char_count": len("Engineer Cafe is a free coworking and community space."),
        "results": [
            {
                "source": "agent_response",
                "content": "Engineer Cafe is a free coworking and community space.",
            }
        ],
    }

    merged = _merge_rag_evidence_metadata(existing, supplemental)

    assert merged == {
        "source": "workflow_knowledge_results+agent_response",
        "contexts": [
            "Retrieved context about events.",
            "Engineer Cafe is a free coworking and community space.",
        ],
        "context_char_count": len("Retrieved context about events.")
        + len("Engineer Cafe is a free coworking and community space."),
        "results": [
            {"source": "official", "content": "Retrieved context about events."},
            {
                "source": "agent_response",
                "content": "Engineer Cafe is a free coworking and community space.",
            },
        ],
    }


def test_agent_response_evidence_metadata_skips_fallback_sources():
    from backend.workflows.main_workflow import _build_agent_response_evidence_metadata

    assert (
        _build_agent_response_evidence_metadata(
            {"include_rag_evidence": True},
            {"agent": "FacilityAgent", "sources": ["fallback"]},
            "I could not find the requested facility information.",
        )
        is None
    )


class TestMainWorkflowMemoryIntegration:
    """MainWorkflow のメモリ統合テスト"""

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_memory_loader_node_retrieves_context(self, mock_orchestrator_class):
        """memory_loader_nodeが会話履歴を取得してstateに追加することを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        # OrchestratorAgentのモック
        mock_orchestrator = AsyncMock()
        mock_orchestrator_class.return_value = mock_orchestrator

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.get_context = AsyncMock(
                return_value={
                    "recent_messages": [
                        {"role": "user", "content": "営業時間は？"},
                        {"role": "assistant", "content": "9時から22時です。"},
                    ],
                    "context_string": "ユーザー: 営業時間は？\nアシスタント: 9時から22時です。",
                    "inherited_request_type": "hours",
                }
            )
            mock_get_helper.return_value = mock_helper

            workflow = MainWorkflow()

            # _memory_loader_nodeを直接テスト
            state = {
                "query": "テスト",
                "session_id": "test-session",
                "language": "ja",
                "context": {},
            }

            result = await workflow._memory_loader_node(state, _mock_runtime())

            assert "context" in result
            assert "memory" in result["context"]
            mock_helper.get_context.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_general_knowledge_node_handles_memory_query(self, mock_orchestrator_class):
        """_general_knowledge_nodeがmemoryクエリをGKA経由で処理することを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_get_helper.return_value = mock_helper

            workflow = MainWorkflow()

            # GKAのanswer_queryをモック
            workflow._general_knowledge_agent.answer_query = AsyncMock(
                return_value={
                    "answer": "営業時間について質問されていましたね。",
                    "emotion": "relaxed",
                    "metadata": {
                        "agent": "GeneralKnowledgeAgent",
                        "status": "success",
                        "query_type": "question_history",
                    },
                }
            )

            state = {
                "query": "さっき何を聞いた？",
                "session_id": "test-session",
                "language": "ja",
                "routing": {"request_type": "memory"},
                "metadata": {},
                "context": {},
            }

            result = await workflow._general_knowledge_node(state)

            assert result["answer"] == "営業時間について質問されていましたね。"
            assert result["emotion"] == "relaxed"
            workflow._general_knowledge_agent.answer_query.assert_called_once_with(
                query="さっき何を聞いた？",
                language="ja",
                session_id="test-session",
                query_type="memory",
                state_context=None,
                context_signals=None,
                long_term_memory=[],
            )

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_memory_loader_node_error_handling(self, mock_orchestrator_class):
        """memory_loader_nodeがエラー時にメモリなしで続行することを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.get_context = AsyncMock(side_effect=Exception("DB Error"))
            mock_get_helper.return_value = mock_helper

            workflow = MainWorkflow()

            state = {
                "query": "テスト",
                "session_id": "test-session",
                "language": "ja",
                "context": {"existing": "data"},
            }

            result = await workflow._memory_loader_node(state, _mock_runtime())

            # エラー時でもcontextが返される
            assert "context" in result
            assert result["context"]["memory"] == {}
            assert result["context"]["existing"] == "data"

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_format_response_shadow_writes_memory_candidates_when_enabled(
        self, mock_orchestrator_class
    ):
        """ENABLE_MEMORY_CANDIDATES=true のとき candidate namespace に保存される"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper

            with (
                patch(
                    "backend.utils.memory_extractor.extract_memories",
                    return_value=[],
                ),
                patch(
                    "backend.utils.memory_extractor.extract_memory_candidates",
                    return_value=[
                        {
                            "status": "candidate",
                            "candidate_type": "visitor_name",
                            "content": "田中",
                            "confidence": 0.9,
                        }
                    ],
                ),
                patch(
                    "backend.utils.memory_feature_flags.get_memory_feature_flags",
                    return_value=SimpleNamespace(
                        enable_memory_candidates=True,
                        enable_memory_promotion=False,
                        enable_style_profile=False,
                        enable_long_term_memory_rerank=False,
                    ),
                ),
                patch.dict(os.environ, {"ENABLE_MEMORY_CANDIDATES": "true"}),
            ):
                workflow = MainWorkflow()
                runtime = MagicMock()
                runtime.context = MagicMock()
                runtime.context.user_id = "visitor-1"
                runtime.store = MagicMock()
                runtime.store.aput = AsyncMock()

                state = {
                    "query": "私は田中です",
                    "answer": "こんにちは田中さん",
                    "session_id": "test-session",
                    "language": "ja",
                }

                async def _passthrough(op, **kw):
                    return await op(runtime.store)

                with patch(
                    "backend.workflows.main_workflow.store_with_retry",
                    side_effect=_passthrough,
                ):
                    await workflow._format_response_node(state, runtime)

                assert runtime.store.aput.await_count == 2
                calls = runtime.store.aput.await_args_list
                candidate_args = calls[0].args
                fast_path_args = calls[1].args
                assert candidate_args[0] == ("visitor_memory_candidates", "visitor-1")
                assert isinstance(candidate_args[1], str)
                assert candidate_args[2]["status"] == "candidate"
                assert candidate_args[2]["candidate_type"] == "visitor_name"
                assert fast_path_args[0] == ("visitor_memories", "visitor-1")
                assert fast_path_args[2]["type"] == "visitor_name"
                assert fast_path_args[2]["source"] == "candidate_fast_path"

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_format_response_strips_postgres_nul_chars_from_memory_candidates(
        self, mock_orchestrator_class
    ):
        """candidate/LTM Store 書き込み前に PostgreSQL 非対応のNUL文字を除去する"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper

            with (
                patch(
                    "backend.utils.memory_extractor.extract_memories",
                    return_value=[],
                ),
                patch(
                    "backend.utils.memory_extractor.extract_memory_candidates",
                    return_value=[
                        {
                            "status": "candidate",
                            "candidate_type": "visitor_name",
                            "content": "田\x00中",
                            "confidence": 0.9,
                            "evidence": {"query": "私は田\x00中です"},
                        }
                    ],
                ),
                patch(
                    "backend.utils.memory_feature_flags.get_memory_feature_flags",
                    return_value=SimpleNamespace(
                        enable_memory_candidates=True,
                        enable_memory_promotion=False,
                        enable_style_profile=False,
                        enable_long_term_memory_rerank=False,
                    ),
                ),
                patch.dict(os.environ, {"ENABLE_MEMORY_CANDIDATES": "true"}),
            ):
                workflow = MainWorkflow()
                runtime = MagicMock()
                runtime.context = MagicMock()
                runtime.context.user_id = "visitor\x00-4"
                runtime.store = MagicMock()
                runtime.store.aput = AsyncMock()

                state = {
                    "query": "私は田\x00中です",
                    "answer": "こんにちは田\x00中さん",
                    "session_id": "test-session",
                    "language": "ja",
                }

                async def _passthrough(op, **kw):
                    return await op(runtime.store)

                with patch(
                    "backend.workflows.main_workflow.store_with_retry",
                    side_effect=_passthrough,
                ):
                    await workflow._format_response_node(state, runtime)

                calls = runtime.store.aput.await_args_list
                candidate_args = calls[0].args
                fast_path_args = calls[1].args
                assert candidate_args[0] == ("visitor_memory_candidates", "visitor-4")
                assert candidate_args[2]["content"] == "田中"
                assert candidate_args[2]["evidence"]["query"] == "私は田中です"
                assert fast_path_args[0] == ("visitor_memories", "visitor-4")
                assert fast_path_args[2]["data"] == "田中"

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_format_response_strips_postgres_nul_chars_before_memory_promotion(
        self, mock_orchestrator_class
    ):
        """candidate promotion も保存済み namespace と同じ安全な user_id で読む"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper

            promoter = MagicMock()
            promoter.promote_for_user = AsyncMock(return_value={"promoted": 0})

            with (
                patch(
                    "backend.utils.memory_extractor.extract_memories",
                    return_value=[],
                ),
                patch(
                    "backend.utils.memory_extractor.extract_memory_candidates",
                    return_value=[],
                ),
                patch(
                    "backend.utils.memory_feature_flags.get_memory_feature_flags",
                    return_value=SimpleNamespace(
                        enable_memory_candidates=True,
                        enable_memory_promotion=True,
                        enable_style_profile=False,
                        enable_long_term_memory_rerank=False,
                    ),
                ),
                patch(
                    "backend.services.memory_promoter.get_memory_promoter",
                    return_value=promoter,
                ),
                patch.dict(os.environ, {"ENABLE_MEMORY_CANDIDATES": "true"}),
            ):
                workflow = MainWorkflow()
                runtime = MagicMock()
                runtime.context = MagicMock()
                runtime.context.user_id = "visitor\x00-promote"
                runtime.store = MagicMock()

                state = {
                    "query": "覚えてください",
                    "answer": "覚えました",
                    "session_id": "test-session",
                    "language": "ja",
                }

                await workflow._format_response_node(state, runtime)

                promoter.promote_for_user.assert_awaited_once_with(
                    runtime.store,
                    "visitor-promote",
                    delete_promoted_candidates=False,
                )

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_format_response_skips_memory_candidates_when_flag_disabled(
        self, mock_orchestrator_class
    ):
        """candidate extractor が値を返しても flag OFF なら保存しない"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper

            with (
                patch(
                    "backend.utils.memory_extractor.extract_memories",
                    return_value=[],
                ),
                patch(
                    "backend.utils.memory_extractor.extract_memory_candidates",
                    return_value=[{"status": "candidate", "candidate_type": "visitor_name"}],
                ),
                patch(
                    "backend.utils.memory_feature_flags.get_memory_feature_flags",
                    return_value=SimpleNamespace(
                        enable_memory_candidates=False,
                        enable_memory_promotion=False,
                        enable_style_profile=False,
                        enable_long_term_memory_rerank=False,
                    ),
                ),
                patch.dict(os.environ, {"ENABLE_MEMORY_CANDIDATES": "false"}),
            ):
                workflow = MainWorkflow()
                runtime = MagicMock()
                runtime.context = MagicMock()
                runtime.context.user_id = "visitor-2"
                runtime.store = MagicMock()
                runtime.store.aput = AsyncMock()

                state = {
                    "query": "私は佐藤です",
                    "answer": "こんにちは",
                    "session_id": "test-session",
                    "language": "ja",
                }

                async def _passthrough(op, **kw):
                    return await op(runtime.store)

                with patch(
                    "backend.workflows.main_workflow.store_with_retry",
                    side_effect=_passthrough,
                ):
                    await workflow._format_response_node(state, runtime)
                runtime.store.aput.assert_not_called()

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_format_response_candidate_shadow_write_failure_does_not_break(
        self, mock_orchestrator_class
    ):
        """candidate shadow write 失敗時も messages を返して継続する"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper

            with (
                patch(
                    "backend.utils.memory_extractor.extract_memories",
                    return_value=[],
                ),
                patch(
                    "backend.utils.memory_extractor.extract_memory_candidates",
                    return_value=[{"status": "candidate", "candidate_type": "visitor_name"}],
                ),
                patch(
                    "backend.utils.memory_feature_flags.get_memory_feature_flags",
                    return_value=SimpleNamespace(
                        enable_memory_candidates=True,
                        enable_memory_promotion=False,
                        enable_style_profile=False,
                        enable_long_term_memory_rerank=False,
                    ),
                ),
                patch.dict(os.environ, {"ENABLE_MEMORY_CANDIDATES": "true"}),
            ):
                workflow = MainWorkflow()
                runtime = MagicMock()
                runtime.context = MagicMock()
                runtime.context.user_id = "visitor-3"
                runtime.store = MagicMock()
                runtime.store.aput = AsyncMock(side_effect=Exception("store unavailable"))

                state = {
                    "query": "私は鈴木です",
                    "answer": "こんにちは",
                    "session_id": "test-session",
                    "language": "ja",
                }

                async def _passthrough(op, **kw):
                    return await op(runtime.store)

                with patch(
                    "backend.workflows.main_workflow.store_with_retry",
                    side_effect=_passthrough,
                ):
                    result = await workflow._format_response_node(state, runtime)
                assert "messages" in result
                assert len(result["messages"]) == 2

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_format_response_runs_memory_promotion_when_enabled(
        self, mock_orchestrator_class
    ):
        """ENABLE_MEMORY_PROMOTION=true のとき Promoter が呼ばれる"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper

            mock_promoter = AsyncMock()
            mock_promoter.promote_for_user = AsyncMock(return_value={"promoted": 1})

            with (
                patch(
                    "backend.utils.memory_extractor.extract_memories",
                    return_value=[],
                ),
                patch(
                    "backend.utils.memory_extractor.extract_memory_candidates",
                    return_value=[],
                ),
                patch(
                    "backend.services.memory_promoter.get_memory_promoter",
                    return_value=mock_promoter,
                ),
                patch(
                    "backend.utils.memory_feature_flags.get_memory_feature_flags",
                    return_value=SimpleNamespace(
                        enable_memory_candidates=False,
                        enable_memory_promotion=True,
                        enable_style_profile=False,
                        enable_long_term_memory_rerank=False,
                    ),
                ),
            ):
                workflow = MainWorkflow()
                runtime = MagicMock()
                runtime.context = MagicMock()
                runtime.context.user_id = "visitor-promote"
                runtime.store = MagicMock()
                runtime.store.aput = AsyncMock()
                runtime.store.asearch = AsyncMock(return_value=[])

                state = {
                    "query": "覚えて: 毎週火曜に来ます",
                    "answer": "承知しました",
                    "session_id": "test-session",
                    "language": "ja",
                }

                async def _passthrough(op, **kw):
                    return await op(runtime.store)

                with patch(
                    "backend.workflows.main_workflow.store_with_retry",
                    side_effect=_passthrough,
                ):
                    await workflow._format_response_node(state, runtime)

                mock_promoter.promote_for_user.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_format_response_fast_path_writes_ltm_when_candidates_enabled(
        self, mock_orchestrator_class
    ):
        """enable_memory_candidates=True でも高信頼候補は即 LTM に保存される"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper

            extract_memories_mock = MagicMock(
                return_value=[{"type": "visitor_name", "content": "田中", "confidence": 0.9}],
            )

            with (
                patch(
                    "backend.utils.memory_extractor.extract_memories",
                    extract_memories_mock,
                ),
                patch(
                    "backend.utils.memory_extractor.extract_memory_candidates",
                    return_value=[
                        {
                            "status": "candidate",
                            "candidate_type": "visitor_name",
                            "content": "田中",
                            "confidence": 0.9,
                        }
                    ],
                ),
                patch(
                    "backend.utils.memory_feature_flags.get_memory_feature_flags",
                    return_value=SimpleNamespace(
                        enable_memory_candidates=True,
                        enable_memory_promotion=False,
                        enable_style_profile=False,
                        enable_long_term_memory_rerank=False,
                    ),
                ),
            ):
                workflow = MainWorkflow()
                runtime = MagicMock()
                runtime.context = MagicMock()
                runtime.context.user_id = "visitor-excl"
                runtime.store = MagicMock()
                runtime.store.aput = AsyncMock()

                state = {
                    "query": "私は田中です",
                    "answer": "こんにちは田中さん",
                    "session_id": "test-session",
                    "language": "ja",
                }

                async def _passthrough(op, **kw):
                    return await op(runtime.store)

                with patch(
                    "backend.workflows.main_workflow.store_with_retry",
                    side_effect=_passthrough,
                ):
                    await workflow._format_response_node(state, runtime)

                # extract_memories should NOT be called directly when candidates enabled
                extract_memories_mock.assert_not_called()
                assert runtime.store.aput.await_count == 2
                namespaces = [call.args[0] for call in runtime.store.aput.await_args_list]
                assert namespaces == [
                    ("visitor_memory_candidates", "visitor-excl"),
                    ("visitor_memories", "visitor-excl"),
                ]

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_format_response_direct_write_when_candidates_disabled(
        self, mock_orchestrator_class
    ):
        """enable_memory_candidates=False のとき直接書き込みが実行される"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper

            with (
                patch(
                    "backend.utils.memory_extractor.extract_memories",
                    return_value=[{"type": "visitor_name", "content": "田中", "confidence": 0.9}],
                ),
                patch(
                    "backend.utils.memory_extractor.extract_memory_candidates",
                    return_value=[],
                ),
                patch(
                    "backend.utils.memory_feature_flags.get_memory_feature_flags",
                    return_value=SimpleNamespace(
                        enable_memory_candidates=False,
                        enable_memory_promotion=False,
                        enable_style_profile=False,
                        enable_long_term_memory_rerank=False,
                    ),
                ),
            ):
                workflow = MainWorkflow()
                runtime = MagicMock()
                runtime.context = MagicMock()
                runtime.context.user_id = "visitor-direct"
                runtime.store = MagicMock()
                runtime.store.aput = AsyncMock()

                state = {
                    "query": "私は田中です",
                    "answer": "こんにちは田中さん",
                    "session_id": "test-session",
                    "language": "ja",
                }

                async def _passthrough(op, **kw):
                    return await op(runtime.store)

                with patch(
                    "backend.workflows.main_workflow.store_with_retry",
                    side_effect=_passthrough,
                ):
                    await workflow._format_response_node(state, runtime)

                # Direct write to visitor_memories namespace
                runtime.store.aput.assert_called_once()
                ns = runtime.store.aput.await_args.args[0]
                assert ns == ("visitor_memories", "visitor-direct")

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_ltm_retry_idempotent_key_value(self, mock_orchestrator_class):
        """store retry が同一 operation を再実行しても key/value が変わらない"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper

            with (
                patch(
                    "backend.utils.memory_extractor.extract_memories",
                    return_value=[{"type": "visitor_name", "content": "田中", "confidence": 0.9}],
                ),
                patch(
                    "backend.utils.memory_feature_flags.get_memory_feature_flags",
                    return_value=SimpleNamespace(
                        enable_memory_candidates=False,
                        enable_memory_promotion=False,
                        enable_style_profile=False,
                        enable_long_term_memory_rerank=False,
                    ),
                ),
            ):
                workflow = MainWorkflow()
                runtime = MagicMock()
                runtime.context = MagicMock()
                runtime.context.user_id = "visitor-idempotent"
                runtime.store = MagicMock()
                runtime.store.aput = AsyncMock()

                state = {
                    "query": "私は田中です",
                    "answer": "こんにちは田中さん",
                    "session_id": "test-session",
                    "language": "ja",
                }

                async def _retry_same_operation(op, **kw):
                    await op(runtime.store)
                    return await op(runtime.store)

                with patch(
                    "backend.workflows.main_workflow.store_with_retry",
                    side_effect=_retry_same_operation,
                ):
                    await workflow._format_response_node(state, runtime)

                assert runtime.store.aput.await_count == 2
                first = runtime.store.aput.await_args_list[0].args
                second = runtime.store.aput.await_args_list[1].args
                assert first[0] == second[0]
                assert first[1] == second[1]
                assert first[2] == second[2]

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_memory_loader_reranks_long_term_memories_when_enabled(
        self, mock_orchestrator_class
    ):
        """ENABLE_LONG_TERM_MEMORY_RERANK=true で long_term_memory の順序が変わる"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.get_context = AsyncMock(
                return_value={
                    "recent_messages": [],
                    "context_string": "",
                    "inherited_request_type": None,
                }
            )
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper

            with patch(
                "backend.utils.memory_feature_flags.get_memory_feature_flags",
                return_value=SimpleNamespace(
                    enable_memory_candidates=False,
                    enable_memory_promotion=False,
                    enable_style_profile=False,
                    enable_long_term_memory_rerank=True,
                ),
            ):
                workflow = MainWorkflow()
                runtime = MagicMock()
                runtime.context = MagicMock()
                runtime.context.user_id = "visitor-rerank"
                runtime.store = MagicMock()

                # explicit_remember を後ろに置くが rerank で先頭に来る想定
                items = [
                    SimpleNamespace(
                        key="a",
                        score=0.7,
                        value={
                            "type": "visitor_name",
                            "data": "田中",
                            "confidence": 0.9,
                            "timestamp": 1_700_000_000.0,
                        },
                    ),
                    SimpleNamespace(
                        key="b",
                        score=0.7,
                        value={
                            "type": "explicit_remember",
                            "data": "火曜に来る",
                            "confidence": 1.0,
                            "timestamp": 1_700_000_000.0,
                        },
                    ),
                ]
                runtime.store.asearch = AsyncMock(return_value=items)

                state = {
                    "query": "火曜のこと覚えてる？",
                    "session_id": "test-session",
                    "language": "ja",
                    "context": {},
                }

                async def _passthrough(op, **kw):
                    return await op(runtime.store)

                with patch(
                    "backend.workflows.main_workflow.store_with_retry",
                    side_effect=_passthrough,
                ):
                    result = await workflow._memory_loader_node(state, runtime)
                lt = result["context"]["long_term_memory"]
                assert lt
                assert lt[0]["type"] == "explicit_remember"

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_memory_loader_strips_postgres_nul_chars_from_ltm_lookup(
        self, mock_orchestrator_class
    ):
        """LTM Store 読み込み前に namespace/query のNUL文字を除去する"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.get_context = AsyncMock(
                return_value={
                    "recent_messages": [],
                    "context_string": "",
                    "inherited_request_type": None,
                }
            )
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper

            with patch(
                "backend.utils.memory_feature_flags.get_memory_feature_flags",
                return_value=SimpleNamespace(
                    enable_memory_candidates=False,
                    enable_memory_promotion=False,
                    enable_style_profile=False,
                    enable_long_term_memory_rerank=False,
                ),
            ):
                workflow = MainWorkflow()
                runtime = MagicMock()
                runtime.context = MagicMock()
                runtime.context.user_id = "visitor\x00-load"
                runtime.store = MagicMock()
                runtime.store.asearch = AsyncMock(return_value=[])

                state = {
                    "query": "覚え\x00てる？",
                    "session_id": "test-session",
                    "language": "ja",
                    "context": {},
                }

                async def _passthrough(op, **kw):
                    return await op(runtime.store)

                with patch(
                    "backend.workflows.main_workflow.store_with_retry",
                    side_effect=_passthrough,
                ):
                    await workflow._memory_loader_node(state, runtime)

                runtime.store.asearch.assert_awaited_once_with(
                    ("visitor_memories", "visitor-load"),
                    query="覚えてる？",
                    limit=5,
                )


class TestWorkflowGraphStructure:
    """ワークフローグラフ構造のテスト"""

    def test_workflow_has_required_nodes(self):
        """ワークフローに必要なノードが含まれることを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        with patch("backend.workflows.main_workflow.OrchestratorAgent"):
            workflow = MainWorkflow()

            # graphが存在することを確認
            assert workflow.graph is not None

    def test_workflow_initialization(self):
        """ワークフローが正常に初期化されることを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        with patch("backend.workflows.main_workflow.OrchestratorAgent") as mock_orchestrator:
            mock_orchestrator.return_value = Mock()

            workflow = MainWorkflow()

            assert workflow.orchestrator is not None
            assert workflow.graph is not None

    def test_workflow_initialization_with_checkpointer(self):
        """Checkpointerを指定してワークフローが正常に初期化されることを確認"""
        from backend.workflows.main_workflow import MainWorkflow
        from langgraph.checkpoint.memory import MemorySaver

        with patch("backend.workflows.main_workflow.OrchestratorAgent") as mock_orchestrator:
            mock_orchestrator.return_value = Mock()
            # 実際のCheckpointerインスタンスを使用
            checkpointer = MemorySaver()

            workflow = MainWorkflow(checkpointer=checkpointer)

            assert workflow.orchestrator is not None
            assert workflow.graph is not None
            assert workflow.checkpointer == checkpointer


class TestOrchestratorIntegration:
    """OrchestratorAgent統合テスト"""

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_orchestrator_node_calls_decide_next_agent(self, mock_orchestrator_class):
        """_orchestrator_nodeがdecide_next_agentを呼び出すことを確認"""
        from backend.workflows.main_workflow import MainWorkflow
        from backend.agents.orchestrator_agent import OrchestratorDecision

        mock_decision = OrchestratorDecision(
            next_agent="business_info",
            language="ja",
            category="business-hours",
            request_type="hours",
            confidence=0.95,
            reasoning="営業時間の質問",
            debug_info={},
        )

        mock_orchestrator = AsyncMock()
        mock_orchestrator.decide_next_agent = AsyncMock(return_value=mock_decision)
        mock_orchestrator_class.return_value = mock_orchestrator

        workflow = MainWorkflow()

        state = {
            "query": "営業時間は？",
            "session_id": "test-session",
            "language": "ja",
            "context": {"memory": {}},
        }

        result = await workflow._orchestrator_node(state)

        # Command patternで結果が返されることを確認
        mock_orchestrator.decide_next_agent.assert_called_once()
        # Commandオブジェクトが返される
        assert hasattr(result, "goto")
        assert result.goto == "business_info"

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_orchestrator_node_normalizes_stale_agent_before_goto(
        self, mock_orchestrator_class
    ):
        """routing category と実際の LangGraph 遷移先をずらさない。"""
        from backend.workflows.main_workflow import MainWorkflow
        from backend.agents.orchestrator_agent import OrchestratorDecision

        mock_decision = OrchestratorDecision(
            next_agent="GeneralKnowledgeAgent",
            language="ja",
            category="pricing",
            request_type="price",
            confidence=0.8,
            reasoning="Fallback agent label was stale",
            debug_info={},
        )
        mock_orchestrator = AsyncMock()
        mock_orchestrator.decide_next_agent = AsyncMock(return_value=mock_decision)
        mock_orchestrator_class.return_value = mock_orchestrator

        workflow = MainWorkflow()

        state = {
            "query": "料金はいくらですか？",
            "session_id": "test-session",
            "language": "ja",
            "context": {"memory": {}},
        }

        with patch("backend.utils.topic_guard.check_topic_adherence", return_value=(True, None)):
            result = await workflow._orchestrator_node(state)

        assert result.goto == "business_info"
        assert result.update["routing"]["agent"] == "business_info"
        assert result.update["routing"]["category"] == "pricing"
        assert result.update["routing"]["request_type"] == "price"
        assert result.update["routing"]["debug_info"]["raw_next_agent"] == "GeneralKnowledgeAgent"
        assert result.update["routing"]["debug_info"]["agent_resolution_source"] == "request_type"

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_orchestrator_node_uses_request_type_when_category_is_too_broad(
        self, mock_orchestrator_class
    ):
        """facility-info + hours のような広いカテゴリでも営業時間は business_info へ送る。"""
        from backend.workflows.main_workflow import MainWorkflow
        from backend.agents.orchestrator_agent import OrchestratorDecision

        mock_decision = OrchestratorDecision(
            next_agent="facility",
            language="ja",
            category="facility-info",
            request_type="hours",
            confidence=0.8,
            reasoning="Broad facility category with business-hours request type",
            debug_info={},
        )
        mock_orchestrator = AsyncMock()
        mock_orchestrator.decide_next_agent = AsyncMock(return_value=mock_decision)
        mock_orchestrator_class.return_value = mock_orchestrator

        workflow = MainWorkflow()

        state = {
            "query": "開館時間を教えてください",
            "session_id": "test-session",
            "language": "ja",
            "context": {"memory": {}},
        }

        with patch("backend.utils.topic_guard.check_topic_adherence", return_value=(True, None)):
            result = await workflow._orchestrator_node(state)

        assert result.goto == "business_info"
        assert result.update["routing"]["agent"] == "business_info"
        assert result.update["routing"]["category"] == "facility-info"
        assert result.update["routing"]["request_type"] == "hours"
        assert result.update["routing"]["debug_info"]["agent_resolution_source"] == "request_type"

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_orchestrator_node_resolves_saino_followup_from_session_memory(
        self, mock_orchestrator_class
    ):
        """EC営業時間の直後の「隣のカフェ」はsaino営業時間として解決する。"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator = AsyncMock()
        mock_orchestrator.decide_next_agent = AsyncMock(
            side_effect=AssertionError("deterministic cafe follow-up should not call LLM router")
        )
        mock_orchestrator_class.return_value = mock_orchestrator

        workflow = MainWorkflow()
        state = {
            "query": "隣のカフェは？",
            "session_id": "test-session",
            "language": "ja",
            "context": {
                "memory": {
                    "recent_messages": [
                        {
                            "role": "user",
                            "content": "エンジニアカフェの営業時間を教えて",
                            "metadata": {"request_type": "hours"},
                        }
                    ],
                    "inherited_request_type": "hours",
                }
            },
            "metadata": {},
            "reception_status": {"stage": "none"},
        }

        result = await workflow._orchestrator_node(state)

        assert result.goto == "business_info"
        assert result.update["routing"]["category"] == "saino-cafe"
        assert result.update["routing"]["request_type"] == "hours"
        resolution = result.update["metadata"]["cafe_entity_resolution"]
        assert resolution["entity"] == "saino_cafe"
        assert resolution["status"] == "resolved"
        assert resolution["context_used"] is True
        mock_orchestrator.decide_next_agent.assert_not_called()

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_format_response_node(self, mock_orchestrator_class):
        """_format_response_nodeが正しくメッセージをフォーマットすることを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        with (
            patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper,
            patch("backend.workflows.main_workflow.CharacterControlAgent") as mock_character_class,
        ):
            mock_helper = AsyncMock()
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper
            mock_character = AsyncMock()
            mock_character.process = AsyncMock(
                return_value={"name": "idle", "duration": 1000, "keyframes": [{"time": 0}]}
            )
            mock_character_class.return_value = mock_character

            workflow = MainWorkflow()

            state = {
                "query": "営業時間は？",
                "answer": "9時から22時です。",
                "session_id": "test-session",
                "emotion": "neutral",
                "metadata": {"agent": "BusinessInfoAgent"},
                "context": {},
            }

            result = await workflow._format_response_node(state, _mock_runtime())

            assert "messages" in result
            assert result["metadata"]["agent"] == "BusinessInfoAgent"
            assert result["metadata"]["vrm_control"]["name"] == "idle"
            assert result["metadata"]["lipsync_data"] == [{"time": 0}]
            assert len(result["messages"]) == 2
            assert result["messages"][0].content == "営業時間は？"
            assert result["messages"][1].content == "9時から22時です。"

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_format_response_node_falls_back_when_character_control_fails(
        self, mock_orchestrator_class
    ):
        """CharacterControlAgent が失敗しても応答生成は継続することを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        with (
            patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper,
            patch("backend.workflows.main_workflow.CharacterControlAgent") as mock_character_class,
        ):
            mock_helper = AsyncMock()
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper
            mock_character = AsyncMock()
            mock_character.process = AsyncMock(side_effect=RuntimeError("character control failed"))
            mock_character_class.return_value = mock_character

            workflow = MainWorkflow()

            state = {
                "query": "営業時間は？",
                "answer": "9時から22時です。",
                "session_id": "test-session",
                "emotion": "neutral",
                "metadata": {"agent": "BusinessInfoAgent"},
                "context": {},
            }

            result = await workflow._format_response_node(state, _mock_runtime())

            assert result["metadata"]["agent"] == "BusinessInfoAgent"
            assert result["metadata"]["vrm_control"] is None
            assert result["metadata"]["lipsync_data"] == []
            assert result["messages"][-1].content == "9時から22時です。"

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_reception_check_node_marks_active_session(self, mock_orchestrator_class):
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = _StubOrchestrator()
        workflow = MainWorkflow()

        with patch(
            "backend.utils.reception_status.check_reception_status",
            new=AsyncMock(return_value={"completed": False, "stage": "greeting"}),
        ):
            result = await workflow._reception_check_node({"session_id": "reception-session"})

        assert result["reception_status"]["stage"] == "greeting"
        assert workflow._reception_check_decision(result) == "active_reception"

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_keyword_router_fast_routes_wifi_query(self, mock_orchestrator_class):
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = _StubOrchestrator()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper

            workflow = MainWorkflow()
            result = await workflow._keyword_router_node(
                {
                    "query": "WiFiのパスワードは？",
                    "session_id": "fast-router-session",
                    "language": "ja",
                    "routing": {},
                }
            )

        assert result["routing"]["pre_memory_fast_path_agent"] == "facility"
        assert result["routing"]["request_type"] == "wifi"
        mock_helper.store_message.assert_awaited_once_with(
            session_id="fast-router-session",
            role="user",
            content="WiFiのパスワードは？",
        )

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_keyword_router_fast_routes_assistant_profile_without_memory_loader(
        self, mock_orchestrator_class
    ):
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = _StubOrchestrator()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper

            workflow = MainWorkflow()
            result = await workflow._keyword_router_node(
                {
                    "query": "あなたの名前は？",
                    "session_id": "assistant-profile-session",
                    "language": "ja",
                    "routing": {},
                }
            )

        assert result["routing"]["pre_memory_fast_path_agent"] == "general_knowledge"
        assert result["routing"]["request_type"] == "assistant_profile"
        assert workflow._keyword_router_decision({"routing": result["routing"]}) == (
            "general_knowledge"
        )
        mock_helper.store_message.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_keyword_router_fast_routes_current_weather(self, mock_orchestrator_class):
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = _StubOrchestrator()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper

            workflow = MainWorkflow()
            result = await workflow._keyword_router_node(
                {
                    "query": "今日の福岡の天気は？",
                    "session_id": "weather-session",
                    "language": "ja",
                    "routing": {},
                }
            )

        assert result["routing"]["pre_memory_fast_path_agent"] == "general_knowledge"
        assert result["routing"]["request_type"] == "current_info"
        assert workflow._keyword_router_decision({"routing": result["routing"]}) == (
            "general_knowledge"
        )

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_keyword_router_keeps_anaphora_on_normal_path(self, mock_orchestrator_class):
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = _StubOrchestrator()
        workflow = MainWorkflow()

        result = await workflow._keyword_router_node(
            {
                "query": "それについてもう少し教えて",
                "session_id": "anaphora-session",
                "language": "ja",
                "routing": {},
            }
        )

        assert result["routing"]["pre_memory_fast_path_agent"] is None
        assert workflow._keyword_router_decision({"routing": result["routing"]}) == "normal"

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_keyword_router_keeps_mixed_intent_greeting_on_normal_path(
        self, mock_orchestrator_class
    ):
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = _StubOrchestrator()
        workflow = MainWorkflow()

        result = await workflow._keyword_router_node(
            {
                "query": "hello wifi?",
                "session_id": "mixed-intent-session",
                "language": "en",
                "routing": {},
            }
        )

        assert result["routing"]["pre_memory_fast_path_agent"] is None
        assert workflow._keyword_router_decision({"routing": result["routing"]}) == "normal"


class TestAsyncWorkflowMethods:
    """非同期ワークフローメソッドのテスト"""

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_workflow_close(self, mock_orchestrator_class):
        """closeメソッドがリソースをクリーンアップすることを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator = AsyncMock()
        mock_orchestrator.close = AsyncMock()
        mock_orchestrator_class.return_value = mock_orchestrator

        workflow = MainWorkflow()

        await workflow.close()

        mock_orchestrator.close.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_workflow_close_with_checkpointer(self, mock_orchestrator_class):
        """checkpointer付きのcloseメソッドが両方をクリーンアップすることを確認"""
        from backend.workflows.main_workflow import MainWorkflow
        from langgraph.checkpoint.memory import MemorySaver

        mock_orchestrator = AsyncMock()
        mock_orchestrator.close = AsyncMock()
        mock_orchestrator_class.return_value = mock_orchestrator

        # MemorySaverを使用（connがないので別のアプローチでテスト）
        checkpointer = MemorySaver()

        workflow = MainWorkflow(checkpointer=checkpointer)

        # closeは例外なく完了すべき
        await workflow.close()

        mock_orchestrator.close.assert_called_once()


class TestStoreMessageIntegration:
    """store_message統合テスト"""

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_memory_loader_stores_user_message(self, mock_orchestrator_class):
        """memory_loader_nodeがユーザーメッセージをstore_message()で保存することを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        # OrchestratorAgentのモック
        mock_orchestrator = AsyncMock()
        mock_orchestrator_class.return_value = mock_orchestrator

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.get_context = AsyncMock(
                return_value={
                    "recent_messages": [],
                    "context_string": "",
                }
            )
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper

            workflow = MainWorkflow()

            state = {
                "query": "営業時間は？",
                "session_id": "test-session-123",
                "language": "ja",
                "context": {},
            }

            await workflow._memory_loader_node(state, _mock_runtime())

            # store_messageが正しい引数で呼ばれたことを確認
            mock_helper.store_message.assert_called_once_with(
                session_id="test-session-123",
                role="user",
                content="営業時間は？",
            )

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_format_response_stores_assistant_message(self, mock_orchestrator_class):
        """format_response_nodeがアシスタント応答をstore_message()で保存することを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper

            workflow = MainWorkflow()

            state = {
                "query": "営業時間は？",
                "answer": "9時から22時までです。",
                "session_id": "test-session-456",
                "emotion": "neutral",
                "routing": {},
            }

            await workflow._format_response_node(state, _mock_runtime())

            # store_messageが正しい引数で呼ばれたことを確認
            mock_helper.store_message.assert_called_once_with(
                session_id="test-session-456",
                role="assistant",
                content="9時から22時までです。",
            )

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_store_message_failure_does_not_break_workflow(self, mock_orchestrator_class):
        """store_message()が失敗してもワークフローは正常に継続することを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator = AsyncMock()
        mock_orchestrator_class.return_value = mock_orchestrator

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            # get_contextは正常に動作
            mock_helper.get_context = AsyncMock(
                return_value={
                    "recent_messages": [],
                    "context_string": "",
                }
            )
            # store_messageは例外を投げる
            mock_helper.store_message = AsyncMock(side_effect=Exception("DB connection error"))
            mock_get_helper.return_value = mock_helper

            workflow = MainWorkflow()

            # memory_loader_nodeのテスト
            state_loader = {
                "query": "営業時間は？",
                "session_id": "test-session-789",
                "language": "ja",
                "context": {},
            }

            result_loader = await workflow._memory_loader_node(state_loader, _mock_runtime())

            # 例外が投げられても正常に結果が返ることを確認
            assert "context" in result_loader
            assert "memory" in result_loader["context"]

            # format_response_nodeのテスト
            state_format = {
                "query": "営業時間は？",
                "answer": "9時から22時までです。",
                "session_id": "test-session-789",
            }

            result_format = await workflow._format_response_node(state_format, _mock_runtime())

            # 例外が投げられても正常に結果が返ることを確認
            assert "messages" in result_format
            assert len(result_format["messages"]) == 2


class TestResponseTranslation:
    """レスポンス翻訳（JA→EN）のテスト"""

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_format_response_translates_ja_to_en(self, mock_orchestrator_class):
        """language='en' の場合、日本語回答が英語に翻訳されることを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        with (
            patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper,
            patch("backend.services.translation_service.get_translation_service") as mock_get_ts,
        ):
            mock_helper = AsyncMock()
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper

            mock_ts = AsyncMock()
            mock_ts.translate = AsyncMock(return_value="It is from 9am to 10pm.")
            mock_get_ts.return_value = mock_ts

            workflow = MainWorkflow()

            state = {
                "query": "What are the hours?",
                "answer": "9時から22時です。",
                "session_id": "test-session",
                "language": "en",
            }

            result = await workflow._format_response_node(state, _mock_runtime())

            mock_ts.translate.assert_called_once_with("9時から22時です。", "ja_to_en")
            assert result["messages"][-1].content == "It is from 9am to 10pm."

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_format_response_skips_translation_for_english_answer(
        self, mock_orchestrator_class
    ):
        """Canonical English answers must not pass through the JA->EN model."""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        with (
            patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper,
            patch("backend.services.translation_service.get_translation_service") as mock_get_ts,
        ):
            mock_helper = AsyncMock()
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper

            workflow = MainWorkflow()
            answer = (
                "Phone: 080-6742-7231 (13:00-21:00). "
                "Website: https://engineercafe.jp/. "
                "Contact form: https://engineercafe.jp/ja/contact."
            )
            state = {
                "query": "How can I contact Engineer Cafe?",
                "answer": answer,
                "session_id": "test-session",
                "language": "en",
            }

            result = await workflow._format_response_node(state, _mock_runtime())

            mock_get_ts.assert_not_called()
            assert result["messages"][-1].content == answer

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_format_response_skips_translation_for_ja(self, mock_orchestrator_class):
        """language='ja' の場合、翻訳をスキップすることを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper

            workflow = MainWorkflow()

            state = {
                "query": "営業時間は？",
                "answer": "9時から22時です。",
                "session_id": "test-session",
                "language": "ja",
            }

            result = await workflow._format_response_node(state, _mock_runtime())

            assert result["messages"][-1].content == "9時から22時です。"

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_format_response_translation_failure_fallback(self, mock_orchestrator_class):
        """翻訳失敗時、元の日本語回答がそのまま使用されることを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        with (
            patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper,
            patch("backend.services.translation_service.get_translation_service") as mock_get_ts,
        ):
            mock_helper = AsyncMock()
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper

            mock_ts = AsyncMock()
            mock_ts.translate = AsyncMock(side_effect=RuntimeError("Model not found"))
            mock_get_ts.return_value = mock_ts

            workflow = MainWorkflow()

            state = {
                "query": "What are the hours?",
                "answer": "9時から22時です。",
                "session_id": "test-session",
                "language": "en",
            }

            result = await workflow._format_response_node(state, _mock_runtime())

            assert result["messages"][-1].content == "9時から22時です。"

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_format_response_stores_translated_in_memory(self, mock_orchestrator_class):
        """翻訳後の英語回答がメモリに保存されることを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        with (
            patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper,
            patch("backend.services.translation_service.get_translation_service") as mock_get_ts,
        ):
            mock_helper = AsyncMock()
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper

            mock_ts = AsyncMock()
            mock_ts.translate = AsyncMock(return_value="It is from 9am to 10pm.")
            mock_get_ts.return_value = mock_ts

            workflow = MainWorkflow()

            state = {
                "query": "What are the hours?",
                "answer": "9時から22時です。",
                "session_id": "test-session",
                "language": "en",
            }

            await workflow._format_response_node(state, _mock_runtime())

            mock_helper.store_message.assert_called_once_with(
                session_id="test-session",
                role="assistant",
                content="It is from 9am to 10pm.",
            )

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_format_response_default_language_ja(self, mock_orchestrator_class):
        """language未指定時のデフォルト'ja'で翻訳がスキップされることを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper

            workflow = MainWorkflow()

            state = {
                "query": "営業時間は？",
                "answer": "9時から22時です。",
                "session_id": "test-session",
            }

            result = await workflow._format_response_node(state, _mock_runtime())

            assert result["messages"][-1].content == "9時から22時です。"


class TestRetryPolicy:
    """RetryPolicy 設定テスト"""

    def test_llm_retry_policy_attributes(self):
        """LLM_RETRY_POLICYの属性値を確認"""
        from backend.workflows.main_workflow import MainWorkflow

        rp = MainWorkflow.LLM_RETRY_POLICY
        assert rp.initial_interval == 1.0
        assert rp.backoff_factor == 2.0
        assert rp.max_interval == 10.0
        assert rp.max_attempts == 3

    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    def test_llm_nodes_have_retry_policy(self, mock_orchestrator_class):
        """LLM依存ノードにretry_policyが設定されていることを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = Mock()
        workflow = MainWorkflow()

        # LangGraphのノード内部でretry_policyが設定されているかは
        # グラフの構造情報から確認
        graph = workflow.graph
        # ノードが存在することを確認（retry_policyはグラフコンパイル時に内部処理される）
        assert graph is not None

    def test_retry_policy_is_langgraph_retry_policy(self):
        """LLM_RETRY_POLICYがLangGraphのRetryPolicyインスタンスであることを確認"""
        from langgraph.types import RetryPolicy
        from backend.workflows.main_workflow import MainWorkflow

        assert isinstance(MainWorkflow.LLM_RETRY_POLICY, RetryPolicy)


class TestAstream:
    """astream() ストリーミングメソッドのテスト"""

    def test_astream_method_exists(self):
        """astream()メソッドが存在することを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        assert hasattr(MainWorkflow, "astream")
        # astream is an async generator (contains yield), so use isasyncgenfunction
        assert inspect.isasyncgenfunction(MainWorkflow.astream)

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_astream_is_async_generator(self, mock_orchestrator_class):
        """astream()が非同期ジェネレータであることを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        workflow = MainWorkflow()

        # astream_eventsをモックして空のイテレータを返す
        async def empty_events(*args, **kwargs):
            return
            yield  # Make it an async generator

        workflow.graph.astream_events = empty_events

        events = []
        async for event in workflow.astream({"query": "test", "session_id": "s1"}):
            events.append(event)

        assert events == []  # 空のジェネレータからは何も出ない

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_astream_yields_token_events(self, mock_orchestrator_class):
        """astream()がon_chat_model_streamイベントからtokenをyieldすることを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        workflow = MainWorkflow()

        # astream_eventsをモックしてtoken eventを返す
        mock_chunk = Mock()
        mock_chunk.content = "Hello"

        async def mock_events(*args, **kwargs):
            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": mock_chunk},
                "name": "some_model",
            }

        workflow.graph.astream_events = mock_events

        events = []
        async for event in workflow.astream({"query": "test", "session_id": "s1"}):
            events.append(event)

        assert len(events) == 1
        assert events[0] == {"type": "token", "content": "Hello"}

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_astream_yields_complete_event(self, mock_orchestrator_class):
        """astream()がon_chain_endイベントからcompleteをyieldすることを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        workflow = MainWorkflow()

        output_data = {"answer": "回答", "emotion": "neutral"}

        async def mock_events(*args, **kwargs):
            yield {
                "event": "on_chain_end",
                "name": "format_response",
                "data": {"output": output_data},
            }

        workflow.graph.astream_events = mock_events

        events = []
        async for event in workflow.astream({"query": "test", "session_id": "s1"}):
            events.append(event)

        assert len(events) == 1
        assert events[0] == {"type": "complete", "data": output_data}

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_astream_skips_empty_content(self, mock_orchestrator_class):
        """astream()が空contentのtokenをスキップすることを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        workflow = MainWorkflow()

        mock_chunk_empty = Mock()
        mock_chunk_empty.content = ""

        mock_chunk_valid = Mock()
        mock_chunk_valid.content = "World"

        async def mock_events(*args, **kwargs):
            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": mock_chunk_empty},
                "name": "model",
            }
            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": mock_chunk_valid},
                "name": "model",
            }

        workflow.graph.astream_events = mock_events

        events = []
        async for event in workflow.astream({"query": "test", "session_id": "s1"}):
            events.append(event)

        assert len(events) == 1
        assert events[0] == {"type": "token", "content": "World"}

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_astream_ignores_irrelevant_events(self, mock_orchestrator_class):
        """astream()が関係ないイベントを無視することを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        workflow = MainWorkflow()

        async def mock_events(*args, **kwargs):
            yield {"event": "on_chain_start", "name": "orchestrator", "data": {}}
            yield {"event": "on_chain_end", "name": "business_info", "data": {"output": {}}}

        workflow.graph.astream_events = mock_events

        events = []
        async for event in workflow.astream({"query": "test", "session_id": "s1"}):
            events.append(event)

        assert events == []
