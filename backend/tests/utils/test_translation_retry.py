"""Tests for tRAG translation retry/backoff (Issue #487)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# =============================================================================
# TranslationService.translate() retry tests
# =============================================================================


class TestTranslationServiceRetry:
    """Tests for retry logic in TranslationService.translate()."""

    @pytest.mark.asyncio
    async def test_translate_succeeds_on_first_attempt(self):
        from backend.services.translation_service import TranslationService

        svc = TranslationService.__new__(TranslationService)
        svc._model_dir = "/dummy"
        svc._translators = {}
        svc._source_sps = {}
        svc._target_sps = {}

        async def _fake_executor(executor, fn, *args):
            return "翻訳されたテキスト"

        with patch.object(
            asyncio.get_running_loop(),
            "run_in_executor",
            side_effect=_fake_executor,
        ):
            result = await svc.translate("hello", "en_to_ja")
            assert result == "翻訳されたテキスト"

    @pytest.mark.asyncio
    async def test_translate_retries_on_failure_then_succeeds(self):
        from backend.services.translation_service import TranslationService

        svc = TranslationService.__new__(TranslationService)
        svc._model_dir = "/dummy"
        svc._translators = {}
        svc._source_sps = {}
        svc._target_sps = {}

        call_count = 0

        async def _fake_executor(executor, fn, *args):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("model load failed")
            return "翻訳結果"

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with patch.object(
                asyncio.get_running_loop(),
                "run_in_executor",
                side_effect=_fake_executor,
            ):
                result = await svc.translate("hello", "en_to_ja")
                assert result == "翻訳結果"
                assert call_count == 2

    @pytest.mark.asyncio
    async def test_translate_returns_original_after_all_retries_exhausted(self):
        from backend.services.translation_service import TranslationService

        svc = TranslationService.__new__(TranslationService)
        svc._model_dir = "/dummy"
        svc._translators = {}
        svc._source_sps = {}
        svc._target_sps = {}

        async def _always_fail(executor, fn, *args):
            raise RuntimeError("persistent failure")

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with patch.object(
                asyncio.get_running_loop(),
                "run_in_executor",
                side_effect=_always_fail,
            ):
                result = await svc.translate("hello", "en_to_ja")
                assert result == "hello"

    @pytest.mark.asyncio
    async def test_translate_skip_when_already_japanese(self):
        from backend.services.translation_service import TranslationService

        svc = TranslationService.__new__(TranslationService)
        svc._model_dir = "/dummy"
        svc._translators = {}
        svc._source_sps = {}
        svc._target_sps = {}

        result = await svc.translate("こんにちは", "en_to_ja")
        assert result == "こんにちは"


# =============================================================================
# _translate_llm_with_retry tests
# =============================================================================


class TestTranslateLlmWithRetry:
    """Tests for KO/ZH LLM translation retry via _translate_llm_with_retry."""

    @pytest.mark.asyncio
    async def test_llm_translate_succeeds_on_first_try(self):
        from backend.workflows.main_workflow import _translate_llm_with_retry

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "営業時間は何時ですか"}}]
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
            with patch(
                "backend.workflows.main_workflow._get_trag_client",
                return_value=mock_client,
            ):
                result = await _translate_llm_with_retry("영업시간", "ko")
                assert result == "営業時間は何時ですか"
                mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_translate_retries_on_500_then_succeeds(self):
        from backend.workflows.main_workflow import _translate_llm_with_retry

        mock_resp_500 = MagicMock()
        mock_resp_500.status_code = 500
        mock_resp_500.text = "Internal Server Error"

        mock_resp_200 = MagicMock()
        mock_resp_200.status_code = 200
        mock_resp_200.json.return_value = {"choices": [{"message": {"content": "営業時間"}}]}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=[mock_resp_500, mock_resp_200])

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with patch(
                    "backend.workflows.main_workflow._get_trag_client",
                    return_value=mock_client,
                ):
                    result = await _translate_llm_with_retry("营业时间", "zh")
                    assert result == "営業時間"
                    assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_llm_translate_returns_empty_after_max_retries(self):
        from backend.workflows.main_workflow import _translate_llm_with_retry

        mock_resp_500 = MagicMock()
        mock_resp_500.status_code = 500
        mock_resp_500.text = "Error"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp_500)

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with patch(
                    "backend.workflows.main_workflow._get_trag_client",
                    return_value=mock_client,
                ):
                    result = await _translate_llm_with_retry(
                        "test",
                        "ko",
                        max_retries=2,
                    )
                    assert result == ""
                    assert mock_client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_llm_translate_no_api_key_returns_empty(self):
        from backend.workflows.main_workflow import _translate_llm_with_retry

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": ""}):
            result = await _translate_llm_with_retry("test", "zh")
            assert result == ""

    @pytest.mark.asyncio
    async def test_llm_translate_strips_preamble(self):
        from backend.workflows.main_workflow import _translate_llm_with_retry

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Translation: 営業時間は9時から22時です"}}]
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
            with patch(
                "backend.workflows.main_workflow._get_trag_client",
                return_value=mock_client,
            ):
                result = await _translate_llm_with_retry("hours", "ko")
                assert result == "営業時間は9時から22時です"
                assert not result.startswith("Translation")

    @pytest.mark.asyncio
    async def test_llm_translate_returns_empty_for_english_only_output(self):
        from backend.workflows.main_workflow import _translate_llm_with_retry

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Business hours are from 9am"}}]
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
            with patch(
                "backend.workflows.main_workflow._get_trag_client",
                return_value=mock_client,
            ):
                result = await _translate_llm_with_retry("hours", "zh")
                assert result == ""

    @pytest.mark.asyncio
    async def test_llm_translate_retries_on_connection_error(self):
        from backend.workflows.main_workflow import _translate_llm_with_retry

        call_count = 0

        async def _post_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Connection reset")
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"choices": [{"message": {"content": "営業時間"}}]}
            return mock_resp

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=_post_side_effect)

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with patch(
                    "backend.workflows.main_workflow._get_trag_client",
                    return_value=mock_client,
                ):
                    result = await _translate_llm_with_retry("test", "ko")
                    assert result == "営業時間"
                    assert call_count == 2
