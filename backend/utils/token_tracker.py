"""
トークン使用量/コスト追跡ユーティリティ

リクエストスコープでLLM呼び出しのトークン消費とコストを集計する。
"""

import logging
import os
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_CEREBRAS_INPUT_COST_PER_1K = 0.0
_DEFAULT_CEREBRAS_OUTPUT_COST_PER_1K = 0.0


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("Invalid %s=%r. Falling back to %.6f.", name, raw, default)
        return default


@dataclass
class TokenUsage:
    """単一LLM呼び出しのトークン使用量"""

    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float


@dataclass
class LLMCallMetadata:
    """Successful LLM call metadata captured for request observability."""

    provider: str
    model: str
    llm_latency_ms: int

    def as_log_metadata(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "llm_latency_ms": self.llm_latency_ms,
        }


@dataclass
class TokenTracker:
    """リクエストスコープのトークン使用量トラッカー"""

    _usages: List[TokenUsage] = field(default_factory=list)
    _llm_calls: List[LLMCallMetadata] = field(default_factory=list)

    def record(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> TokenUsage:
        """トークン使用量を記録

        Args:
            model: モデルID
            prompt_tokens: プロンプトトークン数
            completion_tokens: 完了トークン数

        Returns:
            TokenUsage: 記録されたトークン使用量
        """
        if prompt_tokens < 0 or completion_tokens < 0:
            logger.warning(
                "Negative token count corrected: model=%s, prompt=%d, completion=%d",
                model,
                prompt_tokens,
                completion_tokens,
            )
            prompt_tokens = max(0, prompt_tokens)
            completion_tokens = max(0, completion_tokens)
        total_tokens = prompt_tokens + completion_tokens
        cost = self._estimate_cost(model, prompt_tokens, completion_tokens)

        usage = TokenUsage(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=round(cost, 6),
        )
        self._usages.append(usage)

        logger.debug(
            "Token usage recorded: model=%s, tokens=%d, cost=$%.6f",
            model,
            total_tokens,
            cost,
        )

        return usage

    def record_llm_call(
        self,
        *,
        provider: str,
        model: str,
        llm_latency_ms: int,
    ) -> LLMCallMetadata:
        """Record successful LLM provider/model metadata for this request."""

        metadata = LLMCallMetadata(
            provider=provider,
            model=model,
            llm_latency_ms=max(0, int(llm_latency_ms)),
        )
        self._llm_calls.append(metadata)
        logger.debug(
            "LLM call metadata recorded: provider=%s model=%s latency_ms=%d",
            metadata.provider,
            metadata.model,
            metadata.llm_latency_ms,
        )
        return metadata

    def _estimate_cost(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> float:
        """コストを推定（MODEL_CONFIGSから取得）"""
        try:
            from backend.llm.models import MODEL_CONFIGS

            for config in MODEL_CONFIGS.values():
                if config.model_id.value == model:
                    input_cost = (prompt_tokens / 1000) * config.input_cost_per_1k
                    output_cost = (completion_tokens / 1000) * config.output_cost_per_1k
                    return input_cost + output_cost
            cerebras_fast_model = os.getenv("CEREBRAS_FAST_MODEL", "gpt-oss-120b").strip()
            if model == cerebras_fast_model or model.startswith("gpt-oss"):
                input_cost_per_1k = _env_float(
                    "CEREBRAS_INPUT_COST_PER_1K",
                    _DEFAULT_CEREBRAS_INPUT_COST_PER_1K,
                )
                output_cost_per_1k = _env_float(
                    "CEREBRAS_OUTPUT_COST_PER_1K",
                    _DEFAULT_CEREBRAS_OUTPUT_COST_PER_1K,
                )
                input_cost = (prompt_tokens / 1000) * input_cost_per_1k
                output_cost = (completion_tokens / 1000) * output_cost_per_1k
                return input_cost + output_cost
            logger.warning("No cost data for model '%s'. Cost reported as $0.00.", model)
        except Exception as e:
            logger.debug("Cost estimation failed: %s", e)
        return 0.0

    @property
    def usages(self) -> List[TokenUsage]:
        """記録済み使用量一覧"""
        return list(self._usages)

    @property
    def llm_calls(self) -> List[LLMCallMetadata]:
        """Recorded successful LLM calls for this request."""
        return list(self._llm_calls)

    @property
    def latest_llm_call(self) -> Optional[LLMCallMetadata]:
        """Most recent successful LLM call for response-level observability."""
        return self._llm_calls[-1] if self._llm_calls else None

    @property
    def total_tokens(self) -> int:
        """合計トークン数"""
        return sum(u.total_tokens for u in self._usages)

    @property
    def total_cost_usd(self) -> float:
        """合計推定コスト (USD)"""
        return round(sum(u.estimated_cost_usd for u in self._usages), 6)

    def summary(self) -> dict:
        """サマリーを生成"""
        if not self._usages:
            return {
                "total_calls": 0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
            }

        model_breakdown: dict[str, dict] = {}
        for usage in self._usages:
            if usage.model not in model_breakdown:
                model_breakdown[usage.model] = {
                    "calls": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "cost_usd": 0.0,
                }
            mb = model_breakdown[usage.model]
            mb["calls"] += 1
            mb["prompt_tokens"] += usage.prompt_tokens
            mb["completion_tokens"] += usage.completion_tokens
            mb["total_tokens"] += usage.total_tokens
            mb["cost_usd"] = round(mb["cost_usd"] + usage.estimated_cost_usd, 6)

        return {
            "total_calls": len(self._usages),
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
            "model_breakdown": model_breakdown,
        }

    def reset(self):
        """使用量をクリア"""
        self._usages.clear()
        self._llm_calls.clear()


# リクエストスコープのContextVar
_token_tracker_var: ContextVar[Optional[TokenTracker]] = ContextVar("token_tracker", default=None)


def get_token_tracker() -> TokenTracker:
    """現在のリクエストスコープのトークントラッカーを取得（なければ作成）"""
    tracker = _token_tracker_var.get()
    if tracker is None:
        tracker = TokenTracker()
        _token_tracker_var.set(tracker)
    return tracker


def record_llm_call_metadata(*, provider: str, model: str, llm_latency_ms: int) -> LLMCallMetadata:
    """Record successful LLM metadata in the current request context."""

    return get_token_tracker().record_llm_call(
        provider=provider,
        model=model,
        llm_latency_ms=llm_latency_ms,
    )


def get_latest_llm_metadata() -> dict[str, Any]:
    """Return latest successful LLM metadata for the current request, if any."""

    latest = get_token_tracker().latest_llm_call
    return latest.as_log_metadata() if latest else {}


def reset_token_tracker() -> None:
    """リクエストスコープのトークントラッカーをリセット"""
    _token_tracker_var.set(None)
