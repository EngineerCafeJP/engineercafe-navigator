"""Response formatting, invocation, and cleanup helpers for MainWorkflow."""

from __future__ import annotations

import asyncio
import base64
import logging
import time
import uuid
from typing import Any

import cv2
import numpy as np
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.runtime import Runtime

from backend.services.memory_promoter import MemoryPromoter
from backend.utils.postgres_sanitizer import sanitize_for_postgres
from backend.workflows.main.evidence import (
    _build_agent_response_evidence_metadata,
    _build_rag_evidence_metadata,
    _detect_hallucination_flag,
    _merge_rag_evidence_metadata,
)
from backend.workflows.main.types import WorkflowContext, WorkflowStateDict

logger = logging.getLogger(__name__)


def _public():
    from backend.workflows import main_workflow

    return main_workflow


class ResponseWorkflowMixin:
    async def _format_response_node(
        self, state: WorkflowStateDict, runtime: Runtime[WorkflowContext]
    ) -> dict:
        """応答フォーマットノード: 最終的な応答をフォーマット"""
        from backend.utils.emotion_utils import strip_emotion_tags
        from backend.utils.memory_helper import get_memory_helper
        from backend.utils.message_windowing import apply_message_window
        from backend.utils.pii_scanner import scan_and_mask

        query = state.get("query", "")
        raw_answer = state.get("answer", "回答を生成できませんでした。")
        answer = strip_emotion_tags(raw_answer)
        session_id = state.get("session_id", "")
        state_metadata = state.get("metadata", {})
        state_context = state.get("context", {})
        if not isinstance(state_context, dict):
            state_context = {}

        vrm_control = None
        lipsync_data: list[dict[str, Any]] = []
        if self._character_control_agent is not None:
            try:
                audio_duration = state_context.get("audio_duration") or state_context.get(
                    "audioDuration"
                )
                vrm_control = await self._character_control_agent.process(
                    state.get("emotion") or "neutral",
                    raw_answer,
                    audio_duration=audio_duration,
                    context=state_context,
                )
                lipsync_data = vrm_control.get("keyframes", [])
            except Exception as character_error:
                logger.warning(
                    "Character control generation failed, continuing without VRM metadata: %s",
                    character_error,
                    exc_info=True,
                )

        metadata = {
            **state_metadata,
            "vrm_control": vrm_control,
            "lipsync_data": lipsync_data,
        }
        metadata.setdefault("ltm_store_write", "skipped")

        def _mark_ltm_store_write(status: str) -> None:
            if status == "success" or metadata.get("ltm_store_write") != "success":
                metadata["ltm_store_write"] = status

        if "rag_evidence" not in metadata:
            rag_evidence = _build_rag_evidence_metadata(state_context)
            if rag_evidence is not None:
                metadata["rag_evidence"] = rag_evidence

        # PII Defense-in-Depth: ワークフロー層でもスキャン（API層に加えて二重防御）
        try:
            masked, pii_items = scan_and_mask(answer)
            if pii_items:
                logger.warning(
                    "PII detected in workflow output (%d items), masking",
                    len(pii_items),
                )
                answer = masked
        except Exception:
            pass  # Non-critical — API層でもスキャンするため

        agent_response_evidence = _build_agent_response_evidence_metadata(
            state_context,
            metadata,
            answer,
        )
        merged_rag_evidence = _merge_rag_evidence_metadata(
            metadata.get("rag_evidence"),
            agent_response_evidence,
        )
        if merged_rag_evidence is not None:
            metadata["rag_evidence"] = merged_rag_evidence

        # Response translation: translate JA response to EN for English users
        # zh/ko: rely on LLM's native multilingual output (LANGUAGE_INSTRUCTION)
        # CTranslate2 only supports en<->ja, so no translation for zh/ko
        language = state.get("language", "ja")
        if language == "en" and self._should_translate_answer_to_english(answer):
            try:
                from backend.services.translation_service import (
                    get_translation_service,
                )

                ts = get_translation_service()
                translated_answer = await ts.translate(answer, "ja_to_en")
                if translated_answer != answer:
                    logger.info(
                        "Translated response for lang=%s: '%s' -> '%s'",
                        language,
                        answer[:40],
                        translated_answer[:40],
                    )
                answer = translated_answer
            except Exception as trans_err:
                logger.warning(
                    "Response translation failed, using original: %s",
                    trans_err,
                )

        metadata["hallucination_flag"] = _detect_hallucination_flag(answer, metadata)

        # アシスタント応答を保存
        try:
            memory_helper = get_memory_helper()
            await memory_helper.store_message(
                session_id=session_id,
                role="assistant",
                content=answer,
            )
        except Exception as store_error:
            logger.warning("Failed to store assistant message: %s", store_error)

        # NEW: Extract and store long-term memories
        try:
            user_id = runtime.context.user_id if runtime.context else None
            if user_id and user_id != "anonymous" and runtime.store:
                from backend.utils.memory_extractor import (
                    extract_memories,
                    extract_memory_candidates,
                )
                from backend.utils.memory_feature_flags import get_memory_feature_flags

                memory_flags = get_memory_feature_flags()
                safe_user_id = sanitize_for_postgres(user_id)
                long_term_namespace = ("visitor_memories", safe_user_id)
                candidate_namespace = ("visitor_memory_candidates", safe_user_id)

                def _is_fast_path_memory(memory: dict[str, Any]) -> bool:
                    memory_type = memory.get("candidate_type") or memory.get("type")
                    confidence = float(memory.get("confidence", 0.0) or 0.0)
                    content = str(memory.get("content", "")).strip()
                    evidence = memory.get("evidence", {})
                    evidence_query = ""
                    if isinstance(evidence, dict):
                        evidence_query = str(evidence.get("query", ""))
                    explicit_text = f"{content} {evidence_query} {query}".lower()
                    explicit_keywords = (
                        "覚えて",
                        "記憶して",
                        "忘れないで",
                        "remember",
                        "don't forget",
                        "keep in mind",
                    )

                    # Gate fast-path with the same actionable-content rule as
                    # MemoryPromoter so that empty / filler strings (e.g. "please",
                    # "ください", single characters) never reach LTM.
                    if not MemoryPromoter._has_actionable_content(memory):
                        return False

                    if memory_type == "explicit_remember":
                        return confidence >= 0.5
                    if any(keyword in explicit_text for keyword in explicit_keywords):
                        return confidence >= 0.8
                    return memory_type == "visitor_name" and confidence >= 0.9

                async def _write_long_term_memory(memory: dict[str, Any], source: str) -> None:
                    key = str(uuid.uuid4())
                    value = {
                        "data": memory.get("content", ""),
                        "type": memory.get("candidate_type") or memory.get("type", "unknown"),
                        "confidence": memory.get("confidence", 0.5),
                        "timestamp": time.time(),
                        "source": source,
                    }
                    value = sanitize_for_postgres(value)
                    try:
                        await _public().store_with_retry(
                            lambda s, k=key, v=value: s.aput(long_term_namespace, k, v),
                            store=runtime.store,
                            operation_name="long-term memory store",
                        )
                    except Exception:
                        _mark_ltm_store_write("failed")
                        raise
                    _mark_ltm_store_write("success")

                # Candidate system writes shadow candidates, while high-confidence
                # explicit facts also enter LTM immediately for cross-session recall.
                # When disabled, use legacy direct writes for backward compat.
                if memory_flags.enable_memory_candidates:
                    try:
                        candidates = extract_memory_candidates(
                            query=query,
                            answer=answer,
                            language=state.get("language", "ja"),
                        )
                        if candidates:
                            fast_path_count = 0
                            for candidate in candidates:
                                candidate_key = str(uuid.uuid4())
                                candidate_value = sanitize_for_postgres(dict(candidate))
                                await _public().store_with_retry(
                                    lambda s, k=candidate_key, v=candidate_value: s.aput(
                                        candidate_namespace,
                                        k,
                                        v,
                                    ),
                                    store=runtime.store,
                                    operation_name="long-term memory store",
                                )
                                if _is_fast_path_memory(candidate_value):
                                    await _write_long_term_memory(
                                        candidate_value,
                                        "candidate_fast_path",
                                    )
                                    fast_path_count += 1
                            logger.info(
                                "Stored %d memory candidates for user %s",
                                len(candidates),
                                user_id,
                            )
                            if fast_path_count:
                                logger.info(
                                    "Fast-path stored %d long-term memories for user %s",
                                    fast_path_count,
                                    user_id,
                                )
                    except Exception as candidate_err:
                        _mark_ltm_store_write("failed")
                        logger.warning(
                            "Memory candidate write failed: %s",
                            candidate_err,
                        )
                else:
                    facts = extract_memories(query, answer, state.get("language", "ja"))
                    if facts:
                        for fact in facts:
                            await _write_long_term_memory(fact, "legacy_direct")
                        logger.info(
                            "Stored %d long-term memories for user %s",
                            len(facts),
                            user_id,
                        )

                # Promote candidates to long-term memory (best effort).
                if memory_flags.enable_memory_promotion:
                    try:
                        from backend.services.memory_promoter import (
                            get_memory_promoter,
                        )

                        promoter = get_memory_promoter()
                        promotion_stats = await promoter.promote_for_user(
                            runtime.store,
                            safe_user_id,
                            delete_promoted_candidates=False,
                        )
                        if promotion_stats.get("promoted", 0) > 0:
                            _mark_ltm_store_write("success")
                        if promotion_stats.get("promoted", 0) > 0:
                            logger.info(
                                "Promoted memories for user %s: %s",
                                user_id,
                                promotion_stats,
                            )
                    except Exception as promote_err:
                        _mark_ltm_store_write("failed")
                        logger.warning("Memory promotion failed: %s", promote_err)
        except Exception as e:
            _mark_ltm_store_write("failed")
            logger.warning("Long-term memory store failed: %s", e)

        # Message Windowing: 長セッションでのコンテキストオーバーフロー防止
        existing_msgs = state.get("messages", [])
        windowed = apply_message_window(existing_msgs)

        # 時間帯情報と閉館警告をmetadataに追加
        try:
            from backend.config.routing_constants import CLOSING_WARNING_TEMPLATES
            from backend.utils.time_utils import (
                get_current_time_period,
                get_minutes_until_closing,
                get_now_jst,
                get_today_business_hours,
                is_closing_soon,
            )

            now = get_now_jst()
            time_period = get_current_time_period(now.hour)
            metadata["time_period"] = time_period

            business_hours = get_today_business_hours(now.weekday())
            closing_warning: dict[str, object] = {"is_closing_soon": False}

            if business_hours is not None:
                _, close_time = business_hours
                closing_hour = close_time.hour
                closing_minute = close_time.minute

                if is_closing_soon(now, closing_hour, closing_minute):
                    remaining = get_minutes_until_closing(now, closing_hour, closing_minute)
                    closing_warning = {
                        "is_closing_soon": True,
                        "minutes_remaining": remaining,
                    }
                    # 応答に閉館警告を付加
                    template = CLOSING_WARNING_TEMPLATES.get(
                        language, CLOSING_WARNING_TEMPLATES["ja"]
                    )
                    warning_text = template.format(minutes=remaining)
                    answer = f"{answer}\n\n{warning_text}"

            metadata["closing_warning"] = closing_warning
        except Exception as time_err:
            logger.warning("Time period/closing warning processing failed: %s", time_err)

        return {
            "answer": answer,
            "metadata": metadata,
            "messages": windowed
            + [
                HumanMessage(content=query),
                AIMessage(content=answer),
            ],
        }

    @staticmethod
    def _should_translate_answer_to_english(answer: str) -> bool:
        """Return true only when an English turn still has Japanese text."""
        if not answer:
            return False
        return any(
            ("\u3040" <= char <= "\u30ff") or ("\u4e00" <= char <= "\u9fff") for char in answer
        )

    def _decode_image_data(self, image_data: Any) -> Any:
        """Convert base64 image string to np.ndarray for VisionAgent.

        Other types pass through unchanged.
        """
        if not isinstance(image_data, str):
            return image_data
        try:
            raw = base64.b64decode(image_data)
            arr = np.frombuffer(raw, dtype=np.uint8)
            decoded = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            return decoded if decoded is not None else image_data
        except Exception:
            return image_data

    def _prepare_state(self, input_data: dict) -> tuple[WorkflowStateDict, dict | None]:
        """ainvoke/astream共通: 入力データからstate + configを構築"""
        session_id = input_data.get("session_id", "default")
        raw_image = input_data.get("image_data")
        state: WorkflowStateDict = {
            "messages": [],
            "query": input_data.get("query", ""),
            "session_id": session_id,
            "language": input_data.get("language", "ja"),
            "routing": {},
            "answer": None,
            "emotion": None,
            "metadata": {},
            "context": input_data.get("context", {}),
            "reception_status": {},
            "image_data": self._decode_image_data(raw_image) if raw_image is not None else None,
            "ocr_result": None,
        }
        config = None
        if self.checkpointer:
            config = {"configurable": {"thread_id": session_id}}

        # Store visitor_id for context injection
        self._current_visitor_id = input_data.get("visitor_id") or session_id

        return state, config

    async def _ensure_checkpointer_ready(self, config: dict | None, session_id: str) -> None:
        """Cold-start後の切断済み接続を graph 実行前に一度だけ張り直す。"""
        if not self.checkpointer or not config:
            return

        aget_tuple = getattr(self.checkpointer, "aget_tuple", None)
        if not callable(aget_tuple):
            return

        await aget_tuple(config)

    async def ainvoke(self, input_data: dict) -> dict:
        """ワークフローを非同期実行"""
        state, config = self._prepare_state(input_data)
        await self._ensure_checkpointer_ready(config, state["session_id"])
        visitor_id = input_data.get("visitor_id") or input_data.get("session_id", "anonymous")
        context = WorkflowContext(user_id=visitor_id)

        try:
            result = await asyncio.wait_for(
                self.graph.ainvoke(state, config=config, context=context),
                timeout=30,
            )
        except asyncio.TimeoutError:
            logger.error(
                "Workflow timed out after 30s for session %s",
                state["session_id"],
            )
            return {
                "answer": "申し訳ございません。処理がタイムアウトしました。",
                "emotion": "neutral",
                "metadata": {"error": "Request timed out after 30 seconds"},
            }

        return {
            "answer": result.get("answer", ""),
            "emotion": result.get("emotion", "neutral"),
            "metadata": result.get("metadata", {}),
        }

    async def astream(self, input_data: dict):
        """
        ストリーミング実行 - astream_events() によるイベント発行

        将来のフロントエンド SSE 対応のための基盤。
        LLMノードの中間トークンと最終結果をyieldする。

        Args:
            input_data: ainvoke() と同じ入力データ

        Yields:
            dict: {"type": "token", "content": str} or {"type": "complete", "data": dict}
        """
        state, config = self._prepare_state(input_data)
        await self._ensure_checkpointer_ready(config, state["session_id"])
        visitor_id = input_data.get("visitor_id") or input_data.get("session_id", "anonymous")
        context = WorkflowContext(user_id=visitor_id)
        event_stream = self.graph.astream_events(
            state,
            config=config,
            version="v2",
            context=context,
        )
        try:
            async for event in event_stream:
                kind = event["event"]
                if kind == "on_chat_model_stream":
                    content = event["data"]["chunk"].content
                    if content:
                        yield {"type": "token", "content": content}
                elif kind == "on_chain_end" and event.get("name") == "format_response":
                    yield {"type": "complete", "data": event["data"].get("output", {})}
        finally:
            # Ensure upstream async generator is closed when the client disconnects
            # or the consumer stops iteration early (SSE test path).
            aclose = getattr(event_stream, "aclose", None)
            if callable(aclose):
                try:
                    await aclose()
                except Exception:
                    logger.debug("Failed to close astream_events generator cleanly", exc_info=True)

    async def close(self):
        """リソースのクリーンアップ"""
        await self.orchestrator.close()
        if self.checkpointer:
            try:
                # AsyncPostgresSaverの適切なクローズメソッドを使用
                if hasattr(self.checkpointer, "aclose"):
                    await self.checkpointer.aclose()
                elif hasattr(self.checkpointer, "conn") and hasattr(
                    self.checkpointer.conn, "close"
                ):
                    await self.checkpointer.conn.close()
                logger.info("Checkpointer connection closed")
            except Exception as e:
                logger.warning("Error closing checkpointer: %s", e)
